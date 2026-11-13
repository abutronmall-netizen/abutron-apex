#!/usr/bin/python3
"""ABUTRON APEX unified decision evidence: read-only bridge across broker engines.

No order endpoints, outbound I/O, account control mutations, or model calls.
Production's FP/Deriv native execution authorities remain independent.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import importlib.util
import json
import os
import sqlite3
import stat
import tempfile
import time
from pathlib import Path

ROOT=Path("/var/lib/abutron-unified-decision")
FP_SCAN=Path("/var/lib/abutron-fp-scanner/partial-latest.json")
FP_AI=Path("/var/lib/abutron-fp-scanner/ai/latest.json")
FP_RECON=Path("/var/lib/abutron-fp-execution/reconciliation/latest.json")
FP_ACT=Path("/var/lib/abutron-fp-execution/activation/latest.json")
FP_ROUTER=Path("/var/lib/abutron-fp-execution/order-router/latest.json")
FP_ORDER_SOURCE=Path("/opt/apex-client-mt5/fpmarkets-execution/fp_signal_order_router_v1.py")
DERIV_ROUTER=Path("/var/lib/apex-client-feed/execution-router/summary.json")
DERIV_NATIVE=Path("/var/lib/apex/operator-live/native-status.json")
DERIV_SCANNER=Path("/var/lib/apex/operator-live/native-scanner.json")
BROKER_DB=Path("/var/lib/apex-signup/accounts.sqlite3")
SCHEMA="abutron.apex.unified.readonly.v1"
MAX_FILE_BYTES=5_000_000
RISK_SL_USD=50
REWARD_TP_USD=100
PORTFOLIO_CAP_PERCENT=20

def read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("SYMLINK_UNTRUSTED_"+path.name)
    statobj=path.stat()
    if not stat.S_ISREG(statobj.st_mode) or statobj.st_size > MAX_FILE_BYTES or statobj.st_size < 2:
        raise ValueError("INVALID_EVIDENCE_FILE_"+path.name)
    result=json.loads(path.read_text())
    if not isinstance(result,dict):
        raise ValueError("INVALID_EVIDENCE_SCHEMA_"+path.name)
    return result

def timestamp(value) -> float:
    t=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("MISSING_TIMEZONE")
    return t.timestamp()

def fresh(value, now:float, seconds:int=150)->bool:
    try:
        age=now-timestamp(value)
        return -15<=age<=seconds
    except (TypeError,ValueError,OverflowError):
        return False

def digest_calculator():
    spec=importlib.util.spec_from_file_location("abutron_fp_native_router_hash_only",str(FP_ORDER_SOURCE))
    if not spec or not spec.loader:
        raise ValueError("NATIVE_ROUTER_MODULE_MISSING")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module._ai_evidence_digest

def fp_judge(scan:dict,ai:dict,recon:dict,activation:dict,router:dict,now:float,calculate_digest)->dict:
    # Read-only diagnostic: broker router is the ONLY entry authority.
    if (scan.get("schema")!="abutron.fpmarkets.apex.scanner.partial.readonly.v1"
      or scan.get("status")!="FP_SCANNER_PARTIAL_READONLY"
      or scan.get("symbols")!=13
      or type(scan.get("symbols_verified")) is not int
      or not 0<=scan["symbols_verified"]<=13
      or scan.get("timeframe_series")!=scan["symbols_verified"]*6
      or not isinstance(scan.get("instruments"),list)
      or len(scan["instruments"])!=13
      or len({x.get("symbol") for x in scan["instruments"]})!=13
      or ai.get("schema")!="abutron.fpmarkets.apex.ai_selective_tradingagents.v1"
      or ai.get("execution_authorized") is not False):
        return {"status":"INPUT_INVALID_OR_INCOMPLETE","candidates":[],
                "stage_counts":{"INPUT_INVALID_OR_INCOMPLETE":13},"ready_count":0}
    scan_fresh=fresh(scan.get("checked_at_utc"),now,170)
    ai_fresh=fresh(ai.get("reviewed_at_utc"),now,460)
    recon_fresh=fresh(recon.get("generated_at_utc"),now,135)
    activation_fresh=fresh(activation.get("checked_at_utc"),now,135)
    adaptive=(recon.get("native_risk_model")=="OPTION_C_ADAPTIVE_V2")
    adaptive_risk=(adaptive and recon.get("gross_sl_tp_usd") is None
                   and router.get("risk_SL_usd") is None
                   and router.get("reward_TP_usd") is None
                   and recon.get("portfolio_risk_for_new_entries_verified") is True)
    legacy_risk=(not adaptive and recon.get("gross_sl_tp_usd")==[50,100]
                 and router.get("risk_SL_usd")==50 and router.get("reward_TP_usd")==100)
    risk_ok=(recon_fresh and recon.get("status")=="RECONCILED_READONLY"
             and recon.get("bridge_proof_matches_broker") is True
             and recon.get("broker_history_verified") is True
             and (adaptive_risk or legacy_risk)
             and recon.get("portfolio_ceiling_pct")==20
             and router.get("portfolio_cap_percent")==20)
    control_on=(activation_fresh and activation.get("effective_enabled") is True
                and activation.get("status")=="ON")
    reviews={x.get("symbol"):x for x in ai.get("reviews",[]) if isinstance(x,dict)}
    decisions=[];counts={}
    for row in scan["instruments"]:
        symbol=row.get("symbol");proposal=row.get("proposal")
        review=reviews.get(symbol,{})
        matched=False
        if (scan_fresh and ai_fresh and proposal in ("BUY","SELL")
          and row.get("candidate_for_ai") is True
          and review.get("m5_closed_bar")==row.get("m5_closed_bar")
          and review.get("scanner_proposal")==proposal
          and review.get("llm_direction")==proposal
          and review.get("evidence_status")=="MODEL_REVIEW_COMPLETED"
          and fresh(review.get("reviewed_at_utc"),now,440)):
            try:matched=(review.get("evidence_sha256")==calculate_digest(row))
            except (ValueError,TypeError,KeyError,OverflowError):matched=False
        if not scan_fresh:stage="STALE_SCANNER"
        elif row.get("available") is not True:stage="BROKER_DATA_UNAVAILABLE"
        elif proposal not in ("BUY","SELL"):
            detail=row.get("reason","")
            stage=(detail if isinstance(detail,str) and
                   detail.startswith("ENTRY_QUALITY_") and len(detail)<=95 and
                   detail.replace("_","").isalnum() and detail.upper()==detail
                   else "NO_QUANT_SIGNAL")
        elif not matched:stage="AI_PENDING_OR_DISAGREES"
        elif not risk_ok:stage="BROKER_RISK_NOT_VERIFIED"
        elif not control_on:stage="ACCOUNT_CONTROL_OFF"
        elif router.get("router_mode")!="ARMED":stage="NATIVE_ROUTER_DISARMED"
        else:stage="AI_POSITIVE_NATIVE_ROUTER_REVALIDATION"
        counts[stage]=counts.get(stage,0)+1
        decisions.append({"symbol":symbol,"quant":proposal,
                          "ai":review.get("llm_direction") if matched else "UNCONFIRMED",
                          "stage":stage,"decision":"HOLD",
                          "m5_closed_bar":row.get("m5_closed_bar"),
                          "native_order_authorized":False})
    # Monitor readiness must reflect the native router's current output, not
    # a synthetic approval by the UI.
    ready=(len(router.get("candidates",[]))
           if router.get("status")=="READY"
           and isinstance(router.get("candidates"),list)
           and fresh(router.get("checked_at_utc"),now,140) else 0)
    return {"status":("STALE_INPUT" if not (scan_fresh and ai_fresh)
                       else "PARTIAL_BROKER_COVERAGE" if scan.get("symbols_verified")<13
                       else "READY_FOR_MONITORING"),
            "schema":"abutron.apex.fp.unified.v1","broker":"FP Markets",
            "environment":"DEMO",
            "stages":{"broker_market_data":scan_fresh,
                      "quantitative_structure":scan_fresh,
                      "selective_tradingagents_ai":ai_fresh,
                      "broker_risk_reconciled":risk_ok,
                      "native_execution_control":control_on,
                      "native_router_armed":router.get("router_mode")=="ARMED"},
            "stage_counts":counts,"ready_count":ready,
            "symbols_available":scan.get("symbols_verified"),
            "symbols_total":13,
            "unavailable_symbols":[v.get("symbol") for v in scan["instruments"] if v.get("available") is not True
                and v.get("symbol") in ("XAUUSD","USOIL")],
            "effective_risk_model":recon.get("native_risk_model"),
            "fixed_usd_policy_active":not adaptive,
            "native_router_status":router.get("status"),
            "native_router_blockers":router.get("blockers",[]),
            "broker_verified_acks":recon.get("broker_verified_ack_count"),
            "broker_verified_positions":recon.get("verified_open_positions"),
            "verified_open_risk_usd":recon.get("verified_open_gross_stop_risk_usd"),
            "decisions":decisions,"native_orders_sent_by_unified_engine":0}

def deriv_signal_triage(now:float,db=BROKER_DB)->dict:
    """Live broker-exported Deriv scanner/inbox evidence; read-only diagnostics.

    Not a new authority. Do not interpret scanner approval or an unoccupied
    symbol as permission to trade. Native router alone authorizes orders.
    """
    import re
    with sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=8) as c:
        c.execute("PRAGMA query_only=ON")
        pairs=c.execute("""SELECT id,account_id FROM apex_mt5_connections
            WHERE broker='Deriv' AND environment='DEMO' AND status='CONNECTED'
            ORDER BY id""").fetchall()
    summaries=[];totals={}
    for cid,owner in pairs:
        if not isinstance(cid,str) or not re.fullmatch("[0-9a-f]{32}",cid):
            continue
        path=Path("/var/lib/apex-client-feed")
        row={"account_ref_suffix":cid[-5:],"broker_audit_fresh":False,
             "signals_in_scanner":0,"signals_in_inbox":0,
             "native_router_ready":0,"stage_counts":{},"signals":[]}
        def add(stage,sym=None,side=None,age=None):
            row["stage_counts"][stage]=row["stage_counts"].get(stage,0)+1
            totals[stage]=totals.get(stage,0)+1
            if sym is not None:
                row["signals"].append({"symbol":sym,"proposal":side,
                    "stage":stage,"bar_close_age_seconds":int(age) if age is not None else None})
        try:
            audit=read(path/(cid+".json"))
            if (audit.get("connection_id")!=cid or audit.get("account_id")!=owner
              or audit.get("status")!="BROKER_DATA_VERIFIED_SHADOW"
              or audit.get("broker_data_verified") is not True
              or audit.get("symbol_count")!=13 or audit.get("timeframes_per_symbol")!=6
              or not fresh(audit.get("checked_at_utc"),now,160)):
                add("AUDIT_INVALID_OR_STALE")
                summaries.append(row);continue
            preview=audit.get("signal_preview",[])
            account=audit.get("account",{})
            positions=account.get("positions")
            allowed=audit.get("approved_new_entry_symbols")
            allowed_set={"Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0"}
            if (not isinstance(allowed,list) or set(allowed)!=allowed_set
                or audit.get("approved_new_entry_symbol_count")!=3
                or not isinstance(preview,list) or len(preview)!=3
                or {v.get("symbol") for v in preview if isinstance(v,dict)}!=allowed_set
                or not isinstance(positions,list) or
                account.get("open_positions")!=len(positions) or
                account.get("all_positions_protected") is not True or
                not all(x.get("protected") is True for x in positions)):
                add("ACCOUNT_OR_SCANNER_EVIDENCE_INVALID")
                summaries.append(row);continue
            occupied={p.get("symbol") for p in positions}
            row["broker_audit_fresh"]=True
            row["m5_directional_symbols"]=sum(v.get("m5_signal") in ("BUY","SELL") for v in preview)
            row["approved_new_entry_symbols"]=sorted(allowed_set)
            row["scanner_rejection_counts"]=audit.get("scanner_rejection_counts",{})
            try:
                inbox=read(path/"inboxes"/(cid+".json"))
                inbox_ok=(inbox.get("connection_id")==cid and
                          inbox.get("account_id")==owner and
                          inbox.get("status")=="RESEARCH_PREVIEW" and
                          fresh(inbox.get("updated_at_utc"),now,140) and
                          isinstance(inbox.get("candidates"),list))
                inbox_set={(x.get("symbol"),x.get("side"),x.get("m5_bar_time"))
                           for x in inbox.get("candidates",[]) if isinstance(x,dict)} if inbox_ok else set()
            except (OSError,ValueError,TypeError,AttributeError,KeyError):
                inbox_ok=False;inbox_set=set()
            row["signals_in_inbox"]=len(inbox_set)
            try:
                native=read(path/"execution-router"/(cid+".json"))
                if fresh(native.get("checked_at_utc"),now,150):
                    row["native_router_ready"]=native.get("signals_ready",0)
                    row["native_router_blockers"]=native.get("blockers",[])
            except (OSError,ValueError,TypeError,KeyError):
                pass
            for signal in preview:
                sym=signal.get("symbol");side=signal.get("proposal")
                bar=signal.get("last_closed_m5")
                if side not in ("BUY","SELL"):
                    reason=signal.get("rejection_class","NO_QUALIFIED_SIGNAL")
                    add("SCANNER_HOLD_"+str(reason)[:64],sym,"HOLD");continue
                row["signals_in_scanner"]+=1
                age=now-(bar+300) if type(bar) is int else None
                if age is None or not -10<=age<=240:
                    add("CLOSED_CANDLE_EXPIRED_OR_INVALID",sym,side,age);continue
                if sym in occupied:
                    add("APPROVED_SYMBOL_ALREADY_OCCUPIED",sym,side,age);continue
                if not inbox_ok:
                    add("RESEARCH_INBOX_UNVERIFIED",sym,side,age);continue
                if (sym,side,bar) not in inbox_set:
                    add("APPROVED_UNOCCUPIED_MISSING_INBOX",sym,side,age);continue
                add("UNOCCUPIED_RESEARCH_INBOX_ONLY_NATIVE_PROOF_PENDING",sym,side,age)
        except (OSError,ValueError,TypeError,AttributeError,KeyError):
            add("AUDIT_READ_FAILED")
        summaries.append(row)
    return {"scope":"DIAGNOSTIC_ONLY_NOT_AN_ORDER_AUTHORITY",
            "accounts_checked":len(summaries),"stage_counts":totals,
            "accounts":summaries}

def connected_counts(db=BROKER_DB) -> dict:
    with sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=8) as c:
        c.execute("PRAGMA query_only=ON")
        rows=c.execute("""SELECT broker,environment,COUNT(*),SUM(COALESCE(t.effective_enabled,0))
            FROM apex_mt5_connections x
            LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
            WHERE x.status='CONNECTED' GROUP BY broker,environment""".replace("broker,environment","x.broker,x.environment")).fetchall()
    out={}
    for name,env,n,enabled in rows:
        if name in ("Deriv","FP Markets","IC Markets"):
            out.setdefault(name,{})[env]={"connected":n,"effective_on":enabled or 0}
    return out

def report(now:float|None=None) -> dict:
    now=time.time() if now is None else now
    data={key:read(path) for key,path in {
        "scan":FP_SCAN,"ai":FP_AI,"recon":FP_RECON,"activation":FP_ACT,"router":FP_ROUTER}.items()}
    fp=fp_judge(data["scan"],data["ai"],data["recon"],data["activation"],
                data["router"],now,digest_calculator())
    accounts=connected_counts()
    deriv_router=read(DERIV_ROUTER)
    deriv_native=read(DERIV_NATIVE)
    selected_scan=read(DERIV_SCANNER)
    source_ok=(selected_scan.get("schema")=="apex.scanner.shadow.v1"
      and selected_scan.get("source")=="Deriv DEMO MT5"
      and selected_scan.get("orders_enabled") is False
      and selected_scan.get("symbol_count")==13
      and fresh(selected_scan.get("generated_at_utc"),now,150)
      and isinstance(selected_scan.get("instruments"),list)
      and len(selected_scan["instruments"])==13)
    scanner_labels=[]
    if source_ok:
        for x in selected_scan["instruments"]:
            reason=x.get("reason","")
            label=("SCANNER_APPROVED" if x.get("proposal") in ("BUY","SELL")
                else "HIGHER_TIMEFRAME_CONFLICT" if "higher TF conflict" in reason or
                "conflicts with aligned" in reason
                else "RSI_ENTRY_FILTER" if "outside" in reason
                else "M5_MIXED" if reason.startswith("M5 mixed")
                else "CRASH_BOOM_SPIKE_MODEL_NOT_VALIDATED" if
                    "spike-model requires separate testing" in reason
                else "OTHER_SCANNER_HOLD")
            scanner_labels.append({"symbol":x.get("symbol"),"proposal":x.get("proposal"),
                                   "qualification":label,"reason":reason[:180]})
    deriv_fresh=fresh(deriv_router.get("checked_at_utc"),now,140)
    triage=deriv_signal_triage(now)
    deriv={"signal_triage":triage,
           "selected_operator_scanner":{"source":"SELECTED_OPERATOR_ACCOUNT_ONLY",
             "fresh":source_ok,"instruments":scanner_labels},
           "status":deriv_router.get("status","UNVERIFIED"),
           "environment":"DEMO","audit_fresh":deriv_fresh,
           "native_router_mode":deriv_router.get("mode"),
           "fresh_research_candidates":deriv_router.get("fresh_research_candidates",0),
           "accounts_dispatch_authorized":deriv_router.get("accounts_dispatch_authorized",0),
           "connected_native_bridges":deriv_native.get("bridges_ready",0)
                 if fresh(deriv_native.get("checked_at_utc"),now,140) else None,
           "positive_execution_proven":False,
           "native_orders_sent_by_unified_engine":0}
    ic={"status":"NOT_CONNECTED" if not accounts.get("IC Markets",{}).get("DEMO",{}).get("connected",0)
        else "CONNECTED_NEEDS_NATIVE_DECISION_EVIDENCE",
        "native_orders_sent_by_unified_engine":0}
    return {"schema":SCHEMA,"generated_at_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
            "architecture":["broker_market_data","quantitative_structural_engine",
                "selective_tradingagents_ai_confirmation","final_decision_and_broker_risk",
                "existing_native_mt5_execution"],
            "scope":"READ_ONLY_UNIFIED_DECISION_EVIDENCE_NO_NEW_ORDER_AUTHORITY",
            "broker_accounts":accounts,"brokers":{"FP Markets":fp,"Deriv":deriv,"IC Markets":ic},
            "risk_policy":{"gross_sl_usd":None if data["recon"].get("native_risk_model")=="OPTION_C_ADAPTIVE_V2" else RISK_SL_USD,
                           "gross_tp_usd":None if data["recon"].get("native_risk_model")=="OPTION_C_ADAPTIVE_V2" else REWARD_TP_USD,
                           "fp_effective_risk_model":data["recon"].get("native_risk_model"),
                           "fp_per_trade_equity_pct_max":0.1 if data["recon"].get("native_risk_model")=="OPTION_C_ADAPTIVE_V2" else None,
                           "deriv_effective_risk_model":"PER_ACCOUNT_MIXED_LEGACY_AND_ADAPTIVE",
                           "portfolio_ceiling_percent":PORTFOLIO_CAP_PERCENT},
            "execution_authority":False,"orders_sent":0}

def publish(doc:dict, path:Path=ROOT/"latest.json") -> None:
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    fd,tmp=tempfile.mkstemp(prefix=".unified-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(doc,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def publish_ui_health(doc:dict, path:Path=Path("/var/lib/abutron-unified-decision/ui-health.json")) -> None:
    """Sanitized cross-broker diagnostic: no account identifiers or order authority."""
    fp=doc.get("brokers",{}).get("FP Markets",{})
    dv=doc.get("brokers",{}).get("Deriv",{})
    tri=dv.get("signal_triage",{})
    accounts=doc.get("broker_accounts",{})
    ready={
        "schema":"abutron.apex.runtime_health.readonly.v1",
        "checked_at_utc":doc.get("generated_at_utc"),
        "environment":"DEMO",
        "execution_authority":False,
        "portfolio_ceiling_pct":20,
        "deriv":{
            "connected":accounts.get("Deriv",{}).get("DEMO",{}).get("connected",0),
            "account_controls_on":accounts.get("Deriv",{}).get("DEMO",{}).get("effective_on",0),
            "native_bridges_ready":dv.get("connected_native_bridges"),
            "scanner_status":dv.get("status","UNVERIFIED"),
            "audit_fresh":dv.get("audit_fresh") is True,
            "account_feed_verified":sum(1 for x in tri.get("accounts",[]) if x.get("broker_audit_fresh") is True),
            "qualified_candidates":sum(x.get("signals_in_scanner",0) for x in tri.get("accounts",[])),
            "m5_directional_symbols":max([x.get("m5_directional_symbols",0) for x in tri.get("accounts",[])],default=0),
            "native_router_ready":dv.get("accounts_dispatch_authorized",0),
            "signal_reasons":tri.get("stage_counts",{}),
            "new_entry_symbols":["Volatility 25 Index","Volatility 50 Index","Volatility 75 Index"],
            "adaptive_first_broker_ack_verified":None},
        "fpmarkets":{
            "connected":accounts.get("FP Markets",{}).get("DEMO",{}).get("connected",0),
            "account_controls_on":accounts.get("FP Markets",{}).get("DEMO",{}).get("effective_on",0),
            "status":fp.get("status","UNVERIFIED"),
            "symbols_verified":fp.get("symbols_available"),
            "symbols_total":fp.get("symbols_total",13),
            "unavailable_symbols":fp.get("unavailable_symbols",[]),
            "broker_verified_acks":fp.get("broker_verified_acks"),
            "broker_verified_positions":fp.get("broker_verified_positions"),
            "verified_open_risk_usd":fp.get("verified_open_risk_usd"),
            "risk_model":fp.get("effective_risk_model"),
            "per_trade_risk_pct_max":0.1 if fp.get("effective_risk_model")=="OPTION_C_ADAPTIVE_V2" else None,
            "broker_risk_reconciled":fp.get("stages",{}).get("broker_risk_reconciled") is True,
            "native_account_control_on":fp.get("stages",{}).get("native_execution_control") is True,
            "native_router_status":fp.get("native_router_status"),
            "blockers":fp.get("native_router_blockers",[]),
            "signal_reasons":fp.get("stage_counts",{}),
            "qualified_candidates":fp.get("ready_count",0)},
        "icmarkets":{"status":doc.get("brokers",{}).get("IC Markets",{}).get("status","UNVERIFIED")}
    }
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    path.parent.chmod(0o755)
    fd,tmp=tempfile.mkstemp(prefix=".ui-health-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(ready,f,separators=(",",":"),allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


if __name__=="__main__":
    doc=report()
    publish(doc)
    publish_ui_health(doc)
    fp=doc["brokers"]["FP Markets"]
    print(json.dumps({"schema":SCHEMA,"fp_stage_counts":fp.get("stage_counts"),
                      "fp_ready":fp.get("ready_count"),"deriv_audit_fresh":doc["brokers"]["Deriv"]["audit_fresh"],
                      "ic_markets":doc["brokers"]["IC Markets"]["status"],
                      "orders_submitted":0},separators=(",",":")))

