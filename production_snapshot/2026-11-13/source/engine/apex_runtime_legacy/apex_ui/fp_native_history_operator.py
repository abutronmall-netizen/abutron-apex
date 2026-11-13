"""ABUTRON APEX protected operator FP Markets broker-native history API."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import json,os,stat,time
PATH=Path('/var/lib/apex/operator-live/fp-native-history.json')
SCHEMA='abutron.fpmarkets.native.account_history.readonly.v1'
def read(path=PATH,now=None):
 now=time.time() if now is None else float(now)
 try:
  st=path.lstat()
  if not stat.S_ISREG(st.st_mode) or st.st_size<150 or st.st_size>2_000_000:
   raise ValueError('FP_NATIVE_HISTORY_FILE_INVALID')
  fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
  try:
   before=os.fstat(fd);content=os.read(fd,2_000_001);after=os.fstat(fd)
  finally:os.close(fd)
  if (before.st_ino,before.st_mtime_ns,before.st_size)!=(
      after.st_ino,after.st_mtime_ns,after.st_size):
   raise ValueError('FP_NATIVE_HISTORY_FILE_CHANGED')
  doc=json.loads(content)
  stamp=datetime.fromisoformat(doc['generated_at_utc'].replace('Z','+00:00')).timestamp()
  if not (-30<=now-stamp<=180 and doc.get('schema')==SCHEMA
      and doc.get('available') is True and doc.get('history_verified_from_mt5') is True
      and doc.get('broker')=='FP Markets' and doc.get('environment')=='DEMO'
      and doc.get('account_currency')=='USD'
      and doc.get('execution_enabled') is False
      and doc.get('orders_submitted_by_exporter')==0
      and isinstance(doc.get('trade_deals'),list)
      and isinstance(doc.get('positions'),list)):
   raise ValueError('FP_NATIVE_HISTORY_UNVERIFIED')
  return doc
 except (OSError,ValueError,TypeError,OverflowError,KeyError,UnicodeError):
  return {'schema':SCHEMA,'available':False,'broker':'FP Markets',
    'reason':'FP broker-native positions/deals unavailable or stale',
    'history_verified_from_mt5':False,
    'execution_enabled':False,'positions':[],'trade_deals':[],'pending_orders':[]}
