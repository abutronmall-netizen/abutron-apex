#!/usr/bin/python3
"""Reconcile FP 0512 and 1636 DEMO using actual native EA, receipt and history evidence.
Never sends orders or changes client controls.
"""
import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path
import runpy
import sqlite3
import sys

SOURCE = "/opt/apex-client-mt5/fpmarkets-execution/fp_native_reconcile_readonly.py"
CRM = "/var/lib/apex-signup/accounts.sqlite3"
SOURCE_SHA = "8393c120ecfd98f713b4c20c1854bef6aa260012f676e23e2f1ce417dd22ef1d"
ROUTER = Path("/opt/apex-client-mt5/fpmarkets-execution/fp_signal_order_router_v1.py")
ROUTER_SHA = "470deeef870ea023049d8f6632fb9403c630382ed6cf8c98d0e448d8ad13b606"
DEST = Path("/var/lib/abutron-fp-execution/dual-account-reconciliation")
ACCOUNTS = (
    ("35b81a287b6a030f2f46ff426b135e6c", "7410512",
     "f9f330bd9ca6d5619253200a2e4943d71dfb4515b350ed75912c699ddaf1184f",
     "/var/lib/apex/operator-live/fp-native-history.json", True),
    ("80cf848587fcec6311dd93560c1c46c6", "7411636",
     "f0edbc4fbeb792d970b4e661d7c9d399419bcddbf49b36d36f520fc33a859ed4",
     "/var/lib/apex/operator-live/fp-native-history-account-80cf848587fcec6311dd93560c1c46c6.json", False),
)

def account(cid, login, pin, history, adaptive, db):
    row = db.execute("""SELECT x.broker,x.environment,x.broker_server,
       x.status,x.account_reference,x.worker_binding,t.desired_enabled,t.effective_enabled
       FROM apex_mt5_connections x JOIN apex_trade_controls t
       ON t.connection_id=x.id WHERE x.id=?""", (cid,)).fetchone()
    if not row or row[:3] != ("FP Markets", "DEMO", "FPMarketsSC-Demo") or (
        row[4] != login or row[5] != "abutron-client-mt5-" + cid):
        raise ValueError("CRM_FP_ACCOUNT_IDENTITY_UNVERIFIED")
    worker = Path("/var/lib/private/abutron-client-mt5-" + cid)
    expert = worker / "terminal/MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5"
    if expert.is_symlink() or not expert.is_file() or (
        hashlib.sha256(expert.read_bytes()).hexdigest() != pin):
        raise ValueError("FP_NATIVE_ORDER_EA_IDENTITY_UNVERIFIED")
    # Pin evaluated source AND imported router before loading Python code.
    if (hashlib.sha256(Path(SOURCE).read_bytes()).hexdigest() != SOURCE_SHA or
        hashlib.sha256(ROUTER.read_bytes()).hexdigest() != ROUTER_SHA):
        raise ValueError("FP_RECONCILIATION_CODE_DRIFT")
    mod = runpy.run_path(SOURCE, run_name="_fp_native_reconciliation_only")
    fn = mod["evaluate"]
    g = fn.__globals__
    g["CID"] = cid
    g["WORKER"] = worker
    g["HISTORY"] = Path(history)
    if not adaptive:
        g["adaptive_on"] = lambda: False
    r = fn()
    receipts = r.get("receipt_counts", {})
    if (r.get("status") != "RECONCILED_READONLY" or
        r.get("broker") != "FP Markets" or r.get("environment") != "DEMO" or
        r.get("account_masked") != "••••" + login[-4:] or
        r.get("automatic_order_execution_authorized") is not False or
        receipts.get("UNKNOWN") != 0 or receipts.get("errors") or
        r.get("broker_verified_ack_count") != receipts.get("ACK")):
        # Preserve validated broker-native failure codes; never leak secrets.
        blockers=r.get("blockers",[])
        codes=[x for x in blockers if type(x) is str and
               re.fullmatch(r"[A-Z0-9_]{4,80}",x)]
        if codes:
            raise ValueError(codes[0])
        raise ValueError("FP_NATIVE_RECEIPTS_OR_RECONCILIATION_UNVERIFIED")
    return {"account_suffix": login[-4:], "connection_suffix": cid[-6:],
            "connected": row[3] == "CONNECTED", "desired_on": row[6] == 1,
            "effective_on": row[7] == 1, "equity_usd": r["broker_equity_usd"],
            "positions": r["broker_open_positions"], "pending": r["broker_pending_orders"],
            "historical_broker_ack": receipts["ACK"],
            "unresolved_receipts": receipts["UNKNOWN"],
            "historical_trade_deals": r["broker_trade_deals_90d"],
            "risk_model": r["native_risk_model"], "state": "RECONCILED_READONLY"}

def inspect():
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    with sqlite3.connect("file:" + CRM + "?mode=ro", uri=True, timeout=7) as db:
        db.execute("PRAGMA query_only=ON")
        data = []
        for cid, login, pin, history, adaptive in ACCOUNTS:
            # Native history and bridge files are published asynchronously.
            # Retry only a bounded number of READ-ONLY full attestations; never
            # reuse a prior ACK or stale report to override a genuine denial.
            last_code="UNVERIFIED"
            for attempt in range(3):
                try:
                    row=account(cid, login, pin, history, adaptive, db)
                    data.append(row)
                    break
                except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
                    # Safe opaque code only; never include MT5 credentials.
                    raw=str(exc)
                    last_code=(raw if re.fullmatch(r"[A-Z0-9_]{4,120}",raw)
                               else type(exc).__name__)
                    if attempt<2:
                        time.sleep((2,5)[attempt])
            else:
                data.append({"account_suffix": login[-4:],
                             "state": "BLOCKED",
                             "error_code": last_code,
                             "bounded_readonly_retries_exhausted":True})
    ok = all(x["state"] == "RECONCILED_READONLY" for x in data)
    return {"schema": "abutron.fpmarkets.dual_demo_native_reconciliation.readonly.v1",
            "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "state": "RECONCILED_READONLY" if ok else "BLOCKED",
            "accounts": data, "orders_submitted_by_job": 0,
            "broker_order_authorized": False, "client_switches_modified": False}

def main():
    result = inspect()
    if not DEST.is_dir() or DEST.is_symlink() or DEST.stat().st_uid != 0:
        raise RuntimeError("ROOT_OWNED_OUTPUT_DIRECTORY_REQUIRED")
    temp = DEST / (".latest-" + str(os.getpid()) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(result, f, sort_keys=True, separators=(",", ":"), allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, DEST / "latest.json")
    finally:
        temp.unlink(missing_ok=True)
    print(json.dumps({"state": result["state"], "accounts": result["accounts"],
                      "orders_submitted": 0}))
    return 0 if result["state"] == "RECONCILED_READONLY" else 1

if __name__ == "__main__":
    sys.exit(main())
