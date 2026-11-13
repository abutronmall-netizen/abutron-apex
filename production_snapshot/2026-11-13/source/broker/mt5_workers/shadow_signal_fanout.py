#!/usr/bin/env python3
"""ABUTRON customer-bound APEX shadow fanout (read-only, NO broker order sender).

Consumes only validated, recent native per-client feeds; keys by tenant+connection+M5 bar.
Writes private research inboxes for isolated accounts. Never flips trade permissions,
cannot activate any trading bridge, and never creates a production cutover gate.
"""
import os,json,time,hashlib,sqlite3,math,tempfile
from pathlib import Path
from datetime import datetime,timezone
from apex_deriv_trade_symbol_scope import TRADE_SYMBOLS
FEED=Path("/var/lib/apex-client-feed")
OUT=FEED/"inboxes"
DB="/var/lib/apex-signup/accounts.sqlite3"
SYMBOLS=TRADE_SYMBOLS
def iso():return datetime.now(timezone.utc).isoformat()
def atomic(path,data):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd,tmp=tempfile.mkstemp(dir=str(path.parent),prefix=".candidate-")
 try:
  with os.fdopen(fd,"w") as f:
   json.dump(data,f,allow_nan=False,separators=(",",":"));f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o600);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def decision(audit,owner,cid,now=None):
 now=now or time.time()
 reasons=[]
 if audit.get("account_id")!=owner or audit.get("connection_id")!=cid:
  reasons.append("CROSS_CUSTOMER_OR_CONNECTION_REJECTED")
 if audit.get("status")!="BROKER_DATA_VERIFIED_SHADOW":
  reasons.append("NO_VALIDATED_NATIVE_BROKER_FEED")
 try:
  checked=datetime.fromisoformat(audit["checked_at_utc"].replace("Z","+00:00"))
  if checked.tzinfo is None or not -15<=now-checked.timestamp()<=150:
   reasons.append("BROKER_FEED_AUDIT_STALE")
 except (TypeError,KeyError,ValueError):reasons.append("BROKER_FEED_AUDIT_INVALID_TIME")
 if audit.get("environment")!="DEMO" or audit.get("broker")!="Deriv":
  reasons.append("NON_DEMO_OR_NON_DERIV_DATA")
 if not audit.get("account",{}).get("all_positions_protected",False):
  reasons.append("POSITIONS_NOT_INDEPENDENTLY_PROTECTED")
 if reasons:return {"status":"BLOCKED","blockers":reasons,"candidates":[]}
 results=[]
 for row in audit.get("signal_preview",[]):
  symbol=row.get("symbol");side=row.get("proposal");bar=row.get("last_closed_m5")
  if symbol not in SYMBOLS or side not in ("BUY","SELL") or type(bar) is not int:
   continue
  if not 0<=now-(bar+300)<=240:continue
  signal_key=hashlib.sha256((owner+"|"+cid+"|"+symbol+"|M5|"+str(bar)+"|"+side).encode()).hexdigest()
  results.append({"signal_key":signal_key,"symbol":symbol,"side":side,"m5_bar_time":bar,
    "status":"RESEARCH_ONLY","execution_authorized":False,"trade_ready":False})
 return {"status":"RESEARCH_PREVIEW","blockers":["EXECUTOR_NOT_CERTIFIED",
   "PER_CLIENT_RISK_NOT_APPROVED","SINGLE_WRITER_CUTOVER_INCOMPLETE"],
   "candidates":results}
def fanout():
 OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
 with sqlite3.connect("file:"+DB+"?mode=ro",uri=True) as db:
  accounts=db.execute("""SELECT c.id,c.account_id,c.broker,c.environment,c.status,
       COALESCE(t.effective_enabled,0) FROM apex_mt5_connections c
       LEFT JOIN apex_trade_controls t ON t.connection_id=c.id
       WHERE c.status IN ('CONNECTED','CONNECTING') ORDER BY c.id""").fetchall()
 stats=[]
 for cid,owner,broker,env,status,effective in accounts:
  try:
   audit=json.loads((FEED/(cid+".json")).read_text())
   result=decision(audit,owner,cid)
  except (OSError,ValueError,TypeError):
   result={"status":"BLOCKED","blockers":["NO_CURRENT_NATIVE_FEED"],"candidates":[]}
  if status!="CONNECTED" or type(effective) is not int or effective not in (0,1):
   result={"status":"BLOCKED","blockers":["BROKER_DISCONNECTED_OR_CONTROL_INVALID"],"candidates":[]}
  doc={"schema":"abutron.apex.customer.signal_inbox.v1","updated_at_utc":iso(),
    "account_id":owner,"connection_id":cid,"broker":broker,"environment":env,
    "status":result["status"],"blockers":result["blockers"],
    "candidates":result["candidates"],"orders_submitted":0,"trading_enabled":False,
    "signal_to_order_linked":False,
    "route_candidate_schema":"abutron.apex.native.dispatch.v1",
    "potential_native_dispatcher_input":bool(result["candidates"]),
    "executable_without_account_authorization":False}
  atomic(OUT/(cid+".json"),doc)
  stats.append({"connection_id":cid,"status":doc["status"],
    "research_candidates":len(doc["candidates"]),"orders_submitted":0})
 atomic(OUT/"summary.json",{"schema":"abutron.apex.signal_fanout.shadow.v1",
  "updated_at_utc":iso(),"clients":len(stats),"orders_submitted":0,
  "trading_enabled":False,"execution_handover":"LOCKED","connections":stats})
 print("APEX_CLIENT_SHADOW_FANOUT","clients",len(stats),"order_count",0,
  "research_candidates",sum(x["research_candidates"] for x in stats))
if __name__=="__main__":fanout()
