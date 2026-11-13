#!/usr/bin/env python3
"""ABUTRON APEX customer Deriv DEMO broker-native feed and shadow signal router.

Read-only. Never sends orders, changes MT5 state, grants entitlement or enables trading.
Fail closed unless private MT5 heartbeat, native account+positions, and all 78 histories
are fresh, complete, account-matched and internally consistent.
"""
import os,sys,json,sqlite3,math,time,stat,hashlib,tempfile
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,"/opt/apex-client-mt5")
sys.path.insert(0,"/opt/apex/runtime")
import manager as private_manager
from apex_deriv_trade_symbol_scope import TRADE_SYMBOLS
from apex_fast_scanner import EXPECTED,FRAMES,FRAME_SECS,scan,validate_snapshot
DB="/var/lib/apex-signup/accounts.sqlite3"
OUT=Path("/var/lib/apex-client-feed")
MAX_BYTES=3_500_000
def clock():return datetime.now(timezone.utc).isoformat()
def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd,p=tempfile.mkstemp(prefix=".audit-",dir=str(path.parent))
 try:
  with os.fdopen(fd,"w") as f:
   json.dump(obj,f,allow_nan=False,separators=(",",":"))
   f.flush();os.fsync(f.fileno())
  os.chmod(p,0o600)
  os.replace(p,path)
 finally:
  if os.path.exists(p):os.unlink(p)
def read_native(path,nonce,max_age=170):
 if not path.is_file() or path.is_symlink():raise ValueError("NATIVE_EXPORT_ABSENT")
 info=path.stat()
 if info.st_size<32 or info.st_size>MAX_BYTES:raise ValueError("NATIVE_EXPORT_SIZE_INVALID")
 if not -10<=time.time()-info.st_mtime<=max_age:raise ValueError("NATIVE_EXPORT_STALE")
 flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
 fd=os.open(path,flags)
 try:
  actual=os.fstat(fd)
  if not stat.S_ISREG(actual.st_mode) or actual.st_ino!=info.st_ino:
   raise ValueError("NATIVE_EXPORT_REPLACED")
  raw=os.read(fd,MAX_BYTES+1)
  if os.fstat(fd).st_mtime_ns!=actual.st_mtime_ns:
   raise ValueError("NATIVE_EXPORT_CHANGED_DURING_READ")
 finally:os.close(fd)
 if len(raw)>MAX_BYTES:raise ValueError("NATIVE_EXPORT_EXCESSIVE")
 content=raw.decode("utf-8-sig",errors="strict").splitlines()
 if len(content)<2 or content[1]!=nonce:raise ValueError("NATIVE_EXPORT_NONCE_MISMATCH")
 return content,actual.st_mtime
def finite_positive(s,allow_zero=False):
 x=float(s)
 if not math.isfinite(x) or x<0 or (not allow_zero and x<=0):
  raise ValueError("INVALID_NATIVE_NUMERIC_VALUE")
 return x
def account_file(path,nonce,expected_login):
 rows,mtime=read_native(path,nonce)
 if rows[0]!="ABUTRON_NATIVE_ACCOUNT_V2" or len(rows)<7:
  raise ValueError("INVALID_NATIVE_ACCOUNT_FORMAT")
 if rows[2]!=expected_login:raise ValueError("BROKER_LOGIN_MISMATCH")
 if rows[5]!="USD":raise ValueError("NON_USD_BROKER_ACCOUNT")
 balance=finite_positive(rows[3],True);equity=finite_positive(rows[4],True)
 count=int(rows[6])
 if count<0 or count>500 or len(rows)!=7+count:raise ValueError("BROKER_POSITIONS_INCOMPLETE")
 positions=[];tickets=set()
 for raw in rows[7:]:
  parts=raw.split("\t")
  if len(parts)!=8:raise ValueError("POSITION_FIELDS_INVALID")
  ticket=int(parts[0])
  if ticket<=0 or ticket in tickets:raise ValueError("POSITION_DUPLICATE")
  tickets.add(ticket)
  side=int(parts[2])
  if side not in (0,1):raise ValueError("POSITION_SIDE_INVALID")
  volume=finite_positive(parts[3]);price=finite_positive(parts[4])
  sl=finite_positive(parts[5],True);tp=finite_positive(parts[6],True)
  profit=float(parts[7])
  if not math.isfinite(profit):raise ValueError("POSITION_PROFIT_INVALID")
  positions.append({"ticket":ticket,"symbol":parts[1],"side":("BUY" if side==0 else "SELL"),
     "volume":volume,"open_price":price,"sl":sl,"tp":tp,"floating_profit_usd":profit,
     "protected":bool(sl>0 and tp>0)})
 return {"balance_usd":balance,"equity_usd":equity,"open_positions":count,
    "pending_orders":None,"pending_orders_verified":False,
    "positions":positions,"all_positions_protected":all(x["protected"] for x in positions),
    "export_mtime_utc":datetime.fromtimestamp(mtime,timezone.utc).isoformat()}
