#!/usr/bin/python3
"""FP DEMO 1622: read-only broker exposure and immutable receipt audit.
NEVER creates order requests, authorizes trading, or infers fills from signals.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import sqlite3
import tempfile
import time
import sys
sys.path.insert(0,"/opt/apex-client-mt5") # shared pure native risk validator
sys.path.insert(0,"/opt/apex-client-mt5/fpmarkets-execution")
V113_SHA="76f3503c1661642438e690239d667758f0211fe4790623541345051f0a728a1c"

CID="14eef404262094655b2040c8ced86a53"
FP0512_CID="35b81a287b6a030f2f46ff426b135e6c"
def adaptive_on():
    flag=pathlib.Path('/etc/abutron/optionc-fp1622-demo-v2.json')
    if not flag.is_file() or flag.is_symlink():return False
    try:
        d=json.loads(flag.read_text())
        return (d.get('schema')=='abutron.optionc.activation.v2' and
                d.get('demo_only') is True and d.get('fpmarkets_enabled') is True and
                d.get('fp_enabled') is False and
                d.get('fpmarkets_connection_allowlist')==[CID] and
                d.get('risk_budget_pct_per_trade')==0.1 and
                d.get('portfolio_ceiling_pct')==20)
    except (OSError,ValueError,TypeError):return False

DB=pathlib.Path("/var/lib/apex-signup/accounts.sqlite3")
WORKER=pathlib.Path("/var/lib/private/abutron-client-mt5-"+CID)
HISTORY=pathlib.Path("/var/lib/apex/operator-live/fp-native-history-account-14eef404262094655b2040c8ced86a53.json")
OUTPUT=pathlib.Path("/var/lib/abutron-fp-execution/1622/reconciliation")
HEX32=re.compile(r"^[a-f0-9]{32}$")
HEX64=re.compile(r"^[a-f0-9]{64}$")

def read_json(p,max_size=300000):
    if p.is_symlink() or not p.is_file() or p.stat().st_size>max_size:
        raise ValueError("UNTRUSTED_INPUT")
    return json.loads(p.read_text(encoding="utf-8"))

def age(iso,now):
    try:
        return now-dt.datetime.fromisoformat(iso.replace("Z","+00:00")).timestamp()
    except (ValueError,TypeError,AttributeError):
        return float("inf")

def native_bridge(files,nonce,login,server,now):
    p=files/("ABUTRON_FP_BRIDGE_READY_V3_"+nonce+".txt")
    if p.is_symlink() or not p.is_file() or not 0<=now-p.stat().st_mtime<=18:
        raise ValueError("FP_BRIDGE_V3_PROOF_STALE")
    if p.stat().st_size>500:raise ValueError("FP_BRIDGE_PROOF_TOO_LARGE")
    raw=p.read_text(encoding="utf-8-sig").splitlines()
    if len(raw)!=11 or raw[:5]!=["FP_NATIVE_BRIDGE_READY_V3",nonce,login,server,"FP_DEMO"]:
        raise ValueError("FP_BRIDGE_ACCOUNT_PROOF_MISMATCH")
    clock,pending,positions,terminal,broker,enabled=map(int,raw[5:])
    if (abs(now-clock)>25 or not 0<=pending<=300 or not 0<=positions<=300
        or any(x not in (0,1) for x in (terminal,broker,enabled))):
        raise ValueError("FP_BRIDGE_PROOF_INVALID")
    return {"pending":pending,"positions":positions,"terminal_allowed":bool(terminal),
            "broker_allowed":bool(broker),"input_enabled":bool(enabled),
            "proof_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}

def receipt_audit(files,nonce,login,server):
    folder=files/"ABUTRON_FP"/"receipts"
    if not folder.is_dir() or folder.is_symlink():
        return {"total":0,"ACK":0,"BLOCKED":0,"UNKNOWN":0,"errors":[]}
    results={"total":0,"ACK":0,"BLOCKED":0,"UNKNOWN":0,"errors":[]}
    paths=list(folder.glob("*.txt"))
    if len(paths)>250:
        results["errors"].append("TOO_MANY_NATIVE_RECEIPTS")
        return results
    for path in paths:
        if (path.is_symlink() or not HEX64.fullmatch(path.stem)
            or not path.is_file() or path.stat().st_size>2048):
            results["errors"].append("INVALID_NATIVE_RECEIPT_FILE")
            continue
        lines=path.read_text(encoding="utf-8-sig").splitlines()
        if (len(lines)!=10 or lines[0]!="APEX_FP_NATIVE_V1"
            or lines[1]!=path.stem or lines[2] not in ("ACK","BLOCKED","UNKNOWN")
            or lines[7:]!=[nonce,login,server]):
            results["errors"].append("NATIVE_RECEIPT_ACCOUNT_OR_SCHEMA_MISMATCH")
            continue
        try:
            order_id,deal_id,stamp=map(int,(lines[4],lines[5],lines[6]))
            if min(order_id,deal_id,stamp)<0:raise ValueError()
        except ValueError:
            results["errors"].append("NATIVE_RECEIPT_VALUES_INVALID")
            continue
        results["total"]+=1
        results[lines[2]]+=1
    return results


def verify_broker_acks(files,nonce,login,server,history):
    """Broker-native independent proof for every ACK. Never authorizes an order."""
    folder=files/"ABUTRON_FP"/"receipts"
    verified=0
    proven_open_risk={}
    deals=history.get("trade_deals",[])
    positions=history.get("positions",[])
    if not isinstance(deals,list) or not isinstance(positions,list):
        return 0,False,{}
    for rp in sorted(folder.glob("*.txt")):
        if rp.is_symlink() or not rp.is_file() or rp.stat().st_size>2048:
            return verified,False,{}
        receipt=rp.read_text(encoding="utf-8-sig").splitlines()
        if len(receipt)!=10 or receipt[2]!="ACK":
            continue
        if (receipt[:2]!=["APEX_FP_NATIVE_V1",rp.stem]
          or receipt[7:]!=[nonce,login,server]):
            return verified,False,{}
        ep=files/"ABUTRON_FP"/"evidence"/(rp.stem+".txt")
        if ep.is_symlink() or not ep.is_file() or ep.stat().st_size>4096:
            return verified,False,{}
        ev=ep.read_text(encoding="utf-8-sig").splitlines()
        if (len(ev)!=19 or ev[:5]!=["APEX_FP_BROKER_POSITION_V1",rp.stem,nonce,login,server]
          or ev[7:9]!=receipt[4:6]):
            return verified,False,{}
        symbol,side,state=ev[5],ev[6],ev[16]
        # The EA's historical label can be stale when actual broker SL/TP
        # is intact and gross risk remains below the owner's 0.10% ceiling.
        # Independently verify the exact native risk intent and broker fields.
        if side not in ("BUY","SELL") or state not in ("OPEN_PROTECTED","OPEN_UNPROTECTED","CLOSED_BROKER_VERIFIED"):
            return verified,False,{}
        try:
            order,deal,position_id=map(int,[receipt[4],receipt[5],ev[9]])
            volume,entry,stop,take,risk,reward=map(float,ev[10:16])
            exit_id=int(ev[18])
            assert min(order,deal,position_id)>0
            assert all(math.isfinite(x) for x in [volume,entry,stop,take,risk,reward])
            if state in ("OPEN_PROTECTED","OPEN_UNPROTECTED"):
                # Never weaken cash, stop or volume proofs for a position that is still open.
                assert volume>0 and entry>0 and stop>0 and take>0 and exit_id==0
                legacy=(abs(risk-50)<=2 and abs(reward-100)<=2)
                if not legacy:
                    # V2 positions require a nonce-bound native MT5 risk
                    # intent written before OrderSend, and real broker
                    # history+open position. No synthetic broker evidence.
                    from optionc_native_v2_intent_contract import (
                        parse_native_intent,native_position_risk,ContractViolation)
                    intent_path=files/"ABUTRON_FP"/"optionc_v2"/(rp.stem+".txt")
                    intent=parse_native_intent(intent_path,rp.stem,nonce,login,server,
                                               symbol,side)
                    try:
                        native_position_risk(
                            intent,broker_position_volume=volume,
                            broker_entry=entry,broker_stop=stop,
                            broker_target=take,broker_cash_loss=risk,
                            broker_cash_reward=reward)
                    except ContractViolation as exc:
                        if str(exc)!="BROKER_OPEN_STOP_OVER_APPROVED_BUDGET":
                            raise
                        # Do not relabel broker SL/TP from the EA. Verify actual
                        # broker risk against the owner's 0.10%-at-entry limit,
                        # preserving the original smaller intent budget on disk.
                        from decimal import Decimal
                        account_policy=dict(intent)
                        account_policy['entry_budget']=intent['equity_at_entry']*Decimal('0.001')
                        native_position_risk(
                            account_policy,broker_position_volume=volume,
                            broker_entry=entry,broker_stop=stop,
                            broker_target=take,broker_cash_loss=risk,
                            broker_cash_reward=reward)

            else:
                # The native EA resets numeric position fields when a broker position
                # closes. A closed deal has NO open cash risk to calculate; require
                # all six erased fields and an independently matched broker exit.
                assert exit_id>0
                assert all(abs(x)<=1e-9 for x in (volume,entry,stop,take,risk,reward))
        except (ValueError,AssertionError,OSError):
            return verified,False,{}
        entries=[x for x in deals if isinstance(x,dict)
                 and str(x.get("ticket"))==str(deal)
                 and str(x.get("order_id"))==str(order)
                 and str(x.get("position_id"))==str(position_id)
                 and x.get("symbol")==symbol and x.get("side")==side
                 and x.get("entry")=="IN"
                 and (state=="CLOSED_BROKER_VERIFIED" or
                      abs(float(x.get("volume",0))-volume)<1e-7)]
        if len(entries)!=1:
            return verified,False,{}
        active=[p for p in positions if isinstance(p,dict)
                and str(p.get("ticket"))==str(position_id)]
        if state in ("OPEN_PROTECTED","OPEN_UNPROTECTED"):
            if len(active)!=1 or exit_id!=0:
                return verified,False,{}
            p=active[0]
            if (p.get("symbol")!=symbol or p.get("side")!=side
              or abs(float(p.get("volume",0))-volume)>1e-7
              or abs(float(p.get("stop_loss") or 0)-stop)>0.0001
              or abs(float(p.get("take_profit") or 0)-take)>0.0001
              or not ((stop<take and entry<take) if side=="BUY" else (take<stop and take<entry))):
                return verified,False,{}
            if str(position_id) in proven_open_risk:
                return verified,False,{}
            proven_open_risk[str(position_id)]=risk
        else:
            if active or exit_id<=0:
                return verified,False,{}
            exits=[x for x in deals if isinstance(x,dict)
                   and str(x.get("ticket"))==str(exit_id)
                   and str(x.get("position_id"))==str(position_id)
                   and x.get("entry") in ("OUT","OUT_BY")]
            if len(exits)!=1:
                return verified,False,{}
            # Validate complete broker-side closure independently of erased
            # native EA numeric fields. Partial closes retain exposure and
            # must never be mistaken for full closure.
            original_volume=float(entries[0].get("volume",0))
            all_exit_deals=[x for x in deals if isinstance(x,dict)
                            and str(x.get("position_id"))==str(position_id)
                            and x.get("entry") in ("OUT","OUT_BY")]
            exit_volume=sum(float(x.get("volume",0)) for x in all_exit_deals)
            if (not math.isfinite(original_volume) or original_volume<=0
              or not math.isfinite(exit_volume)
              or abs(exit_volume-original_volume)>1e-7
              or exits[0].get("side")==side):
                return verified,False,{}
        verified+=1
    # APEX receipts must all match broker-native orders and current positions.
    # Positions without APEX receipts remain broker-origin/unattributed:
    # they are NOT new APEX fills, and their risk is independently proven below.
    open_ids=[str(v.get("ticket")) for v in positions if isinstance(v,dict)]
    if len(open_ids)!=len(positions) or not set(proven_open_risk).issubset(set(open_ids)):
        return verified,False,{}
    return verified,True,proven_open_risk


def broker_native_open_stop_risk(files,nonce,login,server,history,now):
    """MT5 OrderCalcProfit exposure, independent of APEX order provenance."""
    path=files/("ABUTRON_FP_POSITION_STOP_RISK_V1_"+nonce+".txt")
    if path.is_symlink() or not path.is_file() or path.stat().st_size>100000:
        raise ValueError("NATIVE_BROKER_ORDER_CALC_PROFIT_PROOF_ABSENT")
    if not -4<=now-path.stat().st_mtime<=125:
        raise ValueError("NATIVE_BROKER_ORDER_CALC_PROFIT_PROOF_STALE")
    lines=path.read_text(encoding="utf-8-sig").splitlines()
    positions=history.get("positions",[])
    pending=history.get("pending_orders_count")
    if (len(lines)!=len(positions)+10 or
        lines[:5]!=["ABUTRON_FP_POSITION_STOP_RISK_V1",
                    nonce,login,server,"USD"] or
        lines[-1]!="END\t"+str(len(positions))):
        raise ValueError("NATIVE_BROKER_STOP_RISK_PROOF_IDENTITY_OR_COUNT")
    ts,npos,npend=int(lines[5]),int(lines[6]),int(lines[7])
    eq=float(lines[8])
    if (abs(now-ts)>150 or npos!=len(positions) or npend!=pending
        or not math.isfinite(eq) or eq<=0 or
        abs(eq-float(history.get("equity_usd",0)))>500):
        raise ValueError("NATIVE_BROKER_STOP_RISK_EQUITY_OR_SESSION_DIVERGENCE")
    brokers={str(x.get("ticket")):x for x in positions if isinstance(x,dict)}
    if len(brokers)!=npos:
        raise ValueError("NATIVE_BROKER_OPEN_POSITION_ID_DUPLICATE")
    risks={}
    for raw in lines[9:-1]:
        f=raw.split("\t")
        if len(f)!=11 or f[0]!="P" or f[1] not in brokers or f[1] in risks:
            raise ValueError("NATIVE_BROKER_POSITION_RISK_ROW_INVALID")
        pos=brokers[f[1]]
        ticket,symbol,side=f[1:4]
        vol,entry,sl,tp,risk,reward,mark=map(float,f[4:])
        numbers=(vol,entry,sl,tp,risk,reward,mark)
        if ((not all(math.isfinite(n) and n>0 for n in (vol,entry,sl,tp,reward,mark))
             or not math.isfinite(risk) or risk<0) or
            symbol!=pos.get("symbol") or side!=pos.get("side") or
            not ((sl<tp and entry<tp) if side=="BUY" else (tp<sl and tp<entry)) or
            abs(float(pos.get("volume",0))-vol)>1e-6 or
            abs(float(pos.get("open_price",0))-entry)>1e-5 or
            abs(float(pos.get("stop_loss",0))-sl)>1e-5 or
            abs(float(pos.get("take_profit",0))-tp)>1e-5):
            raise ValueError("NATIVE_BROKER_STOP_RISK_DIFFERENT_FROM_POSITION")
        risks[ticket]=risk
    if set(risks)!=set(brokers):
        raise ValueError("NATIVE_BROKER_OPEN_STOP_RISK_NOT_EXHAUSTIVE")
    return risks,ts

def evaluate(now=None):
    now=time.time() if now is None else now
    errors=[]
    adaptive=adaptive_on()
    def require(ok,reason):
        if not ok:errors.append(reason)
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=7) as c:
        c.execute("PRAGMA query_only=ON")
        rows=c.execute("""SELECT x.broker,x.environment,x.broker_server,x.status,
                    x.account_reference,COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
                    FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON x.id=t.connection_id
                    WHERE x.id=?""",(CID,)).fetchall()
    require(len(rows)==1,"FP_DEMO_ACCOUNT_NOT_UNIQUE")
    if len(rows)!=1:raise ValueError("FP_ACCOUNT_MISSING")
    broker,mode,server,status,login,desired,effective=rows[0]
    require((broker,mode,server,status)==("FP Markets","DEMO","FPMarketsSC-Demo","CONNECTED"),
            "FP_DEMO_ACCOUNT_NOT_CONNECTED")
    require(desired in (0,1) and effective in (0,1),"FP_ACCOUNT_TRADING_FLAGS_INVALID")
    w=read_json(WORKER/"worker-health.json",30000)
    nonce=w.get("nonce")
    require(w.get("status")=="CONNECTED" and w.get("heartbeat_fresh") is True and
            w.get("id")==CID and w.get("broker")=="FP Markets" and
            w.get("mode")=="DEMO" and w.get("server")==server and
            isinstance(nonce,str) and HEX32.fullmatch(nonce) is not None,
            "FP_WORKER_SESSION_NOT_VERIFIED")
    if not isinstance(nonce,str) or not HEX32.fullmatch(nonce):
        raise ValueError("FP_WORKER_NONCE_INVALID")
    h=read_json(HISTORY,300000)
    require(h.get("schema")=="abutron.fpmarkets.native.account_history.readonly.v1" and
            h.get("available") is True and h.get("history_verified_from_mt5") is True and
            h.get("broker")=="FP Markets" and h.get("environment")=="DEMO" and
            h.get("account_masked")=="••••"+login[-4:] and
            h.get("account_currency")=="USD" and
            h.get("history_complete_within_selected_window") is True and
            h.get("history_window_days")==90 and
            h.get("orders_submitted_by_exporter")==0 and h.get("execution_enabled") is False and
            -20<=age(h.get("generated_at_utc"),now)<=150 and
            -20<=age(h.get("broker_export_at_utc"),now)<=150,
            "FP_BROKER_NATIVE_HISTORY_STALE_OR_INVALID")
    pos=h.get("open_positions_count");pend=h.get("pending_orders_count")
    deal=h.get("trade_deals_count");equity=h.get("equity_usd")
    require(all(type(x) is int and x>=0 for x in (pos,pend,deal)),
            "FP_BROKER_EXPOSURE_COUNTS_INVALID")
    require(type(equity) in (int,float) and math.isfinite(equity) and equity>0,
            "FP_ACCOUNT_EQUITY_INVALID")
    require(isinstance(h.get("positions"),list) and len(h["positions"])==pos and
            isinstance(h.get("pending_orders"),list) and len(h["pending_orders"])==pend and
            isinstance(h.get("trade_deals"),list) and
            len(h["trade_deals"])==h.get("history_trade_deals_shown"),
            "FP_BROKER_HISTORY_ITEM_COUNT_MISMATCH")
    require(pend==0,"FP_BROKER_PENDING_ORDERS_NOT_ZERO")
    # Every open position needs broker-native SL/TP; USD risk is otherwise unverified.
    require(pos==0 or all(isinstance(p,dict) and p.get("stop_loss") and
            p.get("take_profit") for p in h.get("positions",[])),
            "FP_OPEN_POSITION_PROTECTION_UNVERIFIED")
    files=WORKER/"terminal/MQL5/Files"
    bridge=native_bridge(files,nonce,login,server,now)
    if adaptive:
        compiled=WORKER/"terminal/MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5"
        require(compiled.is_file() and not compiled.is_symlink() and
                hashlib.sha256(compiled.read_bytes()).hexdigest()==V113_SHA,
                "FP_ADAPTIVE_NATIVE_EXPERT_BINARY_MISMATCH")
        marker=files/("ABUTRON_OPTIONC_FP_CAPABILITY_V2_"+nonce+".txt")
        ok=(marker.is_file() and not marker.is_symlink() and
            -10<=now-marker.stat().st_mtime<=17)
        if ok:
            lines=marker.read_text(encoding="utf-8-sig").splitlines()
            ok=(len(lines)==9 and lines[:5]==[
              "APEX_OPTIONC_ADAPTIVE_CAPABILITY_V2",nonce,login,server,"FP"] and
              lines[6:]==["1","0.10","20"] and abs(now-int(lines[5]))<=26)
        require(ok,"FP_ADAPTIVE_NATIVE_RISK_CAPABILITY_NOT_VERIFIED")
    require(bridge["pending"]==pend and bridge["positions"]==pos,
            "FP_BRIDGE_BROKER_EXPOSURE_MISMATCH")
    receipts=receipt_audit(files,nonce,login,server)
    require(not receipts["errors"],"FP_NATIVE_RECEIPTS_INVALID")
    require(receipts["UNKNOWN"]==0,
            "FP_NATIVE_UNKNOWN_RECEIPT_REQUIRES_MANUAL_RECONCILIATION")
    verified_acks,acks_match,apex_open_risk=verify_broker_acks(files,nonce,login,server,h)
    require(acks_match and verified_acks==receipts["ACK"],
            "FP_NATIVE_ACK_BROKER_POSITION_RECONCILIATION_FAILED")
    try:
        open_risk,native_risk_ts=broker_native_open_stop_risk(
            files,nonce,login,server,h,now)
        native_risk_valid=True
    except (OSError,ValueError,KeyError,TypeError) as err:
        open_risk={};native_risk_ts=None;native_risk_valid=False
        require(False,"FP_BROKER_NATIVE_ORDER_CALC_PROFIT_PROOF_UNAVAILABLE")
    # APEX receipts, where present, must agree with the independent native
    # position calculation; a broker-origin deal never becomes an APEX ACK.
    if native_risk_valid:
        require(all(t in open_risk and abs(open_risk[t]-risk)<=0.05
                    for t,risk in apex_open_risk.items()),
                "FP_APEX_RECEIPT_RISK_NOT_MATCHED_TO_BROKER_NATIVE")
    # Position fingerprint excludes floating P/L and quote price; only the
    # actual broker exposure identity, size and protective stops are bound.
    exposure_rows=[{
        "ticket":str(p.get("ticket")),"symbol":p.get("symbol"),
        "side":p.get("side"),"volume":p.get("volume"),
        "stop_loss":p.get("stop_loss"),"take_profit":p.get("take_profit")}
        for p in h.get("positions",[]) if isinstance(p,dict)]
    exposure_sha256=hashlib.sha256(json.dumps(
        sorted(exposure_rows,key=lambda x:x["ticket"]),sort_keys=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()
    proven_risk_usd=round(sum(open_risk.values()),3)
    require(native_risk_valid and len(open_risk)==pos and proven_risk_usd>=0,
            "FP_OPEN_POSITION_USD_RISK_UNVERIFIED")
    exposure_verified=bool(native_risk_valid and len(open_risk)==pos and
                           acks_match and verified_acks==receipts["ACK"] and
                           receipts["UNKNOWN"]==0 and not receipts["errors"] and
                           bridge["pending"]==pend and bridge["positions"]==pos and
                           pend==0 and proven_risk_usd<=equity*0.20)
    hash_value=h.get("native_file_sha256")
    require(isinstance(hash_value,str) and HEX64.fullmatch(hash_value) is not None,
            "FP_NATIVE_HISTORY_HASH_INVALID")
    return {"schema":"abutron.fpmarkets.execution.native_reconciliation.readonly.v1",
            "generated_at_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
            "broker":"FP Markets","environment":"DEMO","account_masked":"••••"+login[-4:],
            "status":"RECONCILED_READONLY" if not errors else "BLOCKED",
            "broker_history_verified":bool(h.get("history_verified_from_mt5")),
            "broker_open_positions":pos,"broker_pending_orders":pend,
            "broker_trade_deals_90d":deal,"broker_equity_usd":equity,
            "bridge_proof_matches_broker":bridge["pending"]==pend and bridge["positions"]==pos,
            "bridge_input_enabled":bridge["input_enabled"],
            "history_sha256":hash_value,"bridge_proof_sha256":bridge["proof_sha256"],
            "receipt_counts":receipts,"broker_verified_ack_count":verified_acks,
            "verified_open_positions":len(open_risk),
            "verified_open_gross_stop_risk_usd":proven_risk_usd,
            "native_broker_open_risk_verified":native_risk_valid,
            "native_broker_open_risk_method":"MT5_ORDER_CALC_PROFIT_ENTRY_TO_STOP",
            "native_broker_open_risk_sample_utc":native_risk_ts,
            "apex_open_position_ids":sorted(apex_open_risk),
            "broker_origin_unattributed_position_ids":sorted(
                set(open_risk)-set(apex_open_risk)),
            "broker_exposure_sha256":exposure_sha256,
            "blockers":errors,
            "portfolio_ceiling_pct":20,
            "gross_sl_tp_usd":None if adaptive else [50,100],
            "native_risk_model":"OPTION_C_ADAPTIVE_V2" if adaptive else "LEGACY_FIXED_USD",
            # Broker-origin exposure is real even if this FP account's own
            # adaptive EA has not issued the separate execution approval.
            "portfolio_risk_for_new_entries_verified":exposure_verified,
            "automatic_order_execution_authorized":False,"orders_submitted":0}


# Native V101 history, bridge V3 and broker-native stop-risk files are emitted
# on independent MT5 events. A single read may capture two real but different
# position generations while a fill or close is being reconciled. Wait for
# an actual coherent broker-native snapshot; never declare a mismatch verified.
TRANSIENT_NATIVE_SNAPSHOT_BLOCKERS=frozenset((
    "FP_BRIDGE_BROKER_EXPOSURE_MISMATCH",
    "FP_NATIVE_ACK_BROKER_POSITION_RECONCILIATION_FAILED",
    "FP_BROKER_NATIVE_ORDER_CALC_PROFIT_PROOF_UNAVAILABLE",
    "FP_OPEN_POSITION_USD_RISK_UNVERIFIED",
    "FP_APEX_RECEIPT_RISK_NOT_MATCHED_TO_BROKER_NATIVE",
    "FP_BROKER_NATIVE_HISTORY_STALE_OR_INVALID",
    # V113 marker is rewritten on native MT5 2-second timer, and may briefly
    # report 0 while broker heartbeat is revalidating. Do not accept 0;
    # revalidate every source from scratch and require actual restored 1.
    "FP_ADAPTIVE_NATIVE_RISK_CAPABILITY_NOT_VERIFIED",
))
def evaluate_coherent_native_snapshot(evaluator=evaluate,delay=time.sleep):
    """Bounded source-retry, with full native validation every attempt.

    No fallback to prior success, synthetic evidence, updated timestamps,
    or new trading authority. An unresolved or nontransient error stays BLOCKED.
    """
    latest=evaluator()
    for attempt in range(12):
        if latest.get("status")=="RECONCILED_READONLY":
            return latest
        blockers=latest.get("blockers",[])
        if (not blockers or any(b not in TRANSIENT_NATIVE_SNAPSHOT_BLOCKERS
                                for b in blockers)):
            return latest
        delay(1.0)
        latest=evaluator()
    return latest


def publish(doc):
    OUTPUT.mkdir(mode=0o700,parents=True,exist_ok=True)
    stamp=doc["history_sha256"] if isinstance(doc.get("history_sha256"),str) else None
    db=OUTPUT/"broker-audit.sqlite3"
    with sqlite3.connect(str(db),timeout=7) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS broker_snapshots (
            history_sha256 TEXT PRIMARY KEY, observed_at_utc TEXT NOT NULL,
            broker_equity_usd REAL NOT NULL, open_positions INTEGER NOT NULL,
            pending_orders INTEGER NOT NULL, trade_deals_90d INTEGER NOT NULL,
            bridge_proof_sha256 TEXT NOT NULL)""")
        if doc["status"]=="RECONCILED_READONLY" and stamp and HEX64.fullmatch(stamp):
            c.execute("""INSERT OR IGNORE INTO broker_snapshots VALUES (?,?,?,?,?,?,?)""",
                      (stamp,doc["generated_at_utc"],doc["broker_equity_usd"],
                       doc["broker_open_positions"],doc["broker_pending_orders"],
                       doc["broker_trade_deals_90d"],doc["bridge_proof_sha256"]))
        c.commit()
    fd,tmp=tempfile.mkstemp(dir=OUTPUT,prefix=".fp-reconciliation-")
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(doc,f,sort_keys=True,separators=(",",":"),allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600)
        os.replace(tmp,OUTPUT/"latest.json")
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return {"status":doc.get("status","BLOCKED"),
            "broker_open_positions":doc.get("broker_open_positions"),
            "broker_pending_orders":doc.get("broker_pending_orders"),
            "bridge_matches_broker":doc.get("bridge_proof_matches_broker",False),
            "blockers":doc.get("blockers",[]),
            "automatic_order_execution_authorized":False,
            "orders_submitted":0}

if __name__=="__main__":
    try:
        report=evaluate_coherent_native_snapshot()
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,UnicodeError) as err:
        code=str(err)
        safe_code=code if re.fullmatch(r"[A-Z][A-Z0-9_]{4,89}",code) else type(err).__name__
        report={"schema":"abutron.fpmarkets.execution.native_reconciliation.readonly.v1",
                "generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                "status":"BLOCKED","blockers":["FP_RECONCILIATION_SOURCE_"+safe_code],
                "broker_open_positions":None,"broker_pending_orders":None,
                "bridge_proof_matches_broker":False,
                "automatic_order_execution_authorized":False,"orders_submitted":0,
                "history_sha256":None}
    print(json.dumps(publish(report),sort_keys=True))
