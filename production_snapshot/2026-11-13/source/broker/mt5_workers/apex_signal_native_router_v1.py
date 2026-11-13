#!/usr/bin/env python3
"""ABUTRONFX APEX signal-to-native MT5 dispatcher, Deriv DEMO only.

Uses validated per-tenant native-feed/research data. Fail-closed by default.
Writes an order command only when --dispatch AND all separate broker, risk,
license, per-owner authorization, pending-order, cutover and ledger gates pass.
No LIVE endpoint, credential use, order retry or mock broker acknowledgments.
"""
from __future__ import annotations
import argparse, datetime as dt, fcntl, hashlib, json, math, os, re, sqlite3, sys, tempfile, time
from pathlib import Path
sys.path[:0]=["/opt/apex-client-mt5","/opt/apex-client-portal","/opt/apex-signup"]
import manager, customer_order_ledger as ledger, apex_customer_worker_entitlement as entitlement
import native_apex_feed as native_feed
import apex_fast_scanner as fast
import abutron_selective_tradingagents_v1 as selective
from apex_deriv_trade_symbol_scope import TRADE_SYMBOLS
from apex_portfolio_guard_v3 import capacity,UnsafeExposure

BASE=Path("/var/lib/apex-client-feed")
DB="/var/lib/apex-signup/accounts.sqlite3"
BRIDGE=Path("/opt/apex/native-order-bridge-v2/AbutronApexNativeOrderBridgeV2.ex5")
POLICY=Path("/etc/apex/trading-policy.json")
PROFILE=Path("/opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json")
HANDOVER=BASE/"handover-readiness.json"
RESULT=BASE/"execution-router"
ID=re.compile(r"^[a-f0-9]{32}$")
KEY=re.compile(r"^[a-f0-9]{64}$")
EXPECTED=set(ledger.SYMBOLS)
# Preserve the production V75 broker-feasibility hold during USD50/USD100 cutover.
TEMPORARY_NEW_ENTRY_EXCLUSIONS=frozenset()
MAX_FEED_AGE=160
MAX_SIGNAL_AGE=100
MAX_EA_AGE=12
ADAPTIVE_FLAG=Path("/etc/abutron/optionc-live-010.json")
def optionc_enabled(cid=None):
    if ADAPTIVE_FLAG.is_symlink() or not ADAPTIVE_FLAG.is_file():return False
    p=read(ADAPTIVE_FLAG)
    if p.get("schema")!="abutron.optionc.activation.v2" or p.get("demo_only") is not True:
        raise RuntimeError("ADAPTIVE_RUNTIME_POLICY_INVALID")
    allow=p.get("deriv_connection_allowlist")
    if (not isinstance(allow,list) or len(allow)!=1 or
            not isinstance(allow[0],str) or not ID.fullmatch(allow[0])):
        raise RuntimeError("ADAPTIVE_ACCOUNT_ALLOWLIST_INVALID")
    return p.get("deriv_enabled") is True and cid==allow[0]


def read(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4_000_000:
            return {}
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError, UnicodeError):
        return {}

def timestamp(s,age):
    try:
        value=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
        delta=time.time()-value.timestamp()
        return value.tzinfo is not None and -15<=delta<=age
    except (ValueError,TypeError,AttributeError,OverflowError):
        return False

