#!/usr/bin/python3
"""Existing APEX11 preflight -> native V4 request transport for Deriv DEMO 7593/9244.
Uses original APEX M5 decisions, native MT5 OrderCheck and existing CRM account switch.
One request per account at a time. No new strategies, vetoes or approval processes.
"""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, sqlite3, stat, sys, time
from pathlib import Path
sys.path.insert(0,"/opt/apex-client-mt5/deriv-execution")
import deriv_v4_guard as existing_native

ACCOUNTS=existing_native.ACCOUNTS
CRM=existing_native.CRM
class Refused(Exception):pass

def root_dir(s):return Path("/var/lib/abutron-deriv-v4-"+s)
def draft_path(s):return Path("/var/lib/abutron-apex11-"+s+"/exact-order-draft-latest.json")
def log_result(s,state,**kw):
 obj=dict(account=s,checked_unix=int(time.time()),state=state,**kw)
 directory=root_dir(s)
 tmp=directory/(".writer-report-"+str(os.getpid()))
 with tmp.open("x",encoding="utf-8") as f:
  os.chmod(tmp,0o600)
  json.dump(obj,f,sort_keys=True,separators=(",",":"));f.write("\n");f.flush();os.fsync(f.fileno())
 os.replace(tmp,directory/"writer-latest.json")
 print(json.dumps(obj,sort_keys=True))
def fresh_file(path,age=40,limit=200000):
 p=Path(path)
 if p.is_symlink():raise Refused("SYMLINK_SOURCE")
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  st=os.fstat(fd)
  if not stat.S_ISREG(st.st_mode) or st.st_size<8 or st.st_size>limit or st.st_mode&0o022 or not -2<=time.time()-st.st_mtime<=age:
   raise Refused("INVALID_SOURCE_FRESHNESS_OR_MODE")
  b=os.read(fd,limit+1)
  if len(b)!=st.st_size:raise Refused("RACED_SOURCE")
  return b
 finally:os.close(fd)
def file_from_account(s,a):
 folder=existing_native.terminal_files(a)/"ABUTRON"
 if folder.is_symlink() or not folder.is_dir():raise Refused("NATIVE_FILES_UNAVAILABLE")
 return folder
def native_session(s,a):
 existing_native.deployed_v4(a)
 h,risk=existing_native.native_report(s,a)
 with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=5) as db:
  owner,rev=existing_native.crm_row(db,s,a)
 existing_native.capability(a,h,rev)
 return h,risk,owner,rev

def receipt_lineage(s,a,signal):
 """One immutable EA receipt + matching independently authenticated broker ticket."""
 folder=file_from_account(s,a)
 receipt=folder/"receipts"/(signal+".txt")
 if not receipt.is_file():return None
 lines=fresh_file(receipt,86400,2048).decode("utf-8-sig").splitlines()
 if (len(lines)!=10 or lines[0]!="APEX_NATIVE_V2" or lines[1]!=signal or
     lines[2] not in ("ACK","BLOCKED","UNKNOWN") or
     lines[7] not in (hnonce(a),) or lines[8]!=a["login"] or lines[9]!="Deriv-Demo"):
  raise Refused("NATIVE_RECEIPT_ACCOUNT_OR_PROTOCOL_INVALID")
 status=lines[2]
 if status=="BLOCKED":return dict(status="BLOCKED",reason=lines[3][:110])
 if status=="UNKNOWN":return dict(status="UNKNOWN",reason=lines[3][:110])
 if not(lines[4].isdigit() and lines[5].isdigit() and int(lines[4])>0 and int(lines[5])>0):
  raise Refused("ACK_WITHOUT_BROKER_ORDER_AND_DEAL")
 return dict(status="ACK",order=int(lines[4]),deal=int(lines[5]),reason=lines[3][:100])

def hnonce(a):
 h=existing_native.fresh_json(existing_native.source_worker(a),25)
 return h["nonce"]

def same_broker_volume(native_position_volume,native_deal_volume):
 # MT5 serializes equal lot quantities with different trailing zeros.
 # Decimal equality preserves exact broker volume without rounding tolerance.
 from decimal import Decimal,InvalidOperation
 try:
  left=Decimal(str(native_position_volume))
  right=Decimal(str(native_deal_volume))
  return left.is_finite() and right.is_finite() and left>0 and left==right
 except (InvalidOperation,ValueError,TypeError):
  return False

