#!/usr/bin/env python3
"""ABUTRON APEX final migration cutover gate - evidence ONLY, cannot enable orders."""
import os,json,sqlite3,subprocess,time,tempfile,datetime
from pathlib import Path
ROOT=Path("/var/lib/apex-client-feed")
DB="/var/lib/apex-signup/accounts.sqlite3"
SRC_STATE=Path("/var/backups/apex-full-migration-20261101/pre-shutdown-20261101-2132UTC/source-state")
CUTOVER=Path("/var/lib/apex/migration-gates/BROKER_AND_POSITION_HANDOVER_APPROVED")
def load(path):
 try:return json.loads(path.read_text())
 except (ValueError,OSError,TypeError):return {}
def active_service(name):
 p=subprocess.run(["systemctl","is-active",name],capture_output=True,text=True,timeout=4)
 return p.returncode==0 and p.stdout.strip()=="active"
def write(path,value):
 fd,tmp=tempfile.mkstemp(dir=str(path.parent),prefix=".handover-")
 try:
  with os.fdopen(fd,"w") as f:
   json.dump(value,f,indent=2,allow_nan=False)
   f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o600);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def inspect():
 feed=load(ROOT/"summary.json")
 shadow=load(ROOT/"inboxes/summary.json")
 root_apex=load(Path("/var/lib/apex-shadow/health.json"))
 with sqlite3.connect("file:"+DB+"?mode=ro",uri=True) as db:
  connected=db.execute("SELECT COUNT(*) FROM apex_mt5_connections WHERE status='CONNECTED'").fetchone()[0]
  auto=db.execute("SELECT COUNT(*) FROM apex_trade_controls WHERE effective_enabled=1").fetchone()[0]
  integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
  plans=db.execute("SELECT COUNT(*) FROM apex_crm_licenses WHERE status='active'").fetchone()[0]
 # Verify the owner has a fresh authenticated Deriv DEMO broker-native
 # account snapshot, not merely a user assertion or a historical file.
 owner_native_flat=False
 owner_native_apex_research_verified=False
 historical_close_deals_verified=False
 # Verify historical broker deal closure independently of order-execution state.
 # Current broker flatness and trading readiness are separate mandatory checks.
 try:
  from superadmin_apex_deal_history_v1 import verify as verify_owner_deals
  historical_close_deals_verified=verify_owner_deals().get("historical_close_deals_verified") is True
 except (ValueError,TypeError,KeyError,FileNotFoundError,OSError,sqlite3.Error):
  historical_close_deals_verified=False
 owner_proof=load(Path("/var/lib/apex-client-feed/evidence/owner-flat-reconciliation.json"))
 try:
  with sqlite3.connect("file:"+DB+"?mode=ro",uri=True) as db:
   row=db.execute("""SELECT c.id,c.account_id,c.status,c.broker,c.environment,
       c.broker_server,c.account_reference FROM apex_mt5_connections c
       JOIN accounts a ON a.id=c.account_id WHERE lower(a.email)=?""",
       ("abutroncloud@gmail.com",)).fetchone()
  if row and row[2:6]==("CONNECTED","Deriv","DEMO","Deriv-Demo"):
   cid,owner=row[:2]
   clientfeed=load(ROOT/(cid+".json"))
   checked=datetime.datetime.fromisoformat(str(clientfeed.get("checked_at_utc")).replace("Z","+00:00"))
   age=(datetime.datetime.now(datetime.timezone.utc)-checked).total_seconds()
   account=clientfeed.get("account",{})
   owner_native_flat=bool(
     -15<=age<=150 and clientfeed.get("connection_id")==cid
     and clientfeed.get("account_id")==owner
     and clientfeed.get("status")=="BROKER_DATA_VERIFIED_SHADOW"
     and clientfeed.get("broker_data_verified") is True
     and account.get("open_positions")==0
     and account.get("positions")==[]
     and owner_proof.get("current_open_exposure_status")=="FLAT_BROKER_VERIFIED"
     and owner_proof.get("mt5_login_suffix")==str(row[6])[-4:])
   # The retired local shadow API is deliberately non-executing; its status
   # cannot be an approval input for the current per-customer APEX research.
   # Confirm actual fresh broker candles, 13 scanner outputs and tenant-bound
   # research inbox. Zero BUY/SELL candidates is valid during HOLD markets.
   inbox=load(ROOT/"inboxes"/(cid+".json"))
   research_at=datetime.datetime.fromisoformat(str(inbox.get("updated_at_utc")).replace("Z","+00:00"))
   research_age=(datetime.datetime.now(datetime.timezone.utc)-research_at).total_seconds()
   bars_at=datetime.datetime.fromisoformat(str(clientfeed.get("market_data_generated_utc")).replace("Z","+00:00"))
   bars_age=(datetime.datetime.now(datetime.timezone.utc)-bars_at).total_seconds()
   signals=clientfeed.get("signal_preview")
   owner_native_apex_research_verified=bool(
     owner_native_flat and -15<=bars_age<=150 and -15<=research_age<=150
     and clientfeed.get("symbol_count")==13
     and clientfeed.get("timeframes_per_symbol")==6
     and clientfeed.get("apex_strategy")=="apex_ema_rsi_mtf_research_v1"
     and clientfeed.get("strategy_status")=="RESEARCH_ONLY"
     and isinstance(signals,list) and len(signals)==13
     and all(isinstance(q,dict) and q.get("proposal") in ("BUY","SELL","HOLD") for q in signals)
     and inbox.get("status")=="RESEARCH_PREVIEW"
     and inbox.get("account_id")==owner and inbox.get("connection_id")==cid)
 except (sqlite3.Error,ValueError,KeyError,TypeError,AttributeError,OverflowError):
  owner_native_flat=False
 statuses={
  "website_client_portal_active":active_service("apex-client-portal.service"),
  "dedicated_mt5_manager_active":active_service("abutron-client-mt5-manager.service"),
  "apex_local_shadow_active":active_service("apex-destination-shadow.timer"),
  "native_broker_feed_audit_active":active_service("abutron-client-native-feed.timer"),
  "tenant_signal_shadow_fanout_active":active_service("abutron-client-shadow-fanout.timer"),
  "local_database_integrity":integrity=="ok",
  "connected_customer_mt5_sessions":connected,
  "active_crm_licenses":plans,
  "verified_customer_broker_candle_position_feeds":feed.get("verified_native_market_feeds",0),
  "verified_owner_position_handover":owner_native_flat,
  "owner_native_apex_research_and_market_data_verified":owner_native_apex_research_verified,
  "historical_close_deals_verified":historical_close_deals_verified,
  "source_single_writer_shutdown_last_verified":False, # remote source cannot be assumed current
  "independent_risk_approval_granted":False,
  "fresh_qualified_apex_execution_signal":False,
  "customer_execution_permissions_enabled":auto,
  "destination_apex_order_service_running":active_service("abutron-apex-native-orders.timer"),
  "destination_cutover_gate_exists":CUTOVER.exists(),
  "source_recovery_copy_present":SRC_STATE.is_dir(),
  "source_server_required_for_customer_portal":False,
  "old_owner_apex_shadow_status":root_apex.get("status"),
  "source_candle_snapshot_fresh":False,
  "apex_research_inbox_clients":shadow.get("clients",0),
  "read_only_signal_orders_submitted":shadow.get("orders_submitted",0)
 }
 blockers=[]
 if connected<1:blockers.append("NO_VERIFIED_BROKER_SESSIONS")
 if feed.get("verified_native_market_feeds",0)<connected:
  blockers.append("CUSTOMER_NATIVE_CANDLE_AND_POSITION_FEEDS_NOT_COMPLETE")
 if not owner_native_apex_research_verified:
  blockers.append("APEX_OWNER_NATIVE_RESEARCH_AND_MARKET_DATA_NOT_VERIFIED")
 if not owner_native_flat:blockers.append("CURRENT_OWNER_BROKER_POSITIONS_NOT_RECONCILED")
 if not historical_close_deals_verified:blockers.append("HISTORICAL_APEX_CLOSING_DEALS_NOT_MATCHED")
 blockers+=["INDEPENDENT_ACCOUNT_RISK_APPROVAL_MISSING",
  "PER_CUSTOMER_ORDER_EXECUTOR_NOT_BROKER_TESTED",
  "SINGLE_WRITER_CUTOVER_NOT_AUTHORIZED"]
 if not statuses["local_database_integrity"]:blockers.append("DATABASE_INTEGRITY_FAILED")
 if auto!=0:blockers.append("UNEXPECTED_EFFECTIVE_TRADING_ENABLEMENT")
 summary={
  "schema":"abutron.apex.production.handover.readiness.v1",
  "checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "platform":"ABUTRONFX.ONLINE",
  "status":"NOT_APPROVED_FOR_TRADING_CUTOVER",
  "actual_orders_sent_by_this_audit":0,
  "action_taken":"READ_ONLY_REPORT_ONLY",
  "root_execution_gate_created":False,
  "criteria":statuses,"blockers":blockers
 }
 ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
 write(ROOT/"handover-readiness.json",summary)
 print("APEX_HANDOVER","NOT_APPROVED",len(blockers),"blockers",
       "MT5_CONNECTED",connected,"NATIVE_FEEDS",feed.get("verified_native_market_feeds",0),
       "ORDERS",0)
 return summary
if __name__=="__main__":inspect()