def atomic_json(path,doc):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".router-")
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(doc,f,separators=(",",":"),allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def account_rows():
    c=sqlite3.connect("file:"+DB+"?mode=ro",uri=True,timeout=6)
    try:
        return c.execute("""SELECT x.id,x.account_id,x.broker,x.environment,
          x.broker_server,x.status,x.worker_binding,x.account_reference,
          COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
          FROM apex_mt5_connections x
          LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
          WHERE x.status IN ('CONNECTED','CONNECTING') ORDER BY x.id""").fetchall()
    finally:c.close()

def ea_state(cid,login,server):
    """Broker-bound native EA proof; only fresh V3 authorizes multi-symbol entry.

    V2/V1 compatibility remains read-only when multi-symbol EA is unavailable.
    """
    if not ID.fullmatch(cid) or not isinstance(login,str):
        return None,"INVALID_BRIDGE_IDENTITY"
    home=manager.state(cid)
    try:
        health=read(home/"worker-health.json")
        nonce=health["nonce"]
        if not ID.fullmatch(nonce) or health.get("status")!="CONNECTED":
            return None,"WORKER_NATIVE_HEALTH_UNVERIFIED"
        folder=home/"terminal/MQL5/Files"
        for proto in (3,2):
            proof_file=folder/("ABUTRON_APEX_BRIDGE_READY_V"+str(proto)+"_"+nonce+".txt")
            if proof_file.is_symlink():
                return None,"SYMLINKED_NATIVE_PROOF_DENIED"
            if not proof_file.is_file():
                continue
            if not 0<=time.time()-proof_file.stat().st_mtime<=12:
                return None,"NATIVE_BRIDGE_PROOF_STALE"
            lines=proof_file.read_text(encoding="utf-8-sig").splitlines()
            expected=["APEX_NATIVE_BRIDGE_READY_V"+str(proto),nonce,login,server,"DERIV_DEMO"]
            if len(lines)!=11 or lines[:5]!=expected:
                return None,"NATIVE_BRIDGE_ACCOUNT_OR_NONCE_MISMATCH"
            clock,pending,positions,terminal_allowed,broker_allowed,enabled=map(int,lines[5:11])
            if (abs(time.time()-clock)>18 or not 0<=pending<=300 or
                not 0<=positions<=300 or
                any(x not in (0,1) for x in (terminal_allowed,broker_allowed,enabled))):
                return None,"NATIVE_BRIDGE_EXPOSURE_PROOF_INVALID"
            return {"nonce":nonce,"bridge_loaded":True,"files":folder,
                    "exposure_verified":True,"pending_orders":pending,
                    "positions":positions,"terminal_trade_allowed":terminal_allowed==1,
                    "account_trade_allowed":broker_allowed==1,
                    "native_demo_orders_enabled":enabled==1,
                    "protocol_version":proto},None
        # Legacy V1 heartbeat cannot authorize a new multi-symbol entry.
        path=folder/("ABUTRON_APEX_BRIDGE_READY_V1_"+nonce+".txt")
        if path.is_symlink() or not path.is_file() or not 0<=time.time()-path.stat().st_mtime<=MAX_EA_AGE:
            return None,"NATIVE_BRIDGE_NOT_READY"
        lines=path.read_text(encoding="utf-8-sig").splitlines()
        if lines[:5]!=["APEX_NATIVE_BRIDGE_READY_V1",nonce,login,server,"DERIV_DEMO"]:
            return None,"EA_ACCOUNT_OR_NONCE_MISMATCH"
        proof={"nonce":nonce,"bridge_loaded":True,"files":folder,
               "protocol_version":1,"native_demo_orders_enabled":False}
        if len(lines)<10:
            proof["exposure_verified"]=False
            return proof,"EA_PENDING_ORDER_PROOF_NOT_YET_DEPLOYED"
        clock,pending,positions,terminal_allowed,broker_allowed=map(int,lines[5:10])
        if abs(time.time()-clock)>18 or not 0<=pending<=300 or not 0<=positions<=300:
            return proof,"EA_EXPOSURE_PROOF_STALE_OR_INVALID"
        proof.update({"exposure_verified":True,"pending_orders":pending,
                      "positions":positions,"terminal_trade_allowed":terminal_allowed==1,
                      "account_trade_allowed":broker_allowed==1})
        return proof,None
    except (ValueError,KeyError,IndexError,TypeError,OSError,UnicodeError):
        return None,"EA_PROOF_INVALID"

def plan(row,profile,policy,handover,engine_mode):
    cid,owner,broker,env,server,status,worker,login,desired,effective=row
    doc={"schema":"abutron.apex.native.dispatch.v1","checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
         "connection_id":cid,"account_id":owner,"broker":broker,"environment":env,
         "broker_feed_verified":False,"native_bridge_loaded":False,"execution_authorized":False,
         "signals_considered":0,"signals_ready":0,"orders_submitted":0,
         "orders_acknowledged":0,"candidate_orders":[],"blockers":[],"mode":engine_mode}
    reasons=doc["blockers"]
    def block(reason):
        if reason not in reasons:reasons.append(reason)
    if not ID.fullmatch(cid) or not ID.fullmatch(owner):
        block("INVALID_CONNECTION_ID")
        return doc
    # One-account root pause blocks NEW requests while its EA is reattached.
    # Existing broker positions and immutable reconciliation remain untouched.
    if (Path("/etc/abutron/optionc-canary-pause")/(cid+".pause")).is_file():
        block("ONE_ACCOUNT_EA_RELOAD_NEW_ENTRIES_PAUSED")
    if (broker,env,server,status,worker)!=("Deriv","DEMO","Deriv-Demo","CONNECTED","abutron-client-mt5-"+cid):
        block("NOT_APPROVED_ACTIVE_MT5_DEMO_ACCOUNT")
    verified=manager.attest(cid,broker,server) if broker=="Deriv" and env=="DEMO" else False
    if not verified:block("NATIVE_BROKER_CONNECTION_NOT_ATTESTED")
    audit=read(BASE/(cid+".json"))
    inbox=read(BASE/"inboxes"/(cid+".json"))
    if audit.get("account_id")!=owner or audit.get("connection_id")!=cid:
        block("NATIVE_FEED_TENANT_MISMATCH")
    if audit.get("status")!="BROKER_DATA_VERIFIED_SHADOW" or audit.get("broker_data_verified") is not True:
        block("BROKER_NATIVE_DATA_NOT_VERIFIED")
    if not timestamp(audit.get("checked_at_utc"),MAX_FEED_AGE):
        block("BROKER_FEED_STALE")
    if audit.get("symbol_count")!=13 or audit.get("timeframes_per_symbol")!=6:
        block("SYMBOL_TIMEFRAME_UNIVERSE_INCOMPLETE")
    doc["broker_feed_verified"]=not any(x.startswith(("BROKER_","NATIVE_FEED","SYMBOL_")) for x in reasons) and verified
    if inbox.get("account_id")!=owner or inbox.get("connection_id")!=cid or inbox.get("status")!="RESEARCH_PREVIEW":
        block("SIGNAL_TENANT_OR_SCHEMA_INVALID")
    if not timestamp(inbox.get("updated_at_utc"),MAX_SIGNAL_AGE):
        block("RESEARCH_INBOX_STALE")
    if inbox.get("orders_submitted")!=0 or inbox.get("trading_enabled") is not False:
        block("UNTRUSTED_SIGNAL_INBOX_EXECUTION_STATUS")
    ea,ea_error=ea_state(cid,login,server)
    doc["native_bridge_loaded"]=bool(ea and ea["bridge_loaded"])
    if ea_error:block(ea_error)
    # The fixed USD profile stays valid for legacy orders. In adaptive V2,
    # approved symbols and broker/account controls remain, but MQL5 derives
    # actual volume and structure stops rather than these legacy numbers.
    adaptive=optionc_enabled(cid)
    rows=profile.get("rows")
    lots={}
    if isinstance(rows,list):
        for r in rows:
            if isinstance(r,list) and len(r)==4 and isinstance(r[0],str) and type(r[1]) in (int,float):
                if r[0] in EXPECTED and math.isfinite(r[1]) and r[1]>0 and (
                    adaptive or (r[2]==50 and r[3]==100)):
                    lots[r[0]]=r[1]
    if (profile.get("status")!="ACTIVE_DERIV_DEMO_USD_GROSS" or len(rows or [])!=13 or
        len(lots)!=13 or policy.get("environment")!="DERIV_DEMO" or policy.get("live_trading") is not False or
        policy.get("max_concurrent_positions")!=13 or policy.get("max_positions_per_symbol")!=1):
        block("APEX_BROKER_SYMBOL_ACCOUNT_POLICY_INVALID" if adaptive
              else "APEX_FIXED_USD_RISK_PROFILE_INVALID")
    acct=audit.get("account") if isinstance(audit.get("account"),dict) else {}
    occupied=set()
    if not ea or not ea.get("exposure_verified") or ea.get("protocol_version")!=3:
        block("NATIVE_V3_PORTFOLIO_PROOF_UNVERIFIED")
    else:
        try:
            occupied=capacity(cid,acct,ea,login,server,EXPECTED,ledger.DB)
        except UnsafeExposure as exc:
            block(str(exc))
    if len(occupied)>=13:
        block("MAXIMUM_13_BROKER_POSITIONS_ACTIVE")
    if desired!=1 or effective!=1:
        block("CUSTOMER_AUTOMATED_EXECUTION_SWITCH_OFF")
    if handover.get("status")!="APPROVED_FOR_TRADING_CUTOVER":
        block("EXCLUSIVE_TRADING_HANDOVER_NOT_APPROVED")
    if not (ea and ea.get("terminal_trade_allowed") and ea.get("account_trade_allowed")):
        block("MT5_AUTOTRADING_NOT_BROKER_APPROVED")
    # Evaluate same CRM license/subscription/seat and account-control policy
    # as the signed worker entry endpoint. This is local root read-only evaluation.
    if not reasons:
        try:
            from apex_customer_worker_entitlement import evaluate
            payload={"account_id":owner,"connection_id":cid,"broker":broker,"platform":"MT5",
                     "environment":env,"account_reference":login,"broker_server":server,
                     "worker_binding":worker}
            c=sqlite3.connect("file:"+DB+"?mode=ro",uri=True,timeout=6)
            try:allowed,why,basis=evaluate(c,payload)
            finally:c.close()
            if not allowed or why:block("CRM_ACCOUNT_ENTITLEMENT_DENIED")
        except (ValueError,OSError,sqlite3.Error,TypeError,KeyError):
            block("CRM_ACCOUNT_ENTITLEMENT_UNAVAILABLE")
    if engine_mode=="inspect":
        block("INSPECTION_ONLY_NO_ORDERS")
    else:
        if not BRIDGE.is_file():block("NATIVE_ORDER_BRIDGE_BINARY_MISSING")
    if not isinstance(inbox.get("candidates"),list):
        block("INVALID_RESEARCH_CANDIDATES")
    # Only original APEX BUY/SELL proposals are eligible for selective
    # TradingAgents broker-only Qwen agreement. SMC/ICT/veto not consulted.
    # Existing broker, owner, handover, EA, license and 20% risk gates remain.
    doc["tradingagents_review"]={"schema":"abutron.apex.ta.review.gate.v1",
        "model":selective.MODEL,"approved":0,"held":0,
        "evaluations":[],"review_is_not_order_authority":True}
    seen=set()
    reports=read(Path('/var/lib/abutron-scanner-llm/latest.json'))
    for row_signal in inbox.get("candidates",[]) if isinstance(inbox.get("candidates"),list) else []:
        sym=row_signal.get("symbol");side=row_signal.get("side");bar=row_signal.get("m5_bar_time")
        if not adaptive and sym in TEMPORARY_NEW_ENTRY_EXCLUSIONS:
            doc.setdefault("temporary_entry_exclusions",[]).append(
                {"symbol":sym,"reason":"BROKER_STOP_DISTANCE_NOT_VERIFIED"})
            continue
        if sym not in TRADE_SYMBOLS:continue  # Never dispatch removed Deriv indices.
        if sym not in lots or sym in occupied or side not in ("BUY","SELL") or type(bar)!=int:continue
        if row_signal.get("status")!="RESEARCH_ONLY" or row_signal.get("execution_authorized") is not False:
            block("UNTRUSTED_SIGNAL_RESEARCH_STATUS");continue
        if not 0<=time.time()-(bar+300)<=240:continue
        key=ledger.expected_key(owner,cid,sym,bar,side)
        if not KEY.fullmatch(key) or row_signal.get("signal_key")!=key:
            block("SIGNAL_HASH_MISMATCH");continue
        expected=[x for x in audit.get("signal_preview",[]) if x.get("symbol")==sym]
        if not expected or expected[0].get("proposal")!=side or expected[0].get("last_closed_m5")!=bar:
            block("SIGNAL_NOT_FOUND_IN_VERIFIED_BROKER_SCANNER");continue
        if (sym,bar) in seen:
            block("DUPLICATE_CANDIDATE_IN_INBOX");continue
        seen.add((sym,bar))
        ok=False;why="TA_EVIDENCE_MISSING_OR_STALE"
        try:
            current=time.time()
            if (reports.get("schema")!="abutron.scanner.llm.v1" or
                reports.get("status")!="MODEL_REVIEW_COMPLETED" or
                reports.get("order_execution_modified") is not False or
                not timestamp(reports.get("checked_at_utc"),440)):
                raise ValueError("UNTRUSTED_TRADINGAGENTS_REPORT")
            reviews=[r for r in reports.get("reviews",[]) if isinstance(r,dict) and
                (r.get("symbol"),r.get("m5_bar_time"),r.get("scanner_proposal"))==(sym,bar,side)]
            if len(reviews)!=1:raise ValueError("TA_EXACT_CANDLE_REVIEW_MISSING")
            review=reviews[0]
            if (review.get("framework")!="TradingAgentsGraph selective broker-only analyst" or
                review.get("model")!=selective.MODEL or
                review.get("evidence_status")!="MODEL_REVIEW_COMPLETED" or
                review.get("analysis") not in ("BUY","SELL","HOLD") or
                not timestamp(review.get("reviewed_at_utc"),240)):
                raise ValueError("TA_REVIEW_INVALID_OR_EXPIRED")
            if review.get("llm_direction")!=side:
                why="TA_DISAGREEMENT_OR_HOLD"
            else:
                # Rebuild broker-native evidence independently in the
                # per-account isolated terminal; do not trust an AI file alone.
                if not ea or not ea.get("nonce"):raise ValueError("NATIVE_EA_PROOF_MISSING")
                path=manager.state(cid)/"terminal/MQL5/Files"/(
                    "ABUTRON_NATIVE_BARS_V2_"+ea["nonce"]+".txt")
                broker=native_feed.bars_file(path,ea["nonce"])
                bars=broker["data"][sym]
                frames={tf:fast.frame_state(bars[tf]) for tf in selective.FRAMES}
                _,digest=selective.validate_evidence("Deriv DEMO MT5",sym,bar,side,frames)
                if digest!=review.get("evidence_sha256"):
                    raise ValueError("BROKER_CANDLE_AI_HASH_MISMATCH")
                ok=True;why="EXACT_NATIVE_CANDLE_TA_CONFIRMED"
        except (OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError) as exc:
            why="TA_PROOF_"+type(exc).__name__
        doc["tradingagents_review"]["evaluations"].append(
            {"symbol":sym,"side":side,"bar":bar,"approved":ok,"reason":why})
        if not ok:
            doc["tradingagents_review"]["held"]+=1
            continue
        doc["tradingagents_review"]["approved"]+=1
        doc["candidate_orders"].append({"signal_key":key,"symbol":sym,"side":side,
                         "m5_bar_time":bar,"volume":lots[sym],
                         "gross_sl_usd":None if adaptive else 50.0,
                         "gross_tp_usd":None if adaptive else 100.0,
                         "risk_pct_equity":0.10 if adaptive else None,
                         "volume_source":"MT5_NATIVE_ADAPTIVE" if adaptive else "USD_PROFILE"})
    doc["signals_considered"]=len(inbox.get("candidates",[])) if isinstance(inbox.get("candidates"),list) else 0
    doc["signals_ready"]=len(doc["candidate_orders"])
    if not doc["candidate_orders"]:
        if doc["tradingagents_review"]["held"]:
            block("SELECTIVE_TRADINGAGENTS_REVIEW_NOT_APPROVED")
        block("NO_FRESH_QUALIFIED_SIGNAL")
    doc["execution_authorized"]=not bool(reasons)
    doc["status"]="READY_FOR_DEMO_DISPATCH" if doc["execution_authorized"] else "BLOCKED"
    return doc

def report(mode):
    if os.geteuid()!=0:raise RuntimeError("ROOT_ONLY")
    profile,policy,handover=read(PROFILE),read(POLICY),read(HANDOVER)
    rows=account_rows()
    plans=[plan(row,profile,policy,handover,mode) for row in rows]
    for doc in plans:atomic_json(RESULT/(doc["connection_id"]+".json"),doc)
    summary={"schema":"abutron.apex.native.router.summary.v1",
       "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
       "mode":mode,"accounts_checked":len(plans),
       "broker_feeds_verified":sum(p["broker_feed_verified"] for p in plans),
       "bridges_loaded":sum(p["native_bridge_loaded"] for p in plans),
       "fresh_research_candidates":sum(p["signals_ready"] for p in plans),
       "accounts_dispatch_authorized":sum(p["execution_authorized"] for p in plans),
       "orders_submitted":0,"broker_confirmed_orders":0,
       "status":"READ_ONLY" if mode=="inspect" else "DENIED_BY_GATES",
       "connections":[{"connection_id":p["connection_id"],"status":p["status"],
          "candidate_count":p["signals_ready"],"blockers":p["blockers"]} for p in plans]}
    atomic_json(RESULT/"summary.json",summary)
    print("APEX_NATIVE_SIGNAL_ROUTER",mode.upper(),
          "MT5_VERIFIED",summary["broker_feeds_verified"],
          "EA_LOADED",summary["bridges_loaded"],
          "RESEARCH_CANDIDATES",summary["fresh_research_candidates"],
          "EXECUTION_PERMITTED",summary["accounts_dispatch_authorized"],
          "ORDERS",summary["orders_submitted"],flush=True)
    return plans

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--inspect",action="store_true")
    ap.add_argument("--dispatch",action="store_true")
    args=ap.parse_args()
    if args.inspect and args.dispatch:ap.error("Choose one mode")
    mode="dispatch" if args.dispatch else "inspect"
    RESULT.mkdir(parents=True,exist_ok=True,mode=0o700)
    lockfd=os.open(str(RESULT/"router.lock"),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        plans=report(mode)
        # Intentionally no unverified file writes or OrderSend emulation here.
        # Dispatch remains denied until account-specific broker proof, ownership
        # and broker receipt contract are validated in isolated integration tests.
        if mode=="dispatch" and any(p["execution_authorized"] for p in plans):
            raise RuntimeError("NATIVE_ORDER_RECEIPT_RECONCILIATION_NOT_CERTIFIED")
    finally:os.close(lockfd)
if __name__=="__main__":main()
