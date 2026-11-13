#!/usr/bin/python3
"""FP DEMO cached UI safety: publish no market claims without a current MT5 session.
No broker logins, orders, account-control edits, or signal routing.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import json,sqlite3,subprocess,time,tempfile,os,pwd,grp,stat
CID="35b81a287b6a030f2f46ff426b135e6c"
DB=Path("/var/lib/apex-signup/accounts.sqlite3")
WORKER=Path("/var/lib/private/abutron-client-mt5-"+CID)
OPERATOR=Path("/var/lib/apex/operator-live/fp-markets-ui.json")
CUSTOMER=Path("/var/lib/apex-signup/fp-market-ui")/(CID+".json")
SYMS=("XAUUSD","BTCUSD","EURUSD","GBPUSD","USDJPY","AUDUSD",
      "US100","US30","SP500","GER40","USOIL","USDCHF","NZDUSD")
FRAMES=("M1","M5","M15","H1","H4","D1")

def read_state(db=DB):
    with sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=7) as c:
        c.execute("PRAGMA query_only=ON")
        row=c.execute("""SELECT a.status,a.broker,a.environment,a.broker_server,
             a.account_reference,COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
             FROM apex_mt5_connections a LEFT JOIN apex_trade_controls t
               ON a.id=t.connection_id WHERE a.id=?""",(CID,)).fetchone()
    if not row or row[1:4]!=("FP Markets","DEMO","FPMarketsSC-Demo"):
        raise ValueError("FP_SESSION_IDENTITY_NOT_FOUND")
    status,broker,mode,server,reference,desired,effective=row
    if not isinstance(reference,str) or not reference.isdigit() or len(reference)<4:
        raise ValueError("FP_ACCOUNT_REFERENCE_INVALID")
    return {"status":status,"masked":"••••"+reference[-4:],
            "desired":bool(desired),"effective":bool(effective)}

def broker_connected(state,now=None):
    now=time.time() if now is None else now
    if state["status"]!="CONNECTED":return False
    try:
        unit="abutron-client-mt5-"+CID+".service"
        status=subprocess.run(["systemctl","is-active",unit],capture_output=True,
                              text=True,timeout=4)
        if status.returncode!=0 or status.stdout.strip()!="active":return False
        health=WORKER/"worker-health.json"
        if health.is_symlink() or not health.is_file() or health.stat().st_size>30000:
            return False
        h=json.loads(health.read_text())
        if (h.get("status")!="CONNECTED" or h.get("heartbeat_fresh") is not True
           or h.get("id")!=CID or h.get("broker")!="FP Markets"
           or h.get("server")!="FPMarketsSC-Demo" or
           h.get("mode")!="DEMO" or not isinstance(h.get("nonce"),str)
           or len(h["nonce"])!=32 or now-health.stat().st_mtime>20):return False
        proof=WORKER/"terminal/MQL5/Files"/("ABUTRON_SESSION_HEARTBEAT_V1_"+h["nonce"]+".txt")
        if proof.is_symlink() or not proof.is_file() or not -10<=now-proof.stat().st_mtime<=20:
            return False
        rows=proof.read_text(encoding="utf-8-sig").splitlines()
        return (len(rows)==8 and rows[0]=="ABUTRON_MT5_NATIVE_HEARTBEAT_V1"
           and rows[1]==h["nonce"] and rows[3:]==
           ["FP_MARKETS","FPMarketsSC-Demo","DEMO","CONNECTED","NO_ORDER_FUNCTIONS"])
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
        return False

def offline_snapshot(state,now=None):
    now=time.time() if now is None else now
    status="CONNECTING" if state["status"]=="CONNECTING" else "RECONNECT_REQUIRED"
    notice=("FP Markets DEMO broker session is not authenticated. "
            "Reconnect this account through the ABUTRON client portal. "
            "Market prices, decisions, positions and P/L are not live.")
    symbols=[]
    for sym in SYMS:
        family=("Metal" if sym=="XAUUSD" else "Crypto" if sym=="BTCUSD" else
                "Commodity" if sym=="USOIL" else "Index" if sym in
                ("US100","US30","SP500","GER40") else "Forex")
        symbols.append({
          "symbol":sym,"broker_symbol":"UNAVAILABLE","family":family,
          "available":False,"broker_status":"SESSION_NOT_VERIFIED",
          "timeframe_trends":{},"m5_candle_body":"UNAVAILABLE",
          "bid":None,"ask":None,"quote_timestamp_utc":None,"quote_age_seconds":None,
          "m5_last_close":None,"m5_change_pct":None,"m5_close_utc":None,
          "m5_bar_time":None,"proposal":"HOLD","m5_direction":"HOLD",
          "higher_timeframe_direction":"UNAVAILABLE","rsi14":None,"atr14":None,
          "scanner_reason":"FP_BROKER_SESSION_NOT_CONNECTED",
          "smc":"VETO","smc_score":0,"smc_reason":"NO_BROKER_SESSION",
          "ict":"VETO","liquidity_sweep":False,"zone_retest":False,
          "premium_discount":"UNVERIFIED","ai_status":"PENDING",
          "ai_direction":None,"ai_model":"","ai_analysis":"",
          "research_direction":"HOLD","final_decision":"HOLD",
          "orders_enabled":False,"execution_authorized":False})
    return {
      "schema":"abutron.fpmarkets.ui.readonly.v1",
      "available":False,"generated_at_utc":datetime.fromtimestamp(now,timezone.utc).isoformat(),
      "broker":"FP Markets","environment":"DEMO","account_masked":state["masked"],
      "broker_server":"FPMarketsSC-Demo","status":status,
      "source_quality":"BROKER_SESSION_UNVERIFIED",
      "coverage_complete":False,"unavailable_symbols":list(SYMS),
      "quote_count":0,"fresh_quotes":0,"timeframe_series":0,
      "symbol_list":list(SYMS),"timeframes":list(FRAMES),
      "scanner_proposals":0,"ai_agreements":0,"smc_ict_ai_agreements":0,
      "native_feed_at_utc":None,"scanner_at_utc":None,"ai_review_at_utc":None,
      "execution_enabled":False,"orders_submitted_by_collector":0,
      "trading_controls":{"desired_enabled":state["desired"],"effective_enabled":False},
      "verified_trade_history_available":False,
      "verified_open_positions_count":None,"verified_pending_orders_count":None,
      "verified_broker_trade_deals_90d":None,"verified_equity_usd":None,
      "trade_history_notice":notice,"symbols":symbols,"candles":{}}

def atomic(target,obj,uid,gid):
    if target.is_symlink() or not target.parent.is_dir():
        raise ValueError("FP_PUBLICATION_DESTINATION_INVALID")
    fd,tmp=tempfile.mkstemp(dir=target.parent,prefix=".fp-offline-")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(obj,f,separators=(",",":"),allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640);os.chown(tmp,uid,gid)
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def run():
    state=read_state()
    if broker_connected(state):
        return {"status":"LIVE_SESSION_KEEP_NATIVE_PUBLISHER","changed":False}
    doc=offline_snapshot(state)
    atomic(OPERATOR,doc,0,grp.getgrnam("apexagent").gr_gid)
    client_user=pwd.getpwnam("apexsignup")
    atomic(CUSTOMER,doc,client_user.pw_uid,client_user.pw_gid)
    return {"status":doc["status"],"changed":True,"fresh_quotes":0,
            "orders_submitted":0,"execution_enabled":False}

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True))