def deal_and_protection(s,a,signal,receipt):
 """Read exact broker deal/position, preserve UNKNOWN when evidence lags."""
 if receipt["status"]!="ACK":return False
 h,risk=existing_native.native_report(s,a)
 side=Path("/var/lib/private/abutron-native-readonly-mt5-"+s)
 sh=existing_native.fresh_json(side/"worker-health.json",50)
 nonce=sh.get("nonce","")
 hist=side/"terminal/MQL5/Files"/("ABUTRON_APEX_DEAL_HISTORY_V2_"+nonce+".tsv")
 lines=fresh_file(hist,180,6000000).decode("utf-8-sig").splitlines()
 matching=[z.split("\t") for z in lines[7:] if z and z[0].isdigit() and int(z.split("\t")[0])==receipt["deal"]]
 if len(matching)!=1:return False
 row=matching[0]
 if (len(row)!=15 or row[2]!=str(receipt["order"]) or
     row[7]!="73113011" or row[1]=="0" or row[5]!="0"):
  raise Refused("BROKER_DEAL_TICKET_MAGIC_OR_ENTRY_MISMATCH")
 folder=file_from_account(s,a)
 proof=folder/"execution-audit"/(signal+".protected.txt")
 if not proof.is_file():return False
 e=fresh_file(proof,86400,5000).decode("utf-8-sig").splitlines()
 if len(e)<23 or e[:3]!=["ABUTRON_NATIVE_PROTECTED_AUDIT_V1",signal,h["nonce"]]:
  raise Refused("PROTECTED_AUDIT_ACCOUNT_BINDING_FAILED")
 if (e[7]!=str(receipt["order"]) or e[8]!=str(receipt["deal"]) or
     e[9]!=row[1] or e[-1]!="OPEN_PROTECTED"):
  return False
 # Independently check the actual broker-native SL/TP when the position remains open.
 p=existing_native.terminal_files(a)/("ABUTRON_NATIVE_ACCOUNT_V2_"+h["nonce"]+".txt")
 account=fresh_file(p,25,12000).decode("utf-8-sig").splitlines()
 open_positions=[v.split("\t") for v in account[7:] if v.split("\t")[0]==row[1]]
 if open_positions:
  if len(open_positions)!=1:return False
  current=open_positions[0]
  if len(current)!=8 or current[1]!=row[8] or not same_broker_volume(current[3],row[9]):
   return False
  if abs(float(current[5])-float(e[14]))>0.0000001 or abs(float(current[6])-float(e[15]))>0.0000001:
   return False
 return True

def reconcile_prior(s,a):
 """Never convert an uncertain send into a duplicate attempt."""
 with sqlite3.connect(CRM,timeout=8,isolation_level=None) as db:
  db.execute("PRAGMA busy_timeout=8000")
  rows=db.execute(f"SELECT signal_id,state FROM {existing_native.table(s)} WHERE state IN ('APPROVED','CLAIMED','SEND_UNKNOWN')").fetchall()
 for signal,state in rows:
  receipt=receipt_lineage(s,a,signal)
  if receipt is None:
   # A root-prepared request is never blindly requeued after restart or timeout.
   continue
  update=None
  if receipt["status"]=="BLOCKED":update="REJECTED"
  elif receipt["status"]=="ACK" and deal_and_protection(s,a,signal,receipt):
   update="BROKER_RECONCILED"
  if update:
   with sqlite3.connect(CRM,timeout=8,isolation_level=None) as db:
    db.execute("BEGIN IMMEDIATE")
    db.execute(f"UPDATE {existing_native.table(s)} SET state=?,updated_utc=? WHERE signal_id=? AND state=?",
               (update,int(time.time()),signal,state))
    db.execute("COMMIT")
   print("BROKER_RECEIPT_RECONCILED",s,signal[:12],update,receipt.get("order"),receipt.get("deal"))

