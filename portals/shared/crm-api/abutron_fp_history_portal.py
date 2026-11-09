"""FP Markets authenticated, broker-native deal and position history for client portal.

Read-only, strict owner scoping and MFA-protected admin summary. No mutations.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import json,os,re,sqlite3,stat,time
ROOT=Path('/var/lib/apex-signup/fp-native-history')
SCHEMA='abutron.fpmarkets.native.account_history.readonly.v1'
CID=re.compile(r'^[0-9a-f]{32}$')

def verified(path,now=None):
 now=time.time() if now is None else float(now)
 st=path.lstat()
 if not stat.S_ISREG(st.st_mode) or not 150<=st.st_size<=2_000_000:
  raise ValueError('FP_HISTORY_FILE_UNTRUSTED')
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 try:
  pre=os.fstat(fd);body=os.read(fd,2_000_001);post=os.fstat(fd)
 finally:os.close(fd)
 if (pre.st_ino,pre.st_size,pre.st_mtime_ns)!=(post.st_ino,post.st_size,post.st_mtime_ns):
  raise ValueError('FP_HISTORY_SNAPSHOT_CHANGED')
 doc=json.loads(body)
 try:stamp=datetime.fromisoformat(str(doc['generated_at_utc']).replace('Z','+00:00')).timestamp()
 except (TypeError,KeyError,ValueError,OverflowError) as e:raise ValueError('FP_HISTORY_TIMESTAMP_INVALID') from e
 if not (-30<=now-stamp<=180 and doc.get('schema')==SCHEMA and
      doc.get('available') is True and doc.get('history_verified_from_mt5') is True
      and doc.get('account_currency')=='USD' and
      doc.get('environment')=='DEMO' and doc.get('broker')=='FP Markets'
      and doc.get('execution_enabled') is False and
      doc.get('orders_submitted_by_exporter')==0
      and doc.get('history_window_days')==90
      and isinstance(doc.get('positions'),list)
      and isinstance(doc.get('trade_deals'),list)
      and len(doc.get('positions'))==doc.get('open_positions_count')
      and len(doc.get('trade_deals'))==doc.get('history_trade_deals_shown')):
  raise ValueError('FP_HISTORY_UNTRUSTED_OR_STALE')
 return doc

def client_snapshot(connect,owner,root=ROOT):
 with connect() as c:
  c.execute('PRAGMA query_only=ON')
  rows=c.execute("""SELECT id,account_reference FROM apex_mt5_connections
   WHERE account_id=? AND broker='FP Markets' AND status='CONNECTED'
   AND environment='DEMO' AND broker_server='FPMarketsSC-Demo'""",(owner,)).fetchall()
 if not rows:
  return {'available':False,'broker':'FP Markets','reason':'NO_CONNECTED_FP_DEMO_ACCOUNT',
          'native_history_verified':False}
 if len(rows)>1:raise ValueError('FP_HISTORY_OWNER_AMBIGUOUS')
 cid,login=rows[0]
 if not isinstance(cid,str) or CID.fullmatch(cid) is None:raise ValueError('FP_HISTORY_ACCOUNT_ID_INVALID')
 if not isinstance(login,str) or not login.isdigit():raise ValueError('FP_HISTORY_LOGIN_INVALID')
 try:
  doc=verified(root/(cid+'.json'))
  if doc.get('account_masked')!='••••'+login[-4:]:
   raise ValueError('FP_HISTORY_CLIENT_ACCOUNT_BINDING_INVALID')
  return doc
 except (OSError,ValueError,TypeError,OverflowError,KeyError,json.JSONDecodeError):
  return {'available':False,'broker':'FP Markets',
          'reason':'FP_NATIVE_HISTORY_NOT_YET_VERIFIED','native_history_verified':False}

def admin_snapshot(connect,root=ROOT):
 """MFA-only independent summaries; never merge two clients' deal totals."""
 with connect() as c:
  c.execute('PRAGMA query_only=ON')
  rows=c.execute("""SELECT id,account_reference FROM apex_mt5_connections
   WHERE broker='FP Markets' AND status='CONNECTED' AND
     environment='DEMO' AND broker_server='FPMarketsSC-Demo'
   ORDER BY id LIMIT 9""").fetchall()
 if not rows:
  return {'available':False,'broker':'FP Markets','reason':'NO_CONNECTED_FP_DEMO_ACCOUNT'}
 if len(rows)>8:raise ValueError('FP_HISTORY_ADMIN_UNEXPECTED_ACCOUNT_COUNT')
 records=[]
 for cid,login in rows:
  if not isinstance(cid,str) or CID.fullmatch(cid) is None:
   raise ValueError('FP_HISTORY_ACCOUNT_ID_INVALID')
  if not isinstance(login,str) or not login.isdigit():
   raise ValueError('FP_HISTORY_ACCOUNT_REFERENCE_INVALID')
  label='••••'+login[-4:]
  try:
   doc=verified(root/(cid+'.json'))
   if doc.get('account_masked')!=label:
    raise ValueError('FP_HISTORY_CROSS_ACCOUNT_DATA_MISMATCH')
   records.append({k:doc.get(k) for k in (
     'available','broker','environment','account_masked','account_currency',
     'generated_at_utc','history_window_days','balance_usd','equity_usd',
     'account_floating_profit_usd','open_positions_count','pending_orders_count',
     'broker_deals_count','trade_deals_count','closing_deals_count',
     'closing_deal_cashflow_usd','history_complete_within_selected_window')})
  except (OSError,ValueError,TypeError,KeyError,OverflowError):
   records.append({'available':False,'account_masked':label,
                   'reason':'FP_NATIVE_HISTORY_NOT_YET_VERIFIED'})
 return {'schema':'abutron.fpmarkets.native.admin_history.multi.readonly.v1',
         'available':any(r['available'] for r in records),
         'broker':'FP Markets','environment':'DEMO',
         'account_count':len(records),'accounts':records,
         'all_accounts_history_verified':all(r['available'] for r in records),
         'execution_enabled':False,'orders_submitted':0}