def bars_file(path,nonce):
 rows,mtime=read_native(path,nonce)
 if rows[0]!="ABUTRON_NATIVE_BARS_V2":raise ValueError("INVALID_NATIVE_BARS_SCHEMA")
 if len(rows)>8100:raise ValueError("NATIVE_BARS_EXCESSIVE")
 data={k:{tf:[] for tf in FRAMES} for k in EXPECTED}
 for raw in rows[2:]:
  p=raw.split("\t")
  if len(p)!=7:raise ValueError("INVALID_BAR_FIELDS")
  symbol,tf=p[:2]
  if symbol not in data or tf not in FRAMES:raise ValueError("UNAPPROVED_SYMBOL_OR_TIMEFRAME")
  ts=int(p[2]);prices=[finite_positive(x) for x in p[3:]]
  data[symbol][tf].append({"time":ts,"open":prices[0],"high":prices[1],
    "low":prices[2],"close":prices[3]})
 doc={"schema":"apex.mt5.market.v1","source":"Deriv DEMO MT5",
      "generated_at_utc":datetime.fromtimestamp(mtime,timezone.utc).isoformat(),
      "execution_enabled":False,"data":data}
 validate_snapshot(doc,datetime.now(timezone.utc))
 return doc
def rejection_class(signal):
 reason=signal.get("reason","")
 if signal.get("proposal") in ("BUY","SELL"):return "QUALIFIED_RESEARCH"
 if reason.startswith("M5 mixed"):return "M5_MOMENTUM_MIXED"
 if "higher TF conflict" in reason or "conflicts with aligned" in reason:
  return "HIGHER_TIMEFRAME_CONFLICT"
 if "outside" in reason and "entry filter" in reason:return "RSI_ENTRY_FILTER"
 if "spike-model" in reason:return "CRASH_BOOM_SPIKE_SAFETY"
 if "ATR unavailable" in reason:return "VOLATILITY_UNAVAILABLE"
 return "OTHER_RESEARCH_HOLD"
def diagnostic_row(signal):
 frames=signal.get("indicators",{})
 m5=frames.get("M5",{})
 a=m5.get("atr14")
 extension=None
 if isinstance(a,(int,float)) and a>0:
  extension=round(abs(m5["close"]-m5["ema9"])/a,3)
 return {
  "symbol":signal["symbol"],"proposal":signal["proposal"],
  "last_closed_m5":signal["last_closed_m5"],
  "rejection_class":rejection_class(signal),
  "reason":signal.get("reason","")[:240],
  "m5_signal":signal.get("m5_signal"),
  "higher_tf_signal":signal.get("higher_tf_signal"),
  "m5_rsi14":m5.get("rsi14"),"m5_atr14":m5.get("atr14"),
  "m5_close_to_ema9_atr":extension,
  "m15_trend":frames.get("M15",{}).get("trend"),
  "h1_trend":frames.get("H1",{}).get("trend"),
  "h4_trend":frames.get("H4",{}).get("trend"),
 }