def canonical_q(s,a,d,h,rev,expiration):
 order=d["order"]
 return dict(phase="CLAIM",nonce=h["nonce"],signal=d["signal_id"],
  login=a["login"],server="Deriv-Demo",symbol=d["symbol"],side=d["side"],
  lots=str(order["volume"]),sl=str(order["sl"]),tp=str(order["tp"]),
  revision=rev,expiry=expiration,lease="-")

def precheck_request(folder,a,h,d):
 """Native OrderCheck, only; no broker order request is allowed from this stage."""
 order=d["order"]
 signal=d["signal_id"]
 f=folder/"APEX11_EXACT_CHECK_ONLY.req"
 receipt=folder/"execution-audit"/("apex11-check-"+signal+".txt")
 if receipt.exists():return False
 if f.exists():return False
 expiry=min(int(time.time())+10,d["expires_utc"])
 if expiry<=int(time.time())+2:return False
 lines=["ABUTRON_APEX11_EXACT_CHECK_NO_SEND_V1",h["nonce"],a["login"],"Deriv-Demo",
        d["source_decision_id"],signal,d["symbol"],d["side"],str(order["volume"]),
        str(order["price"]),str(order["sl"]),str(order["tp"]),str(expiry),
        "CHECK_ONLY_NEVER_SEND"]
 native_atomic(folder,f,lines)
 return True

def native_atomic(folder,target,lines):
 st=folder.stat()
 if target.exists() or target.is_symlink():raise Refused("NATIVE_PENDING_REQUEST_ALREADY_EXISTS")
 tmp=folder/(".v4-account-bound-"+str(os.getpid())+"-"+str(time.time_ns()))
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  os.fchown(fd,st.st_uid,st.st_gid)
  with os.fdopen(fd,"w",encoding="utf8",newline="") as f:
   f.write("\r\n".join(lines)+"\r\n");f.flush();os.fsync(f.fileno())
  if target.exists() or target.is_symlink():raise Refused("NATIVE_REQUEST_RACE")
  os.rename(tmp,target)
  dirfd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(dirfd)
  finally:os.close(dirfd)
 finally:tmp.unlink(missing_ok=True)

