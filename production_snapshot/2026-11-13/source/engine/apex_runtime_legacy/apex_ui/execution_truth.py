#!/usr/bin/python3
"""Read-only, account-bound execution truth for the existing APEX operator publisher.
Does not alter CRM switches, submit orders, or certify a future broker fill."""
import datetime as dt, json, os, pathlib, sqlite3, time
BASE=pathlib.Path('/var/lib/apex/operator-live')
CRM='/var/lib/apex-signup/accounts.sqlite3'
DERIV='/var/lib/abutron-deriv-multi-native-reconciliation/latest.json'
FP={
 '0512':('/var/lib/abutron-fp-execution/reconciliation/latest.json','/var/lib/apex/operator-live/fp-native-history.json','/var/lib/abutron-fp-execution/order-router/latest.json','/var/lib/abutron-fp-execution/order-router/order-journal.sqlite3'),
 '1636':('/var/lib/abutron-fp-execution/1636/reconciliation/latest.json','/var/lib/apex/operator-live/fp-native-history-account-80cf848587fcec6311dd93560c1c46c6.json','/var/lib/abutron-fp-execution/1636/order-router/latest.json','/var/lib/abutron-fp-execution/1636/order-router/order-journal.sqlite3'),
 '1622':('/var/lib/abutron-fp-execution/1622/reconciliation/latest.json','/var/lib/apex/operator-live/fp-native-history-account-14eef404262094655b2040c8ced86a53.json','/var/lib/abutron-fp-execution/1622/order-router/latest.json','/var/lib/abutron-fp-execution/1622/order-router/order-journal.sqlite3')
}
SUFFIXES=('6207','7593','9244','0512','1636','1622')
def doc(path,ttl=160):
 try:
  p=pathlib.Path(path);s=p.lstat()
  if p.is_symlink() or not p.is_file() or s.st_size>6000000 or not 0<=time.time()-s.st_mtime<ttl:return {}
  x=json.loads(p.read_text(encoding='utf-8'));return x if isinstance(x,dict) else {}
 except (OSError,ValueError,TypeError):return {}
def recent_fp_fills(suffix,history,ledger,now):
 if not isinstance(history.get('positions'),list) or not history.get('positions'):return 0
 try:
  with sqlite3.connect('file:'+ledger+'?mode=ro',uri=True,timeout=2) as c:
   rows=c.execute("SELECT broker_order_id,broker_deal_id FROM requests WHERE state='OPEN_PROTECTED' AND created_at>=?",(int(now)-900,)).fetchall()
  positions={str(x.get('ticket')):x for x in history['positions']}
  deals=history.get('trade_deals',[])
  valid=0
  for oid,did in rows:
   pos=positions.get(str(oid))
   if not pos or float(pos.get('stop_loss') or 0)<=0 or float(pos.get('take_profit') or 0)<=0:continue
   if any(str(d.get('ticket'))==str(did) and str(d.get('position_id'))==str(oid) and d.get('entry')=='IN' for d in deals):
    valid+=1
  return valid
 except (OSError,sqlite3.Error,ValueError,TypeError):return 0
def recent_deriv_fills(now):
 root=pathlib.Path('/var/lib/private/abutron-client-mt5-d6fc2524ec373b8d1bc278a8be3ec635/terminal/MQL5/Files/ABUTRON/receipts')
 status=doc(BASE/'native-status.json',165)
 positions={str(x.get('ticket')) for x in status.get('primary_account',{}).get('positions',[])}
 try:
  for path in sorted(root.glob('*.txt'),key=lambda p:p.stat().st_mtime,reverse=True)[:40]:
   if path.is_symlink() or not 0<=now-path.stat().st_mtime<=900:continue
   z=path.read_text(encoding='utf-8-sig').splitlines()
   if len(z)==10 and z[0]=='APEX_NATIVE_V2' and z[2]=='ACK' and z[4] in positions:
    return 1
 except (OSError,UnicodeError,ValueError):pass
 return 0
