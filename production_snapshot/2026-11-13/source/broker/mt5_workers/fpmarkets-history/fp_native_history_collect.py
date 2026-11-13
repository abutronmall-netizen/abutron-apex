#!/usr/bin/python3
"""ABUTRON FP Markets authenticated broker-native positions/orders/deal reader.

No MT5 IPC or order APIs; reads native MQL5 proof under the isolated FP terminal.
No inference from scanner signals. Broker-verified empty sets are real zeros.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import csv,hashlib,json,math,os,pwd,grp,sqlite3,stat,tempfile,time

DB=Path('/var/lib/apex-signup/accounts.sqlite3')
CID='35b81a287b6a030f2f46ff426b135e6c' # Broker-specific readonly history target
PRIVATE=Path('/var/lib/private')
OPERATOR=Path('/var/lib/apex/operator-live/fp-native-history.json')
CLIENT=Path('/var/lib/apex-signup/fp-native-history')
MAGIC='ABUTRON_FP_ACCOUNT_HISTORY_V1'
SCHEMA='abutron.fpmarkets.native.account_history.readonly.v1'
HEADER_LINES=20
MAX_BYTES=4_000_000
MAX_DEALS=10000
HORIZON_DAYS=90

def assert_ok(condition,code):
 if not condition:raise ValueError(code)

def integer(value):
 n=int(str(value))
 assert_ok(str(n)==str(value) and n>=0,'FP_HISTORY_INTEGER_INVALID')
 return n

def real(value):
 x=float(value)
 assert_ok(math.isfinite(x),'FP_HISTORY_NONFINITE_VALUE')
 return x

def time_iso(value,offset=0):
 return datetime.fromtimestamp(value-offset,timezone.utc).isoformat()

def source_bytes(path):
 st=path.lstat()
 assert_ok(stat.S_ISREG(st.st_mode) and 100<=st.st_size<=MAX_BYTES,
           'FP_HISTORY_SOURCE_FILE_MISSING_OR_SIZE')
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 try:
  before=os.fstat(fd);body=os.read(fd,MAX_BYTES+1);after=os.fstat(fd)
 finally:os.close(fd)
 assert_ok((before.st_ino,before.st_mtime_ns,before.st_size)==
           (after.st_ino,after.st_mtime_ns,after.st_size) and len(body)<=MAX_BYTES,
           'FP_HISTORY_INCOMPLETE_SOURCE_READ')
 return body

def broker_account(db=DB):
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=6) as conn:
  conn.execute('PRAGMA query_only=ON')
  rows=conn.execute("""SELECT a.id,a.account_id,a.account_reference,a.broker_server,
    coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
    FROM apex_mt5_connections a LEFT JOIN apex_trade_controls t ON t.connection_id=a.id
    WHERE a.broker='FP Markets' AND a.environment='DEMO'
    AND a.broker_server='FPMarketsSC-Demo' AND a.status='CONNECTED' AND a.id=?""",(CID,)).fetchall()
 assert_ok(len(rows)==1,'FP_HISTORY_CONNECTED_DEMO_NOT_UNIQUE')
 cid,account,login,server,desired,effective=rows[0]
 assert_ok(type(cid) is str and len(cid)==32 and type(account) is str and len(account)==32,
           'FP_HISTORY_IDS_INVALID')
 assert_ok(desired in (0,1) and effective in (0,1),'FP_HISTORY_TRADING_FLAGS_INVALID')
 return cid,account,str(login),str(server)

def worker_proof(cid,login,server,private=PRIVATE,now=None):
 now=time.time() if now is None else float(now)
 home=private/('abutron-client-mt5-'+cid)
 health=json.loads((home/'worker-health.json').read_text())
 assert_ok(health.get('id')==cid and health.get('server')==server
    and health.get('mode')=='DEMO' and health.get('broker')=='FP Markets'
    and health.get('status')=='CONNECTED' and health.get('heartbeat_fresh') is True,
    'FP_HISTORY_WORKER_NOT_CONNECTED')
 nonce=health.get('nonce');owner=health.get('proof_owner')
 assert_ok(type(nonce) is str and len(nonce)==32 and
    all(c in '0123456789abcdef' for c in nonce)
    and type(owner) is str and len(owner)==36,
    'FP_HISTORY_NONCE_INVALID')
 hb=home/'terminal/MQL5/Files'/('ABUTRON_SESSION_HEARTBEAT_V1_'+nonce+'.txt')
 st=hb.lstat()
 assert_ok(stat.S_ISREG(st.st_mode) and -15<=now-st.st_mtime<=20,
           'FP_HISTORY_WORKER_HEARTBEAT_STALE')
 expected=['ABUTRON_MT5_NATIVE_HEARTBEAT_V1',nonce,owner,'FP_MARKETS',
           server,'DEMO','CONNECTED','NO_ORDER_FUNCTIONS']
 assert_ok(hb.read_text(encoding='utf-8-sig').splitlines()==expected,
           'FP_HISTORY_WORKER_HEARTBEAT_UNTRUSTED')

 # The separate weekend-safe V101 indicator must be the exact QA-compiled
 # NO-ORDER binary, not a mutable scanner or stale V100 exporter.
 approved=home/'terminal/MQL5/Indicators/ABUTRON/ABUTRON-FP-HISTORY-V101-READONLY/AbutronFPAccountHistoryV101.ex5'
 assert_ok(hashlib.sha256(source_bytes(approved)).hexdigest()==
   ('3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac' if cid=='80cf848587fcec6311dd93560c1c46c6' else '3157811099558f6fd140a11d7b8047cc466b0130043d5a02b441ef095a1007ac'),
   'FP_HISTORY_V101_BINARY_UNATTESTED')
 return home,nonce,owner

def parse_native(payload,*,nonce,owner,login,server,now=None):
 now=time.time() if now is None else float(now)
 lines=payload.decode('utf-8-sig').splitlines()
 assert_ok(len(lines)>=HEADER_LINES+1,'FP_HISTORY_EXPORT_SHORT')
 assert_ok(lines[0:6]==[MAGIC,nonce,owner,server,login,'DEMO'],
           'FP_HISTORY_ACCOUNT_BINDING_MISMATCH')
 stamp=integer(lines[6]);offset=int(lines[7])
 assert_ok(-30<=now-stamp<=140,'FP_HISTORY_EXPORT_STALE')
 assert_ok(offset==7200,'FP_HISTORY_BROKER_SERVER_UTC_OFFSET_INVALID')
 assert_ok(lines[8]=='USD','FP_HISTORY_NOT_USD_ACCOUNT')
 account_fields=dict(zip(('balance','equity','margin','free_margin','floating_profit'),
                        [real(v) for v in lines[9:14]]))
 expected_counts=[integer(x) for x in lines[14:17]]
 begin=integer(lines[17]);end=integer(lines[18])
 # The broker's TimeCurrent may stop advancing during weekend market closure.
 # Never silently treat a newly written export as fresh trading-history proof.
 # Distinguish a genuinely stale broker-clock end from malformed export data.
 assert_ok(lines[19]=='BROKER_NATIVE_NO_ORDER_FUNCTIONS',
           'FP_HISTORY_ORDER_FUNCTIONS_PROHIBITED')
 assert_ok(0<end-begin<=91*86400 and begin<=end,
           'FP_HISTORY_WINDOW_INVALID')
 assert_ok(end-offset<=now+1_000_000,
           'FP_HISTORY_BROKER_CLOCK_AHEAD')
 assert_ok(end-offset>=now-86400,
           'FP_HISTORY_BROKER_CLOCK_STALE')
 assert_ok(expected_counts[0]<=500 and expected_counts[1]<=500 and
           expected_counts[2]<=MAX_DEALS,'FP_HISTORY_TOO_MANY_RECORDS')
 assert_ok(lines[-1]==('END\t'+'\t'.join(str(x) for x in expected_counts)),
           'FP_HISTORY_EXPORT_END_SENTINEL_MISMATCH')
 records=lines[HEADER_LINES:-1]
 assert_ok(len(records)==sum(expected_counts),'FP_HISTORY_EXPORT_RECORD_COUNT_MISMATCH')
 positions=[];pending=[];deals=[];seen={'P':set(),'O':set(),'D':set()}
 for line in records:
  parts=line.split('\t');kind=parts[0]
  assert_ok(kind in seen,'FP_HISTORY_UNKNOWN_RECORD_TYPE')
  assert_ok(len(parts)==({'P':13,'O':11,'D':15}[kind]),
            'FP_HISTORY_RECORD_COLUMN_MISMATCH')
  ticket=integer(parts[1]);assert_ok(ticket>0 and ticket not in seen[kind],
     'FP_HISTORY_DUPLICATE_TICKET')
  seen[kind].add(ticket)
  if kind=='P':
   _,_,symbol,p_type,volume,price_open,current,sl,tp,profit,swap,opened,updated=parts
   assert_ok(p_type in ('0','1') and
       1<=len(symbol)<=60,'FP_HISTORY_POSITION_TYPE_OR_SYMBOL_INVALID')
   values=[real(z) for z in (volume,price_open,current,sl,tp,profit,swap)]
   assert_ok(values[0]>0 and values[1]>0 and values[2]>0 and values[3]>=0 and values[4]>=0,
      'FP_HISTORY_POSITION_VALUES_INVALID')
   opened=integer(opened);updated=integer(updated)
   assert_ok(opened<=updated and updated<now+1_000_000,'FP_HISTORY_POSITION_CLOCK_INVALID')
   positions.append({'ticket':str(ticket),'symbol':symbol,'side':'BUY' if p_type=='0' else 'SELL',
      'volume':values[0],'open_price':values[1],'current_price':values[2],
      'stop_loss':values[3] or None,'take_profit':values[4] or None,
      'floating_profit_usd':values[5],'swap_usd':values[6],
      'opened_broker_time':opened,'opened_at_utc':time_iso(opened,offset),
      'updated_at_utc':time_iso(updated,offset)})
  elif kind=='O':
   _,_,symbol,otype,state,initial,current,price,sl,tp,when=parts
   assert_ok(1<=len(symbol)<=60,'FP_HISTORY_ORDER_SYMBOL_INVALID')
   values=[real(z) for z in (initial,current,price,sl,tp)]
   assert_ok(values[0]>0 and values[1]>=0,'FP_HISTORY_ORDER_VOLUME_INVALID')
   pending.append({'ticket':str(ticket),'symbol':symbol,'order_type_code':integer(otype),
       'state_code':integer(state),'initial_volume':values[0],
       'remaining_volume':values[1],'order_price':values[2],
       'stop_loss':values[3] or None,'take_profit':values[4] or None,
       'created_at_utc':time_iso(integer(when),offset)})
  else:
   _,_,order_id,position_id,when,typ,entry,reason,symbol,vol,price,profit,commission,fee,swap=parts
   typeid=integer(typ);entryid=integer(entry)
   assert_ok(0<=typeid<30 and 0<=entryid<10,'FP_HISTORY_DEAL_TYPE_INVALID')
   assert_ok(len(symbol)<=60,'FP_HISTORY_DEAL_SYMBOL_INVALID')
   values=[real(z) for z in (vol,price,profit,commission,fee,swap)]
   assert_ok(values[0]>=0,'FP_HISTORY_DEAL_NEGATIVE_VOLUME')
   ts=integer(when)
   assert_ok(begin-7200-86400<=ts<=end+86400,'FP_HISTORY_DEAL_OUTSIDE_WINDOW')
   details={'ticket':str(ticket),'order_id':str(integer(order_id)),
      'position_id':str(integer(position_id)),'symbol':symbol,
      'side':'BUY' if typeid==0 else 'SELL' if typeid==1 else 'ACCOUNT_EVENT',
      'deal_type_code':typeid,'entry':{0:'IN',1:'OUT',2:'INOUT',3:'OUT_BY'}.get(entryid,'OTHER'),
      'reason_code':integer(reason),'volume':values[0],'price':values[1],
      'profit_usd':values[2],'commission_usd':values[3],
      'fee_usd':values[4],'swap_usd':values[5],
      'net_cashflow_usd':round(sum(values[2:]),2),
      'broker_time':ts,'time_utc':time_iso(ts,offset)}
   deals.append(details)
 assert_ok([len(positions),len(pending),len(deals)]==expected_counts,
    'FP_HISTORY_BROKER_COUNTS_NOT_MATCHED')
 trade_deals=[x for x in deals if x['deal_type_code'] in (0,1)]
 trade_deals.sort(key=lambda x:(x['broker_time'],int(x['ticket'])),reverse=True)
 closings=[x for x in trade_deals if x['entry'] in ('OUT','OUT_BY','INOUT')]
 positions.sort(key=lambda x:int(x['ticket']),reverse=True)
 pending.sort(key=lambda x:int(x['ticket']),reverse=True)
 return {'schema':SCHEMA,'available':True,'broker':'FP Markets','environment':'DEMO',
  'account_masked':'••••'+login[-4:],'account_currency':'USD',
  'generated_at_utc':time_iso(int(now)),
  'broker_export_at_utc':time_iso(stamp),
  'broker_clock_offset_seconds':offset,
  'source':'Authenticated FP Markets MT5 PositionsTotal + OrdersTotal + HistorySelect/HistoryDealsTotal',
  'history_window_days':HORIZON_DAYS,
  'history_from_broker_time':begin,'history_to_broker_time':end,
  'balance_usd':round(account_fields['balance'],2),
  'equity_usd':round(account_fields['equity'],2),
  'margin_usd':round(account_fields['margin'],2),
  'free_margin_usd':round(account_fields['free_margin'],2),
  'account_floating_profit_usd':round(account_fields['floating_profit'],2),
  'open_positions_count':len(positions),'pending_orders_count':len(pending),
  'broker_deals_count':len(deals),'trade_deals_count':len(trade_deals),
  'closing_deals_count':len(closings),
  'closing_deal_cashflow_usd':round(sum(x['net_cashflow_usd'] for x in closings),2),
  'total_trade_deal_cashflow_usd':round(sum(x['net_cashflow_usd'] for x in trade_deals),2),
  'cashflow_note':'Deal-level cashflow includes broker profit, commission, fee and swap. Entry costs are shown on their entry deals. This is not strategy-level net performance or a complete account statement.',
  'history_complete_within_selected_window':True,
  'history_trade_deals_shown':min(len(trade_deals),300),
  'execution_enabled':False,'orders_submitted_by_exporter':0,
  'positions':positions,'pending_orders':pending,'trade_deals':trade_deals[:300],
  'history_verified_from_mt5':True}

def snapshot(*,db=DB,private=PRIVATE,now=None):
 now=time.time() if now is None else float(now)
 cid,owner,login,server=broker_account(db)
 root,nonce,proof_owner=worker_proof(cid,login,server,private=private,now=now)
 p=root/'terminal/MQL5/Files'/('ABUTRON_FP_ACCOUNT_HISTORY_V101_'+nonce+'.txt')
 raw=source_bytes(p)
 doc=parse_native(raw,nonce=nonce,owner=proof_owner,login=login,server=server,now=now)
 doc['native_file_sha256']=hashlib.sha256(raw).hexdigest()
 doc['producer_build']='FP_HISTORY_V101_READONLY_TIMETRADESERVER_ESTIMATED'
 doc['broker_history_window_end_clock']='TERM_CLOCK_ESTIMATED_BOUNDED_UTC_OFFSET'
 doc['market_quote_fresh_for_execution']=False
 doc['broker_execution_ack_certified']=False
 doc['customer_portfolio_risk_certified']=False
 return cid,owner,doc

def atomic(path,doc,uid,gid):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=str(path.parent),prefix='.fp-history-')
 try:
  with os.fdopen(fd,'w') as h:
   json.dump(doc,h,separators=(',',':'),allow_nan=False)
   h.flush();os.fsync(h.fileno())
  os.chown(tmp,uid,gid);os.chmod(tmp,0o640);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def publish():
 now=time.time()
 cid,owner,doc=snapshot(now=now)
 op_gid=grp.getgrnam('apexagent').gr_gid
 client_uid=pwd.getpwnam('apexsignup').pw_uid
 client_gid=grp.getgrnam('apexsignup').gr_gid
 CLIENT.mkdir(parents=True,exist_ok=True)
 os.chown(CLIENT,client_uid,client_gid);os.chmod(CLIENT,0o700)
 atomic(OPERATOR,doc,0,op_gid)
 atomic(CLIENT/(cid+'.json'),doc,client_uid,client_gid)
 return {'status':'FP_NATIVE_ACCOUNT_HISTORY_VERIFIED',
   'positions':doc['open_positions_count'],'pending_orders':doc['pending_orders_count'],
   'broker_deals_90d':doc['broker_deals_count'],
   'trade_deals_90d':doc['trade_deals_count'],
   'history_from_mt5':True,'exporter_orders':0}

if __name__=='__main__':
 try:print(json.dumps(publish(),sort_keys=True))
 except (OSError,ValueError,TypeError,OverflowError,IndexError,KeyError,sqlite3.Error) as exc:
  print('FP_NATIVE_HISTORY_BLOCKED',str(exc)[:155])
  raise SystemExit(1)