def observe(cid,owner,broker,environment,server,login,worker,status):
 out={"schema":"abutron.client.broker.audit.v1","checked_at_utc":clock(),
      "connection_id":cid,"account_id":owner,"broker":broker,"environment":environment,
      "status":"BLOCKED","trade_execution_enabled":False,"signals_dispatched":0,
      "orders_submitted":0,"blockers":[]}
 try:
  if status!="CONNECTED" or broker!="Deriv" or environment!="DEMO" or server!="Deriv-Demo":
   raise ValueError("NO_APPROVED_DERIV_DEMO_SESSION")
  if worker!="abutron-client-mt5-"+cid:raise ValueError("WRONG_CLIENT_WORKER")
  if not private_manager.attest(cid,broker,server):raise ValueError("NATIVE_BROKER_HEARTBEAT_NOT_VERIFIED")
  home=Path("/var/lib/private")/("abutron-client-mt5-"+cid)
  health=json.loads((home/"worker-health.json").read_text())
  nonce=health["nonce"]
  if not isinstance(nonce,str) or len(nonce)!=32:raise ValueError("MISSING_NATIVE_NONCE")
  files=home/"terminal/MQL5/Files"
  account=account_file(files/("ABUTRON_NATIVE_ACCOUNT_V2_"+nonce+".txt"),nonce,login)
  market=bars_file(files/("ABUTRON_NATIVE_BARS_V2_"+nonce+".txt"),nonce)
  signals=scan(market)
  out.update({"status":"BROKER_DATA_VERIFIED_SHADOW","broker_data_verified":True,
   "account":account,"market_data_generated_utc":market["generated_at_utc"],
   "timeframes_per_symbol":6,"symbol_count":13,
   "apex_strategy":"apex_ema_rsi_mtf_research_v1",
   "strategy_status":"RESEARCH_ONLY","qualified_research_signals":sum(s["proposal"] in ("BUY","SELL") for s in signals["instruments"] if s["symbol"] in TRADE_SYMBOLS),
   "approved_new_entry_symbols":sorted(TRADE_SYMBOLS),"approved_new_entry_symbol_count":3,
   # Advisory diagnostics: preserve exact executable proposal/bar fields.
   # These fields NEVER grant orders; they explain a research HOLD from broker M5/M15/H1/H4.
   "signal_preview":[diagnostic_row(s) for s in signals["instruments"] if s["symbol"] in TRADE_SYMBOLS],
   "scanner_rejection_counts":dict(sorted(__import__("collections").Counter(
     rejection_class(s) for s in signals["instruments"] if s["symbol"] in TRADE_SYMBOLS).items())),
   "blockers":["NO_ACCOUNT_EXECUTION_AUTHORIZATION","NO_VERIFIED_ORDER_BRIDGE",
               "OWNER_POSITION_HANDOVER_PENDING"]})
  if not account["all_positions_protected"]:
   out["blockers"].append("UNPROTECTED_BROKER_POSITIONS")
 except (OSError,KeyError,IndexError,ValueError,TypeError,OverflowError,UnicodeError) as e:
  out["blockers"].append(str(e)[:105])
 return out
def collect():
 OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
 with sqlite3.connect("file:"+DB+"?mode=ro",uri=True) as c:
  rows=c.execute("""SELECT id,account_id,broker,environment,broker_server,
    account_reference,worker_binding,status FROM apex_mt5_connections
    WHERE status IN ('CONNECTED','CONNECTING') ORDER BY id""").fetchall()
 reports=[]
 for cid,owner,broker,mode,server,login,worker,status in rows:
  if not (isinstance(cid,str) and len(cid)==32 and all(x in "0123456789abcdef" for x in cid)):
   continue
  result=observe(cid,owner,broker,mode,server,login,worker,status)
  atomic(OUT/(cid+".json"),result)
  reports.append({"connection_id":cid,"status":result["status"],
       "blockers":result["blockers"],"orders_submitted":0})
 summary={"schema":"abutron.apex.client_feed.summary.v1","checked_at_utc":clock(),
  "client_connections_checked":len(reports),
  "verified_native_market_feeds":sum(r["status"]=="BROKER_DATA_VERIFIED_SHADOW" for r in reports),
  "execution_cutover":"LOCKED","customer_trading_enabled":False,"orders_submitted":0,
  "source_server_dependency":False,"connections":reports}
 atomic(OUT/"summary.json",summary)
 print("CLIENT_NATIVE_FEED",summary["client_connections_checked"],"VERIFIED",
  summary["verified_native_market_feeds"],"ORDER_COUNT",0)
 return summary
if __name__=="__main__":collect()