def build():
 now=time.time()
 with sqlite3.connect('file:'+CRM+'?mode=ro',uri=True,timeout=4) as c:
  data=c.execute("""SELECT substr(x.account_reference,-4),x.broker,x.environment,x.status,
       coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
       FROM apex_mt5_connections x JOIN apex_trade_controls t ON t.connection_id=x.id
       WHERE x.environment='DEMO'""").fetchall()
  leases=c.execute('SELECT revision,ack_revision,ack_expires_utc FROM abutron_v4_6207_activation_revision').fetchall()
 bysuffix={}
 for s,broker,env,connected,desired,effective in data:
  if s in SUFFIXES:bysuffix[s]=(broker,env,connected,bool(desired),bool(effective))
 deriv=doc(DERIV,150)
 derivmap={a.get('account_suffix'):a for a in deriv.get('accounts',[]) if isinstance(a,dict)}
 lease_ok=bool(len(leases)==1 and leases[0][0]==leases[0][1] and isinstance(leases[0][2],int) and leases[0][2]>int(now))
 accounts=[]
 for s in SUFFIXES:
  cfg=bysuffix.get(s)
  if not cfg:
   accounts.append({'account_suffix':s,'status':'CRM_ACCOUNT_NOT_VERIFIED','fully_operational_verified':False})
   continue
  broker,env,conn,desired,effective=cfg
  broker_ok=False; protected=False; npos=None; recent=0; router='NOT_OBSERVED'
  if broker=='Deriv':
   d=derivmap.get(s,{})
   broker_ok=bool(deriv.get('all_verified') is True and d.get('state')=='VERIFIED_READONLY')
   protected=bool(broker_ok and d.get('all_current_positions_sl_tp_usd_risk_verified') is True)
   npos=d.get('positions') if broker_ok else None
   if s=='6207':recent=recent_deriv_fills(now)
   router='CRM_ACK_CURRENT' if s=='6207' and lease_ok else ('CRM_ACK_NOT_CURRENT' if s=='6207' else 'NATIVE_DEMO_READONLY_RECONCILED')
  else:
   paths=FP[s];d=doc(paths[0],150);h=doc(paths[1],150);r=doc(paths[2],150)
   npos=h.get('open_positions_count')
   broker_ok=bool(d.get('status')=='RECONCILED_READONLY' and isinstance(npos,int) and d.get('broker_open_positions')==npos and h.get('pending_orders_count')==0)
   protected=bool(broker_ok and d.get('native_broker_open_risk_verified') is True and all(
    float(x.get('stop_loss') or 0)>0 and float(x.get('take_profit') or 0)>0 for x in h.get('positions',[])))
   recent=recent_fp_fills(s,h,paths[3],now) if broker_ok else 0
   router=r.get('status','ROUTER_STATUS_STALE')
   if r.get('blockers'):
    router=router+':'+str(r['blockers'][0])[:65]
  if not desired:state='CRM_REQUESTED_OFF'
  elif not effective:state='CRM_EFFECTIVE_OFF'
  elif conn!='CONNECTED':state='BROKER_CONNECTION_NOT_VERIFIED'
  elif not broker_ok or not protected:state='NATIVE_POSITION_OR_SLTP_UNVERIFIED'
  elif s=='6207' and not lease_ok:state='CURRENT_V4_AUTHORIZATION_ACK_MISSING'
  elif 'BLOCKED_NATIVE_DISPATCH' in router or 'PRIOR_NATIVE_REQUEST_UNRESOLVED' in router or 'FP_AUTOMATIC_TRADING_CONTROL_OFF' in router:state='BROKER_ROUTER_BLOCKED'
  elif recent>0:state='RECENT_BROKER_ACK_AND_PROTECTED_POSITION'
  elif 'SUBMITTED_TO_NATIVE_BRIDGE_AWAIT_BROKER_RECEIPT' in router:state='REQUEST_PENDING_BROKER_ACK'
  else:state='CRM_ON_NO_RECENT_BROKER_EXECUTION_PROOF'
  accounts.append({'account_suffix':s,'broker':broker,'environment':env,'crm_requested_on':desired,
     'crm_effective_on':effective,'broker_connected':conn=='CONNECTED','broker_positions':npos,
     'native_reconciliation_current':broker_ok,'broker_sl_tp_verified':protected,
     'recent_broker_fills_verified':recent,'router_observation':router,
     'trailing_stop_modification_verified_this_check':False,
     'status':state,'fully_operational_verified':state=='RECENT_BROKER_ACK_AND_PROTECTED_POSITION'})
 full=bool(len(accounts)==6 and all(a.get('fully_operational_verified') for a in accounts))
 return {'schema':'abutron.operator.execution_truth.v1',
   'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
   'all_demo_accounts_fully_operational_verified':full,
   'crm_effective_on_count':sum(a.get('crm_effective_on',False) for a in accounts),
   'accounts_with_recent_broker_fills':sum(a.get('recent_broker_fills_verified',0)>0 for a in accounts),
   'broker_native_execution_proof_is_not_equivalent_to_crm_on':True,
   'trailing_stop_proof_scope':'No fresh independently proven stop modification in this status report',
   'accounts':accounts}
if __name__=='__main__':print(json.dumps(build(),indent=2))
