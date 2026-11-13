#!/usr/bin/env python3
"""ABUTRON APEX: root-owned Deriv DEMO native order dispatch & reconciliation.

Integration with current production modules:
- apex_signal_native_router_v1.plan/account_rows/ea_state
- customer_order_ledger.reserve/queue_native_usd_pending/broker_ack/confirm_position/closed
- V2 MT5 EA immutable receipts and broker-position evidence

Does NOT create customer authorization, alter licenses, bypass handover, or trade LIVE.
No automatic retry of an unknown outcome, including after restart.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path[:0] = ["/opt/apex-client-mt5", "/opt/apex-client-portal", "/opt/apex-signup"]
import apex_signal_native_router_v1 as router
from apex_deriv_trade_symbol_scope import TRADE_SYMBOLS
import customer_order_ledger as ledger

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
REQUEST_NAME = "APEX_NATIVE_ORDER_V1.req"
RECEIPT_DIR = "receipts"
EVIDENCE_DIR = "evidence"
MAX_RECEIPT_AGE_SEC = 2 * 86400
MAX_EVIDENCE_AGE_SEC = 130
MAX_DOLLAR_ERROR = 2.0  # broker tick rounding: before commission and slippage
ROOT = Path("/var/lib/apex-client-feed/execution-router")
ORIGINAL_EA_STATE = router.ea_state
ADAPTIVE_FLAG=Path("/etc/abutron/optionc-live-010.json")
def optionc_on(cid=None):
    if not ADAPTIVE_FLAG.is_file() or ADAPTIVE_FLAG.is_symlink():return False
    policy=router.read(ADAPTIVE_FLAG)
    if (policy.get("schema")!="abutron.optionc.activation.v2" or
        policy.get("demo_only") is not True):
        raise Refused("DERIV_ADAPTIVE_FLAG_POLICY_INVALID")
    allow=policy.get("deriv_connection_allowlist")
    if (not isinstance(allow,list) or len(allow)!=1 or
            not isinstance(allow[0],str) or not HEX32.fullmatch(allow[0])):
        raise Refused("DERIV_ADAPTIVE_ACCOUNT_ALLOWLIST_INVALID")
    return policy.get("deriv_enabled") is True and cid==allow[0]



def ea_state_v2(cid: str, login: str, server: str):
    """Support existing V1 proof for diagnostics, V2 for dispatch.

    No V1 EA will receive an order from this package.
    """
    try:
        if not HEX32.fullmatch(cid):
            return None, "INVALID_CONNECTION"
        home = router.manager.state(cid)
        health = router.read(home / "worker-health.json")
        nonce = health.get("nonce", "")
        if not HEX32.fullmatch(nonce) or health.get("status") != "CONNECTED":
            return None, "NATIVE_BROKER_HEALTH_INVALID"
        folder = home / "terminal/MQL5/Files"
        ready = folder / ("ABUTRON_APEX_BRIDGE_READY_V3_" + nonce + ".txt")
        proto = 3
        header = "APEX_NATIVE_BRIDGE_READY_V3"
        if not ready.is_file():
            ready = folder / ("ABUTRON_APEX_BRIDGE_READY_V2_" + nonce + ".txt")
            proto = 2
            header = "APEX_NATIVE_BRIDGE_READY_V2"
        if ready.is_file() and not ready.is_symlink() and 0 <= time.time() - ready.stat().st_mtime <= 12:
            rows = ready.read_text(encoding="utf-8-sig").splitlines()
            if rows[:5] != [header, nonce, login, server, "DERIV_DEMO"] or len(rows) != 11:
                return None, "NATIVE_BRIDGE_ACCOUNT_IDENTITY_MISMATCH"
            t, pending, positions, terminal, broker, enabled = map(int, rows[5:11])
            if abs(time.time() - t) > 18 or not 0 <= pending <= 300 or not 0 <= positions <= 300:
                return None, "NATIVE_V2_EXPOSURE_PROOF_INVALID"
            return {"nonce": nonce, "bridge_loaded": True, "exposure_verified": True,
                    "pending_orders": pending, "positions": positions,
                    "terminal_trade_allowed": terminal == 1,
                    "account_trade_allowed": broker == 1,
                    "native_demo_orders_enabled": enabled == 1,
                    "protocol_version": proto, "files": folder}, None
    except (ValueError, TypeError, IndexError, OSError, UnicodeError):
        return None, "NATIVE_V2_PROOF_UNREADABLE"
    state, err = ORIGINAL_EA_STATE(cid, login, server)
    if state is not None:
        state["native_demo_orders_enabled"] = False
        state["protocol_version"] = 1
    return state, err


# Reuse existing router's full gates while requiring the upgraded EA for orders.
router.ea_state = ea_state_v2


class Refused(RuntimeError):
    pass


def seconds(iso: str) -> float:
    date = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("naive time")
    return time.time() - date.timestamp()


def atomic_native_request(path: Path, lines: list[str]) -> None:
    """Create exactly one command in the terminal's private Files/ABUTRON directory.

    Preconditions: correct account and order checks plus durable UNKNOWN ledger state.
    Atomic rename avoids half-written requests; never overwrite an unconsumed one.
    """
    if path.is_symlink() or path.exists():
        raise Refused("NATIVE_REQUEST_ALREADY_PRESENT")
    if any("\r" in x or "\n" in x for x in lines):
        raise Refused("INVALID_REQUEST_DELIMITERS")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise Refused("NATIVE_REQUEST_DIRECTORY_UNAVAILABLE")
    st = parent.stat()
    fd, tmp = tempfile.mkstemp(prefix=".apex-native-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))
            out.flush()
            os.fsync(out.fileno())
        os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, 0o600)
        if path.exists():
            raise Refused("ANOTHER_NATIVE_REQUEST_HAS_APPEARED")
        os.replace(tmp, path)
        dfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def verify_6207_audit_readiness(files: Path, nonce: str, login: str, server: str) -> None:
    """Require a current account-bound audit-capable MT5 EA before demo request."""
    marker=files/("ABUTRON_EXECUTION_AUDIT_V1_"+nonce+".txt")
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size>1024:
        raise Refused("AUDIT_EA_NATIVE_CAPABILITY_MISSING")
    rows=marker.read_text(encoding="utf-8-sig").splitlines()
    if len(rows)!=8 or rows[:4]!=[
        "ABUTRON_EXECUTION_AUDIT_READY_V1",nonce,str(login),str(server)]:
        raise Refused("AUDIT_EA_IDENTITY_INVALID")
    try:
        diff=time.time()-int(rows[4])
    except (ValueError,TypeError):
        raise Refused("AUDIT_EA_TIME_INVALID")
    if not -5<=diff<=15 or rows[6:]!=["1","1"]:
        raise Refused("AUDIT_EA_STALE_OR_ADAPTIVE_RECONCILER_DISABLED")


def atomic_audit_client_context(folder: Path, key: str, nonce: str, login: str,
                                server: str, symbol: str, side: str) -> None:
    """Immutable event before request publication: original host client time_ns."""
    if not HEX64.fullmatch(key) or side not in ("BUY","SELL"):
        raise Refused("AUDIT_REQUEST_ID_OR_SIDE_INVALID")
    parent=folder/"execution-audit"
    if parent.is_symlink() or not parent.is_dir():
        raise Refused("AUDIT_REQUEST_DIRECTORY_UNAVAILABLE")
    path=parent/(key+".client.txt")
    if path.is_symlink() or path.exists():
        raise Refused("DUPLICATE_CLIENT_AUDIT_CONTEXT")
    st=parent.stat()
    body="\r\n".join([
      "ABUTRON_NATIVE_CLIENT_CONTEXT_V1",key,nonce,str(login),str(server),
      symbol,side,str(time.time_ns()),str(time.monotonic_ns())])+"\r\n"
    fd,tmp=tempfile.mkstemp(prefix=".audit-client-",dir=parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(body.encode("utf-8"));f.flush();os.fsync(f.fileno())
        os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,0o600)
        if path.exists():raise Refused("CONCURRENT_CLIENT_AUDIT_CONTEXT")
        os.replace(tmp,path)
        dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def parse_receipt(path: Path, key: str, nonce: str, login: str, server: str) -> dict | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4000:
        return None
    rows = path.read_text(encoding="utf-8-sig").splitlines()
    if len(rows) != 10 or rows[:2] != ["APEX_NATIVE_V2", key]:
        raise Refused("NATIVE_RECEIPT_SCHEMA_OR_IDENTITY_INVALID")
    kind, reason, order, deal, timestamp, got_nonce, got_login, got_server = rows[2:]
    if (got_nonce, got_login, got_server) != (nonce, login, server):
        raise Refused("NATIVE_RECEIPT_ACCOUNT_MISMATCH")
    if kind not in ("BLOCKED", "UNKNOWN", "ACK") or not reason or len(reason) > 120:
        raise Refused("NATIVE_RECEIPT_STATE_INVALID")
    order, deal, timestamp = int(order), int(deal), int(timestamp)
    if not 0 <= time.time() - timestamp <= MAX_RECEIPT_AGE_SEC:
        raise Refused("NATIVE_RECEIPT_STALE_OR_FUTURE")
    if kind == "ACK" and (order <= 0 or deal <= 0):
        raise Refused("BROKER_RECEIPT_MISSING_IDENTIFIERS")
    return {"kind": kind, "reason": reason, "order": order, "deal": deal, "when": timestamp}


def parse_position(path: Path, key: str, nonce: str, login: str, server: str) -> dict | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 5000:
        return None
    r = path.read_text(encoding="utf-8-sig").splitlines()
    # schema/key/nonce/login/server/symbol/side/order/deal/position/volume/
    # entry/sl/tp/loss_usd/tp_usd/status/ts/exit_deal
    if len(r) != 19 or r[:5] != ["APEX_BROKER_POSITION_V2", key, nonce, login, server]:
        raise Refused("POSITION_PROOF_IDENTITY_INVALID")
    symbol, side, order, deal, pos = r[5], r[6], int(r[7]), int(r[8]), int(r[9])
    volume, entry, sl, tp, loss, gain = map(float, r[10:16])
    state, timestamp, exit_deal = r[16], int(r[17]), int(r[18])
    if not -5 <= time.time() - timestamp <= MAX_EVIDENCE_AGE_SEC:
        raise Refused("POSITION_PROOF_STALE")
    if state not in ("OPEN_PROTECTED", "OPEN_UNPROTECTED", "CLOSED_BROKER_VERIFIED", "NOT_YET_VISIBLE"):
        raise Refused("POSITION_PROOF_UNKNOWN_STATUS")
    values = (volume, entry, sl, tp, loss, gain)
    if (symbol not in ledger.SYMBOLS or side not in ("BUY", "SELL") or
        min(order, deal, pos) <= 0 or not all(math.isfinite(v) for v in values)):
        raise Refused("POSITION_PROOF_INVALID_VALUES")
    if state == "OPEN_PROTECTED":
        geometry=(volume>0 and entry>0 and sl>0 and tp>0 and
          ((sl<entry<tp) if side=="BUY" else (tp<entry<sl)))
        legacy=((abs(loss-50.0)<=MAX_DOLLAR_ERROR and
                 abs(gain-100.0)<=MAX_DOLLAR_ERROR) or
                (abs(loss-10.0)<=MAX_DOLLAR_ERROR and
                 abs(gain-20.0)<=MAX_DOLLAR_ERROR))
        if not geometry:raise Refused("BROKER_POSITION_STOP_GEOMETRY_INVALID")
        if not legacy:
            from optionc_native_v2_intent_contract import parse_native_intent,native_position_risk
            intent=parse_native_intent(
                 path.parent.parent/"optionc_v2"/(key+".txt"),
                 key,nonce,login,server,symbol,side)
            native_position_risk(intent,broker_position_volume=volume,
                broker_entry=entry,broker_stop=sl,broker_target=tp,
                broker_cash_loss=loss,broker_cash_reward=gain)

    return {"state": state, "symbol": symbol, "side": side, "order": order,
            "deal": deal, "position": pos, "volume": volume, "entry": entry,
            "sl": sl, "tp": tp, "stop_usd": loss, "tp_usd": gain,
            "closed_deal": exit_deal, "timestamp": timestamp}


def fresh_customer_broker_feed(cid: str, owner: str) -> dict:
    audit = router.read(router.BASE / (cid + ".json"))
    if (audit.get("account_id") != owner or audit.get("connection_id") != cid or
        audit.get("broker_data_verified") is not True or
        audit.get("status") != "BROKER_DATA_VERIFIED_SHADOW" or
        not router.timestamp(audit.get("checked_at_utc"), 170)):
        raise Refused("NO_FRESH_CUSTOMER_BROKER_SNAPSHOT")
    account = audit.get("account")
    if not isinstance(account, dict) or not isinstance(account.get("positions"), list):
        raise Refused("NO_BROKER_POSITIONS_LIST")
    return account


def matches_position(account: dict, proof: dict) -> bool:
    for item in account["positions"]:
        try:
            if (int(item.get("ticket")) == proof["position"] and
                item.get("symbol") == proof["symbol"] and
                item.get("side") == proof["side"] and
                abs(float(item.get("sl")) - proof["sl"]) < 1e-7 and
                abs(float(item.get("tp")) - proof["tp"]) < 1e-7):
                return True
        except (TypeError, ValueError):
            continue
    return False


def get_customer_row(cid: str) -> tuple:
    with sqlite3.connect("file:" + router.DB + "?mode=ro", uri=True, timeout=10) as c:
        row = c.execute("""SELECT x.id,x.account_id,x.broker,x.environment,
           x.broker_server,x.status,x.worker_binding,x.account_reference,
           COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
           FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
           WHERE x.id=?""", (cid,)).fetchone()
    if row is None:
        raise Refused("CUSTOMER_ACCOUNT_DISCONNECTED")
    return row


def require_fresh_customer_switch_on(cid: str, owner: str) -> None:
    """Revalidate exact tenant, DEMO broker and client's ON before publication.

    This is a last-read denial guard, not proof of a transactional MT5 ACK.
    No exception can grant execution or change a CRM control.
    """
    row = get_customer_row(cid)
    if (row[0] != cid or row[1] != owner or
            (row[2],row[3],row[4],row[5],row[6]) !=
            ("Deriv","DEMO","Deriv-Demo","CONNECTED","abutron-client-mt5-"+cid)):
        raise Refused("CUSTOMER_ACCOUNT_IDENTITY_CHANGED_BEFORE_SEND")
    if row[8] != 1 or row[9] != 1:
        raise Refused("CUSTOMER_SWITCH_OFF_BEFORE_NATIVE_SEND")


def reconcile_one(c: sqlite3.Connection, row: tuple) -> str:
    # Reconciliation remains permitted with execution OFF, to account for already-sent orders.
    (key, owner, cid, symbol, side, state, order, deal, position) = row
    customer = get_customer_row(cid)
    if customer[1] != owner or customer[4] != "Deriv-Demo" or customer[3] != "DEMO":
        raise Refused("RECONCILIATION_ACCOUNT_IDENTITY_MISMATCH")
    ea, err = router.ea_state(cid, customer[7], customer[4])
    if err or not ea:
        raise Refused("NO_FRESH_MATCHING_BROKER_EA")
    folder = ea["files"] / "ABUTRON"
    receipt = parse_receipt(folder / RECEIPT_DIR / (key + ".txt"), key,
                            ea["nonce"], customer[7], customer[4])
    if state == "RESERVED":
        # RESERVED can be from a pre-crash process. Never automatically resubmit.
        return "UNSENT_OR_UNKNOWN_RESERVED_MANUAL_RECONCILIATION"
    if state == "SUBMISSION_UNKNOWN":
        if receipt is None:
            return "WAITING_FOR_IMMUTABLE_NATIVE_RECEIPT_NO_RETRY"
        if receipt["kind"] == "BLOCKED":
            ledger.broker_rejection(c, key, receipt["reason"][:120])
            return "BROKER_NATIVE_REQUEST_BLOCKED"
        if receipt["kind"] == "UNKNOWN":
            return "UNKNOWN_BROKER_RESULT_NO_RETRY"
        ledger.broker_ack(c, key, receipt["order"], receipt["deal"])
        order, deal, state = receipt["order"], receipt["deal"], "BROKER_ACK_UNRECONCILED"
    if state not in ("BROKER_ACK_UNRECONCILED", "OPEN_PROTECTED", "UNPROTECTED"):
        return "NO_RECONCILIATION_TRANSITION"
    proof = parse_position(folder / EVIDENCE_DIR / (key + ".txt"), key,
                           ea["nonce"], customer[7], customer[4])
    if proof is None or proof["state"] == "NOT_YET_VISIBLE":
        return "WAITING_FOR_VERIFIED_BROKER_POSITION"
    if proof["symbol"] != symbol or proof["side"] != side or proof["order"] != order or proof["deal"] != deal:
        raise Refused("BROKER_POSITION_DOES_NOT_MATCH_ORIGINAL_TRADE")
    account = fresh_customer_broker_feed(cid, owner)
    if state == "BROKER_ACK_UNRECONCILED":
        # A broker-native deal may open and CLOSE before the first account-feed
        # poll. Recover this terminal state only when the original ACK, broker
        # exit deal, position identity and absence from the broker feed agree.
        # Never invent an OPEN_PROTECTED state or resubmit any order.
        if proof["state"] == "CLOSED_BROKER_VERIFIED":
            if proof["closed_deal"] <= 0 or proof["position"] <= 0:
                return "EARLY_CLOSURE_MISSING_NATIVE_EXIT_IDENTIFIERS"
            if any(int(p.get("ticket",-1)) == proof["position"]
                   for p in account["positions"]):
                return "EARLY_CLOSURE_STILL_PRESENT_IN_BROKER_FEED"
            c.execute("BEGIN IMMEDIATE")
            try:
                updated=c.execute("""UPDATE attempts
                    SET state='CLOSED_RECONCILED',broker_position=?,
                        reason='CLOSED_BROKER_VERIFIED_BEFORE_OPEN_ACK',
                        updated_at_utc=?
                    WHERE signal_key=? AND state='BROKER_ACK_UNRECONCILED'
                      AND broker_order=? AND broker_deal=?""",
                    (proof["position"],ledger.utc(),key,order,deal))
                if updated.rowcount!=1:
                    raise Refused("BROKER_EARLY_CLOSURE_STATE_CONFLICT")
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
            return "EARLY_CLOSED_BROKER_RECONCILED"
        if proof["state"] != "OPEN_PROTECTED" or not matches_position(account, proof):
            return "POSITION_PROTECTION_UNVERIFIED_HOLD"
        # Existing ledger.confirm_position requires broker price fields, which
        # were intentionally not known when the order was reserved.
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("""UPDATE attempts SET volume=?,entry_price=?,stop_loss=?,take_profit=?,
                     broker_position=?,updated_at_utc=? WHERE signal_key=?
                     AND state='BROKER_ACK_UNRECONCILED'""",
                      (proof["volume"], proof["entry"], proof["sl"], proof["tp"],
                       proof["position"], ledger.utc(), key))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        ledger.confirm_position(c, key, proof["position"], proof["sl"], proof["tp"], True, True)
        return "OPEN_PROTECTED_BROKER_VERIFIED"
    if state in ("OPEN_PROTECTED", "UNPROTECTED"):
        if proof["state"] == "CLOSED_BROKER_VERIFIED" and proof["closed_deal"] > 0:
            if any(int(p.get("ticket", -1)) == proof["position"] for p in account["positions"]):
                return "CLOSURE_NOT_YET_ABSENT_IN_BROKER_FEED"
            ledger.closed(c, key, proof["position"], proof["closed_deal"], True)
            return "CLOSED_AND_RECONCILED"
        if proof["state"] != "OPEN_PROTECTED" or not matches_position(account, proof):
            return "POSITION_CHANGED_OR_UNPROTECTED_MANUAL_INTERVENTION"
        return "STILL_OPEN_PROTECTED"
    return "BROKER_PROOF_REQUIRES_MANUAL_REVIEW"


def reconcile() -> list[tuple[str, str]]:
    c = ledger.new()
    results = []
    try:
        rows = c.execute("""SELECT signal_key,owner,connection_id,symbol,side,state,
                            broker_order,broker_deal,broker_position
                            FROM attempts WHERE state IN
                            ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED',
                             'OPEN_PROTECTED','UNPROTECTED')
                            ORDER BY created_at_utc""").fetchall()
        for row in rows:
            try:
                status = reconcile_one(c, row)
            except (Refused, ledger.Blocked, ValueError, OSError, sqlite3.Error) as ex:
                status = "HOLD_" + str(ex)[:90]
            results.append((row[0][:12], status))
    finally:
        c.close()
    return results


def ensure_twenty_percent_nominal_equity_ceiling(account: dict, occupied: set[str]) -> None:
    """Check prospective NEW DEMO $50 stop against 20% CURRENT broker equity.

    No existing position/SL/TP/lot changes. This is a nominal stop-risk cap,
    not an enforceable worst-case loss bound (broker slippage may exceed stops).
    Existing portfolio guard has already reconciled all broker positions.
    """
    equity=account.get("equity_usd")
    if (type(equity) not in (int,float) or not math.isfinite(equity) or equity<=0):
        raise Refused("BROKER_EQUITY_UNAVAILABLE_FOR_20_PERCENT_RISK_CAP")
    positions=account.get("positions")
    if not isinstance(positions,list) or len(positions)!=len(occupied):
        raise Refused("PORTFOLIO_EXPOSURE_NOT_VERIFIED_FOR_20_PERCENT_RISK_CAP")
    # Broker tick-rounding allowance $2 per $50 gross stop. Existing portfolio
    # capacity() independently checks native protection and ledger consistency.
    projected_loss=52.0
    for position in positions:
        floating=position.get("floating_profit_usd")
        if (type(floating) not in (int,float) or not math.isfinite(floating)):
            raise Refused("BROKER_FLOATING_PNL_INVALID_FOR_20_PERCENT_RISK_CAP")
        projected_loss+=max(0.0,52.0+float(floating))
    if projected_loss>float(equity)*0.20:
        raise Refused("NEW_ENTRY_NOMINAL_PORTFOLIO_RISK_EXCEEDS_20_PERCENT_EQUITY")


def send_once(doc: dict) -> str:
    if not doc.get("execution_authorized") or not doc.get("candidate_orders"):
        raise Refused("ACCOUNT_NOT_AUTHORIZED_BY_CURRENT_ROUTER")
    cid, owner = doc["connection_id"], doc["account_id"]
    if not (HEX32.fullmatch(cid) and HEX32.fullmatch(owner)):
        raise Refused("INVALID_OWNER_ACCOUNT_ID")
    # Recompute the existing router's full authorization from LIVE data at dispatch time.
    # Require the account-specific adaptive 0.10% equity DEMO policy.
    # Never fall back to the legacy $50 fixed-stop for another Deriv account.
    # Reconciliation of existing positions runs outside send_once().
    if not optionc_on(cid):
        raise Refused("DERIV_LEGACY_FIXED_RISK_ORDER_DISPATCH_DISABLED")
    row = get_customer_row(cid)
    policy, profile, handover = router.read(router.POLICY), router.read(router.PROFILE), router.read(router.HANDOVER)
    current = router.plan(row, profile, policy, handover, "dispatch")
    if current.get("blockers") or not current.get("execution_authorized"):
        raise Refused("ACCOUNT_NO_LONGER_EXECUTION_AUTHORIZED")
    requested = doc["candidate_orders"][0]["signal_key"]
    candidates = [x for x in current["candidate_orders"] if x["signal_key"] == requested]
    if not candidates:
        raise Refused("RESEARCH_SIGNAL_EXPIRED_OR_CHANGED")
    candidate = candidates[0]
    if candidate["symbol"] not in TRADE_SYMBOLS:
        raise Refused("DERIV_SYMBOL_REMOVED_FROM_NEW_ENTRY_ALLOWLIST")
    adaptive=optionc_on(cid)
    # V75 is owner-approved. Existing EA must still pass native stop geometry,
    # broker OrderCheck, account margin and portfolio risk proof.
    # Existing trades on other symbols must remain broker-protected and
    # independently reconciled before one new trade can be reserved.
    from apex_portfolio_guard_v3 import capacity,UnsafeExposure
    ea_check,err_check=ea_state_v2(cid,row[7],row[4])
    account=fresh_customer_broker_feed(cid,owner)
    try:
        occupied=capacity(cid,account,ea_check,row[7],row[4],ledger.SYMBOLS,ledger.DB)
    except UnsafeExposure as exc:
        raise Refused(str(exc)) from exc
    if candidate["symbol"] in occupied:
        raise Refused("SYMBOL_ALREADY_HAS_PROTECTED_BROKER_POSITION")
    ensure_twenty_percent_nominal_equity_ceiling(account,occupied)
    ea, err = router.ea_state(cid, row[7], row[4])
    if err or not ea or not ea.get("exposure_verified") or not ea.get("terminal_trade_allowed") or not ea.get("account_trade_allowed"):
        raise Refused("NO_CURRENT_BROKER_NATIVE_EXECUTION_PROOF")
    if ea.get("protocol_version") != 3 or not ea.get("native_demo_orders_enabled"):
        raise Refused("NATIVE_V3_EA_NOT_LOADED_OR_ORDERS_INPUT_DISABLED")
    if ea["pending_orders"] != 0 or ea["positions"] >= 13:
        raise Refused("NATIVE_PORTFOLIO_POSITION_LIMIT_OR_PENDING_ORDER")
    if adaptive:
        capability=ea["files"]/("ABUTRON_OPTIONC_DERIV_CAPABILITY_V2_"+
                                ea["nonce"]+".txt")
        if (capability.is_symlink() or not capability.is_file() or
            not 0<=time.time()-capability.stat().st_mtime<=12):
            raise Refused("ADAPTIVE_DERIV_NATIVE_EA_NOT_RUNNING")
        marker=capability.read_text(encoding="utf-8-sig").splitlines()
        if (len(marker)!=9 or marker[:5]!=[
            "APEX_OPTIONC_ADAPTIVE_CAPABILITY_V2",ea["nonce"],
            row[7],row[4],"DERIV"] or marker[6:]!=["1","0.10","20"] or
            abs(time.time()-int(marker[5]))>18):
            raise Refused("ADAPTIVE_DERIV_NATIVE_CAPABILITY_INVALID")
    else:
        # Unchanged pre-cutover $50/$100 native capability proof.
        policy_proof = ea["files"] / ("ABUTRON_APEX_V2_USD_50_100_" +
                                    ea["nonce"] + ".txt")
        if (policy_proof.is_symlink() or not policy_proof.is_file() or
            not 0 <= time.time()-policy_proof.stat().st_mtime <= 12):
            raise Refused("NATIVE_50_100_COMPILED_EA_NOT_ACTIVE")
        marker = policy_proof.read_text(encoding="utf-8-sig").splitlines()
        expected_prefix = ["APEX_NATIVE_BRIDGE_USD_50_100_V1", ea["nonce"],
                           row[7], row[4], "DERIV_DEMO"]
        try:
            if (len(marker)!=11 or marker[:5]!=expected_prefix or
                abs(time.time()-int(marker[5]))>18 or
                int(marker[6])!=ea["pending_orders"] or
                int(marker[7])!=ea["positions"] or
                int(marker[8])!=1 or int(marker[9])!=1 or int(marker[10])!=1):
                raise Refused("NATIVE_50_100_EA_CAPABILITY_INVALID")
        except (ValueError,TypeError,IndexError):
            raise Refused("NATIVE_50_100_EA_CAPABILITY_INVALID")
    folder = ea["files"] / "ABUTRON"
    if not folder.is_dir() or folder.is_symlink():
        raise Refused("BROKER_TERMINAL_ORDER_DIRECTORY_MISSING")
    # No pending request or stale, unreconciled receipt can be overwritten.
    if (folder / REQUEST_NAME).exists():
        raise Refused("UNCONSUMED_BROKER_REQUEST_EXISTS")
    key = candidate["signal_key"]
    if not HEX64.fullmatch(key):
        raise Refused("INVALID_SIGNAL_KEY")
    if (folder / RECEIPT_DIR / (key + ".txt")).exists():
        raise Refused("PREEXISTING_BROKER_RECEIPT")
    qty = candidate["volume"]
    if not (isinstance(qty, (float, int)) and math.isfinite(qty) and qty > 0):
        raise Refused("INVALID_ORDER_VOLUME")
    proof = {"broker": "Deriv", "environment": "DEMO", "server": "Deriv-Demo",
             "current_broker_identity_verified": True, "open_positions": ea["positions"],
             "occupied_symbols": sorted(occupied), "protected_positions_reconciled": True,
             "pending_orders": ea["pending_orders"], "risk_governor_approved": True,
             "account_trade_authorized": current["execution_authorized"],
             "single_writer_approved": handover.get("status") == "APPROVED_FOR_TRADING_CUTOVER"}
    require_fresh_customer_switch_on(cid,owner)
    c = ledger.new()
    try:
        ledger.reserve(c, owner, cid, candidate["symbol"], candidate["side"],
                       candidate["m5_bar_time"], key, proof)
        # UNKNOWN is made durable BEFORE placing bytes into broker's command folder.
        if adaptive:
            ledger.queue_native_adaptive_pending(c,key,account["equity_usd"])
        else:
            ledger.queue_native_usd_pending(c,key,qty,50.0,100.0)
    finally:
        c.close()
    expires = int(time.time() + 12)
    if adaptive:
        protocol,volume,stop,target=("APEX_NATIVE_ADAPTIVE_ORDER_V3",
                                     "AUTO","0.10","STRUCTURE_M5")
    else:
        protocol,volume,stop,target=("APEX_NATIVE_ORDER_V2",str(qty),"50","100")
    lines = [protocol,ea["nonce"],key,row[7],row[4],
             candidate["symbol"],candidate["side"],volume,stop,target,
             str(expires),"SEND_DEMO_ONLY"]
    try:
        # Account 6207 only. No changes to another customer's execution paths.
        # Requires the instrumented MT5 bridge with fresh native identity proof.
        if str(row[7]).endswith("6207"):
            verify_6207_audit_readiness(ea["files"],ea["nonce"],row[7],row[4])
            atomic_audit_client_context(folder,key,ea["nonce"],row[7],row[4],
                                        candidate["symbol"],candidate["side"])
        # A client OFF after research/ledger reservation must still deny SEND.
        # Old reserved UNKNOWN intents require reconciliation, never retry.
        require_fresh_customer_switch_on(cid,owner)
        atomic_native_request(folder / REQUEST_NAME, lines)
    except Exception:
        # UNKNOWN stays UNKNOWN. Never try to submit the same key again.
        raise
    return "SUBMISSION_UNKNOWN_WAITING_FOR_NATIVE_BROKER_RECEIPT"


def demo_6207_dispatch_targets(plans: list[dict], target: str | None) -> list[dict]:
    """An account-scoped runner may dispatch ONLY the selected Deriv DEMO 6207.

    Never turn an unrelated account's future CRM ON into implicit dispatch here.
    """
    if target is None:
        return plans
    if target != "d6fc2524ec373b8d1bc278a8be3ec635":
        raise Refused("TARGET_CONNECTION_NOT_DEMO_6207")
    matched = [p for p in plans if (p.get("connection_id")==target and
              p.get("broker")=="Deriv" and p.get("environment")=="DEMO")]
    if len(matched)!=1:
        raise Refused("EXACT_DEMO_6207_ACCOUNT_NOT_FOUND")
    return matched


def main() -> None:
    ap = argparse.ArgumentParser(description="APEX native DEMO order dispatcher")
    ap.add_argument("--status", action="store_true", help="Read-only account status")
    ap.add_argument("--dispatch", action="store_true", help="Place authorized native DEMO requests")
    ap.add_argument("--only-demo-connection", help="Scope native SEND to exact Deriv DEMO 6207")
    ap.add_argument("--reconcile", action="store_true", help="Reconcile native receipts against broker feed")
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("ROOT_REQUIRED")
    if sum((args.status, args.dispatch, args.reconcile)) > 1:
        ap.error("Choose one mode")
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = os.open(ROOT / "execution-writer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for key, outcome in reconcile():
            print("RECONCILE", key, outcome, flush=True)
        plans = router.report("dispatch" if args.dispatch else "inspect")
        if args.status or not args.dispatch:
            print("INSPECTION_ONLY")
            return
        for plan in demo_6207_dispatch_targets(plans,args.only_demo_connection):
            if plan.get("execution_authorized"):
                try:
                    outcome = send_once(plan)
                    print("NATIVE_ORDER_INTENT", plan["connection_id"][:8], outcome, flush=True)
                except (Refused, ledger.Blocked, OSError, ValueError, sqlite3.Error) as exc:
                    print("ORDER_DENIED", plan["connection_id"][:8], str(exc)[:110], flush=True)
    finally:
        os.close(lock)


if __name__ == "__main__":
    main()
