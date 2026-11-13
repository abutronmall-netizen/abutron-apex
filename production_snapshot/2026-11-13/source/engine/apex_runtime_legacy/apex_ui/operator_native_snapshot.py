#!/usr/bin/python3
"""Publish sanitized, validated native Deriv DEMO feed to legacy operator UI.

Called AFTER existing native feed collection. No trading, credential operations,
remote communications, account permissions, or separate monitoring timers.
"""
from __future__ import annotations
import json,os,sys,sqlite3,grp,time,tempfile
from pathlib import Path
from datetime import datetime,timezone

sys.path.insert(0,"/opt/apex-client-mt5")
sys.path.insert(0,"/opt/apex/runtime")
import manager
from native_apex_feed import bars_file
from apex_fast_scanner import scan

BASE=Path("/var/lib/apex/operator-live")
DB="file:/var/lib/apex-signup/accounts.sqlite3?mode=ro"
PUBLIC_GROUP=grp.getgrnam("apexagent").gr_gid

def atomic(name,doc):
    fd,tmp=tempfile.mkstemp(prefix=".native.",dir=BASE)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(doc,stream,separators=(",",":"),allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(tmp,0,PUBLIC_GROUP)
        os.chmod(tmp,0o640)
        os.replace(tmp,BASE/name)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def eligible(cid,owner,broker,mode,server,status,worker,audit):
    if not (status=="CONNECTED" and broker=="Deriv" and mode=="DEMO" and
            server=="Deriv-Demo" and worker=="abutron-client-mt5-"+cid):
        return False
    if (not isinstance(audit,dict) or audit.get("connection_id")!=cid or
        audit.get("account_id")!=owner or
        audit.get("status")!="BROKER_DATA_VERIFIED_SHADOW" or
        audit.get("broker_data_verified") is not True or
        audit.get("symbol_count")!=13 or audit.get("timeframes_per_symbol")!=6):
        return False
    try:
        checked=datetime.fromisoformat(audit["checked_at_utc"].replace("Z","+00:00"))
        if not checked.tzinfo or not -15<=time.time()-checked.timestamp()<=170:
            return False
    except (KeyError,ValueError,TypeError):
        return False
    return manager.attest(cid,broker,server)


def broker_stops_attached(pos):
    try:
        stop=float(pos["sl"]); target=float(pos["tp"]); entry=float(pos["open_price"])
        return stop>0 and target>0 and (
          (stop<entry<target) if pos.get("side")=="BUY" else (target<entry<stop))
    except (ValueError,TypeError,KeyError):
        return False


def native_protection_index(cid,nonce,login,server):
    """Read-only EA attestation: never promote an over-budget stop to risk-verified."""
    out={}
    root=manager.state(cid)/"terminal/MQL5/Files/ABUTRON"
    evidence=root/"evidence"
    if not evidence.is_dir():
        return out
    try:
        files=sorted(evidence.glob("*.txt"),key=lambda f:f.stat().st_mtime,reverse=True)[:250]
    except OSError:
        return out
    for f in files:
        try:
            if f.is_symlink() or f.stat().st_size>5000:
                continue
            z=f.read_text(encoding="utf-8-sig").splitlines()
            if len(z)!=19 or z[:5]!=["APEX_BROKER_POSITION_V2",f.stem,nonce,login,server]:
                continue
            if z[16] not in ("OPEN_PROTECTED","OPEN_UNPROTECTED"):
                continue
            if not 0<=time.time()-int(z[17])<=90:
                continue
            position=int(z[9])
            d={"ea_risk_attestation":z[16],"native_stop_risk_usd":float(z[14])}
            intent=root/"optionc_v2"/(f.stem+".txt")
            if intent.is_file() and not intent.is_symlink() and intent.stat().st_size<3000:
                x=intent.read_text(encoding="utf-8-sig").splitlines()
                if len(x)==14 and x[:7]==["APEX_OPTIONC_NATIVE_RISK_INTENT_V2",
                   f.stem,nonce,login,server,z[5],z[6]]:
                    budget=float(x[8])
                    if budget>0 and float(x[11])==float(z[12]) and float(x[12])==float(z[13]):
                        d["native_risk_budget_usd"]=budget
                        d["native_budget_exceeded"]=float(z[14])>budget*1.01+0.005
            out[position]=(z,d)
        except (OSError,ValueError,TypeError,KeyError,OverflowError):
            continue
    return out


def main():
    if os.geteuid()!=0:
        raise RuntimeError("ROOT_PUBLISH_REQUIRED")
    BASE.mkdir(parents=True,exist_ok=True)
    os.chown(BASE,0,PUBLIC_GROUP)
    os.chmod(BASE,0o750)
    with sqlite3.connect(DB,uri=True) as c:
        rows=c.execute("""
        SELECT x.id,x.account_id,x.broker,x.environment,x.broker_server,
               x.status,x.worker_binding,x.account_reference,a.email,
               COALESCE(t.effective_enabled,0)
        FROM apex_mt5_connections x JOIN accounts a ON a.id=x.account_id
        LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
        WHERE x.status IN ('CONNECTED','CONNECTING','ERROR')
        ORDER BY x.id
        """).fetchall()
    # Read-only execution reporting. No customer identifiers leave this publisher.
    ledger_positions={}
    ledger_entry_events=[]
    ledger_deals=ledger_unresolved=0
    ledger_available=False
    try:
        with sqlite3.connect(
          "file:/var/lib/apex-client-feed/execution-ledger.sqlite3?mode=ro",
          uri=True,timeout=3) as ledger:
            ledger_positions={
              (cid,int(ticket)):(symbol,side)
              for cid,ticket,symbol,side in ledger.execute(
                "SELECT connection_id,broker_position,symbol,side FROM attempts "
                "WHERE state='OPEN_PROTECTED' AND broker_position IS NOT NULL")
            }
            ledger_deals=ledger.execute(
              "SELECT COUNT(*) FROM attempts WHERE broker_deal>0").fetchone()[0]
            ledger_unresolved=ledger.execute(
              "SELECT COUNT(*) FROM attempts WHERE state IN "
              "('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED','UNPROTECTED')").fetchone()[0]
            # Broker-acknowledged APEX entry DEAL IDs, with APEX request timestamps.
            # This is NOT the full MT5 broker execution history or broker deal time.
            ledger_entry_events=ledger.execute("""
               SELECT connection_id,broker_position,broker_deal,symbol,side,
                      volume,entry_price,state,created_at_utc
               FROM attempts
               WHERE broker_deal>0 AND state IN ('OPEN_PROTECTED','CLOSED_RECONCILED')
               ORDER BY created_at_utc DESC LIMIT 250
            """).fetchall()
            ledger_available=True
    except (sqlite3.Error,ValueError,TypeError):
        pass
    verified_positions=0
    records=[]
    selected=None
    for cid,owner,broker,mode,server,status,worker,login,email,enabled in rows:
        # This is the Deriv-native operator publisher; FP has its own UI.
        # Other brokers must not inflate Deriv connected/enabled counters.
        if (broker,mode)!=("Deriv","DEMO"):
            continue
        try:
            audit=json.loads((Path("/var/lib/apex-client-feed")/(cid+".json")).read_text())
        except (ValueError,OSError,UnicodeError):
            audit={}
        verified=eligible(cid,owner,broker,mode,server,status,worker,audit)
        if verified and ledger_available:
            acct=audit.get("account",{}) if isinstance(audit,dict) else {}
            positions=acct.get("positions",[])
            if acct.get("all_positions_protected") is True and isinstance(positions,list):
                for pos in positions:
                    if not isinstance(pos,dict) or pos.get("protected") is not True:
                        continue
                    try:
                        key=(cid,int(pos.get("ticket")))
                        if (ledger_positions.get(key)==(pos.get("symbol"),pos.get("side"))
                            and float(pos.get("sl",0))>0 and float(pos.get("tp",0))>0):
                            verified_positions+=1
                    except (ValueError,TypeError):
                        continue
        home=manager.state(cid)
        nonce=""
        health={}
        bridge=False
        if verified:
            try:
                health=json.loads((home/"worker-health.json").read_text())
                nonce=health.get("nonce","")
                proof=home/"terminal/MQL5/Files"/("ABUTRON_APEX_BRIDGE_READY_V1_"+nonce+".txt")
                if proof.is_file() and 0<=time.time()-proof.stat().st_mtime<20:
                    parts=proof.read_text(encoding="utf-8-sig").splitlines()
                    bridge=parts[:5]==["APEX_NATIVE_BRIDGE_READY_V1",nonce,login,server,"DERIV_DEMO"]
            except (OSError,ValueError,TypeError):
                bridge=False
        role=("Primary owner" if email.lower()=="abutroncloud@gmail.com"
              else "Client MT5")
        records.append({"label":role,"connected":bool(verified),
             "bridge_ready":bridge,"trade_enabled":bool(enabled==1),
             "symbol_count":13 if verified else 0})
        if verified:
            score=1 if role=="Primary owner" else 0
            if selected is None or score>selected[0]:
                selected=(score,cid,nonce,audit,role)
    now=datetime.now(timezone.utc).isoformat()
    summary={"schema":"abutron.operator.native.v1","checked_at_utc":now,
       "sessions_total":len(records),
       "sessions_connected":sum(x["connected"] for x in records),
       "bridges_ready":sum(x["bridge_ready"] for x in records),
       "trading_enabled":sum(x["trade_enabled"] for x in records if x["connected"]),
       "execution_verified":bool(ledger_available and ledger_deals>0),
       "source_server_dependency":False,
       "accounts":records,"broker_source":"UNAVAILABLE",
       "primary_account":{"available":False,"stale":True},
       "execution_runtime":{"ledger_available":ledger_available,
         "broker_acknowledged_deals":ledger_deals if ledger_available else None,
         "verified_protected_positions":verified_positions if ledger_available else None,
         "unreconciled_attempts":ledger_unresolved if ledger_available else None,
         "new_entry_accounts":sum(x["trade_enabled"] for x in records if x["connected"]),
         "mode":"DERIV_DEMO_ONLY"}}
    market_file=BASE/"native-market.json"
    scanner_file=BASE/"native-scanner.json"
    if selected:
        _,cid,nonce,audit,role=selected
        try:
            path=manager.state(cid)/"terminal/MQL5/Files"/("ABUTRON_NATIVE_BARS_V2_"+nonce+".txt")
            market=bars_file(path,nonce)
            result=scan(market)
            atomic("native-market.json",market)
            atomic("native-scanner.json",result)
            summary["broker_source"]="NATIVE_BROKER_VERIFIED"
            summary["market_snapshot_utc"]=market["generated_at_utc"]
            summary["research_only"]=True
            if role=="Primary owner":
                acct=audit.get("account",{})
                # Restrict the operator's APEX deal view to its SELECTED owner
                # account; never combine another customer's broker history.
                owner_events=[r for r in ledger_entry_events if r[0]==cid]
                open_requests={int(r[1]):r[8] for r in owner_events
                               if r[7]=='OPEN_PROTECTED' and r[1] is not None}
                entries=[{
                    "deal":int(r[2]),"time_utc":r[8],"symbol":r[3],
                    "side":r[4],"entry":("OPEN" if r[7]=="OPEN_PROTECTED"
                                         else "CLOSED_RECONCILED"),
                    "volume":r[5],"price":r[6],
                    "profit_usd":None,"net_cashflow_usd":None,
                    "timestamp_source":"APEX_ORDER_REQUEST_NOT_BROKER_EXECUTION"
                } for r in owner_events[:30]]
                native_index=native_protection_index(cid,nonce,
                     next((r[7] for r in rows if r[0]==cid),""),
                     "Deriv-Demo")
                positions_with_annotation=[]
                broker_stop_count=risk_overrun_count=0
                for p in acct.get("positions",[])[:50]:
                    has_stops=bool(p.get("protected") is True and broker_stops_attached(p))
                    if has_stops:
                        broker_stop_count+=1
                    ticket=int(p.get("ticket",0))
                    matched=native_index.get(ticket)
                    proof={}
                    if matched:
                        z,d=matched
                        if (z[5]==p.get("symbol") and z[6]==p.get("side") and
                            abs(float(z[12])-float(p.get("sl",0)))<1e-7 and
                            abs(float(z[13])-float(p.get("tp",0)))<1e-7):
                            proof=d
                    if proof.get("native_budget_exceeded") is True:
                        risk_overrun_count+=1
                    positions_with_annotation.append({
                      "ticket":p.get("ticket"),"symbol":p.get("symbol"),
                      "side":p.get("side"),"volume":p.get("volume"),
                      "price_open":p.get("open_price"),"sl":p.get("sl"),
                      "tp":p.get("tp"),"profit_usd":p.get("floating_profit_usd"),
                      "request_utc":open_requests.get(ticket),
                      "broker_stops_attached":has_stops,
                      **proof})
                summary["execution_runtime"]["broker_stops_attached_positions"]=broker_stop_count
                summary["execution_runtime"]["ea_risk_budget_overrun_positions"]=risk_overrun_count
                summary["primary_account"]={
                    "available":True,"stale":False,"environment":"Deriv DEMO USD",
                    "generated_at_utc":audit.get("checked_at_utc"),
                    "age_seconds":0,
                    "balance_usd":acct.get("balance_usd"),
                    "equity_usd":acct.get("equity_usd"),
                    "open_positions":acct.get("open_positions"),
                    "positions":positions_with_annotation,
                    "recent_deals":entries,"history_complete":False,
                    "deal_list_scope":"APEX_BROKER_ACKNOWLEDGED_ENTRIES_ONLY",
                    "timestamp_semantics":"APEX_REQUEST_CREATED_NOT_MT5_EXECUTION_TIME"}
        except (OSError,ValueError,KeyError,TypeError,OverflowError):
            summary["broker_source"]="UNAVAILABLE"
            market_file.unlink(missing_ok=True)
            scanner_file.unlink(missing_ok=True)
    else:
        market_file.unlink(missing_ok=True)
        scanner_file.unlink(missing_ok=True)
    try:
        from apex_ui.execution_truth import build as build_account_execution_truth
        summary["account_execution"]=build_account_execution_truth()
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):
        summary["account_execution"]={"schema":"abutron.operator.execution_truth.v1",
          "checked_at_utc":datetime.now(timezone.utc).isoformat(),
          "all_demo_accounts_fully_operational_verified":False,
          "status":"CURRENT_ACCOUNT_EXECUTION_EVIDENCE_UNAVAILABLE"}
    atomic("native-status.json",summary)
    print("OPERATOR_NATIVE_PUBLISHED",
          "CONNECTED",summary["sessions_connected"],"OF",summary["sessions_total"],
          "BRIDGES",summary["bridges_ready"],
          "MARKET",summary["broker_source"],
          "TRADING_ENABLED",summary["trading_enabled"])

if __name__=="__main__":
    main()