def prepare_and_send(s,a,d,h,risk,owner,rev):
 signal=d["signal_id"];folder=file_from_account(s,a);now=int(time.time())
 if (d.get("connection_id")!=a["cid"] or d.get("account_suffix")!=s or
     d.get("broker")!="Deriv" or d.get("environment")!="DEMO" or
     d.get("source")!="APEX11_ACCOUNT_BOUND_NATIVE_M5_JOURNAL" or
     d.get("broker_order_ack_verified") is not False or d.get("orders_submitted")!=0 or
     d.get("original_policy_risk_ceiling_pct")!="0.10" or
     d.get("symbol") not in existing_native.SYMS or
     d.get("side") not in ("BUY","SELL") or
     not now+4 < int(d.get("expires_utc",0)) <= now+300):
  raise Refused("INVALID_ACCOUNT_BOUND_APEX_DRAFT")
 with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=4) as db:
  existing_native.journal_match(a,canonical_q(s,a,d,h,rev,now+10),owner,d["source_decision_id"])
 q=canonical_q(s,a,d,h,rev,now+10)
 # Check the immutable exact broker OrderCheck from the current signal.
 audit=folder/"execution-audit"/("apex11-check-"+signal+".txt")
 if not audit.is_file():
  if precheck_request(folder,a,h,d):return "NATIVE_EXACT_ORDERCHECK_REQUESTED"
  return "BROKER_ORDERCHECK_PENDING"
 digest,source_decision=existing_native.native_check(a,h,q,risk)
 if source_decision!=d["source_decision_id"]:raise Refused("ORDER_CHECK_SOURCE_DECISION_DIFFERENT")
 existing_native.capability(a,h,rev)
 if (folder/"ABUTRON_APEX_V4.req").exists() or (folder/"APEX_NATIVE_ORDER_V1.req").exists():
  raise Refused("BROKER_WRITER_REQUEST_ALREADY_PENDING")
 with sqlite3.connect(CRM,timeout=8,isolation_level=None) as db:
  db.execute("BEGIN IMMEDIATE")
  try:
   owner2,rev2=existing_native.crm_row(db,s,a)
   if owner2!=owner or rev2!=rev:raise Refused("CRM_SWITCH_CHANGED_DURING_PREPARE")
   if db.execute(f"SELECT 1 FROM {existing_native.table(s)} WHERE signal_id=?",(signal,)).fetchone():
    raise Refused("DUPLICATE_SIGNAL_ATTEMPT")
   if db.execute(f"SELECT 1 FROM {existing_native.table(s)} WHERE state IN ('APPROVED','CLAIMED','SEND_UNKNOWN') LIMIT 1").fetchone():
    raise Refused("PREVIOUS_BROKER_ATTEMPT_NOT_RECONCILED")
   fields=[q[x] for x in ("nonce","signal","login","server","symbol","side","lots","sl","tp")]
   reqdig=hashlib.sha256("\n".join(map(str,fields+[str(rev),str(q["expiry"])])).encode("ascii")).hexdigest()
   db.execute(f"INSERT INTO {existing_native.table(s)} VALUES(?,?,?,?,?,?,?,?,?,?,?)",
     (signal,d["source_decision_id"],h["nonce"],reqdig,digest,rev,q["expiry"],
      "APPROVED",None,now,now))
   db.execute("COMMIT")
  except BaseException:
   db.execute("ROLLBACK");raise
 try:
  lines=["APEX_NATIVE_ACCOUNT_BOUND_ORDER_V4",h["nonce"],signal,a["login"],
         "Deriv-Demo",d["symbol"],d["side"],q["lots"],q["sl"],q["tp"],
         str(rev),str(q["expiry"]),"SEND_DEMO_ONLY"]
  native_atomic(folder,folder/"ABUTRON_APEX_V4.req",lines)
 except BaseException:
  with sqlite3.connect(CRM,timeout=6) as db:
   db.execute(f"UPDATE {existing_native.table(s)} SET state='REJECTED',updated_utc=? WHERE signal_id=? AND state='APPROVED'",(int(time.time()),signal))
  raise
 return "V4_NATIVE_BROKER_ORDER_REQUEST_QUEUED_ONCE"

def run(s):
 if os.geteuid()!=0:raise Refused("ROOT_REQUIRED")
 a=ACCOUNTS[s];root=root_dir(s)
 fd=os.open(root/"single-account-native-writer.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  reconcile_prior(s,a)
  h,risk,owner,rev=native_session(s,a)
  r=json.loads(fresh_file(draft_path(s),42,100000))
  if (r.get("state")!="DRAFT_ONLY_NO_BROKER_ORDER_CHECK_OR_EXECUTION_AUTHORITY"
      or r.get("orders_submitted")!=0 or
      len(r.get("drafts",[]))>5):
   raise Refused("INVALID_APEX_NATIVE_PRECOMMIT_REPORT")
  # APEX determines BUY/SELL. Do not introduce an additional ranking strategy.
  choices=[d for d in r["drafts"] if d.get("expires_utc",0)>time.time()+12]
  if not choices:return log_result(s,"NO_DUE_FRESH_ACCOUNT_BOUND_APEX_SIGNAL")
  for d in choices:
   try:
    result=prepare_and_send(s,a,d,h,risk,owner,rev)
    return log_result(s,result,signal=d["signal_id"][:14],symbol=d["symbol"])
   except (Refused,existing_native.Denied,OSError,sqlite3.Error,ValueError,TypeError,KeyError) as e:
    print("V4_CANDIDATE_NOT_SUBMITTED",s,d.get("symbol"),type(e).__name__,str(e)[:120])
  return log_result(s,"ALL_CURRENT_APEX_CANDIDATES_NOT_SUBMITTED")
 finally:
  os.close(fd)

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--account",required=True,choices=sorted(ACCOUNTS))
 args=p.parse_args()
 try:run(args.account)
 except (Refused,existing_native.Denied,OSError,sqlite3.Error,ValueError,TypeError,KeyError) as e:
  log_result(args.account,"NATIVE_ORDER_TRANSPORT_NOT_READY",reason=type(e).__name__+":"+str(e)[:130])
