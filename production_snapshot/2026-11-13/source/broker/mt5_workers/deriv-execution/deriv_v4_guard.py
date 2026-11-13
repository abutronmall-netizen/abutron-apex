#!/usr/bin/python3
"""Deriv 7593/9244 DEMO V4 native authorization. Denies unless exact root-approved
APEX intent, fresh independent broker exposure, authentic native OrderCheck,
CRM ON/license and one-shot two-phase lease all match. Never submits orders.
"""
from __future__ import annotations
import argparse, datetime, hashlib, hmac, json, math, os, re, secrets, sqlite3, stat, time
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ACCOUNTS = {
 "7593":dict(cid="9568525eee306da891258ad98c654919",login="6357593",port=19745,
             sha="ba95b6153cce90833d424cc94c3a776e0788af0bd794816ab20a5443deefa644"),
 "9244":dict(cid="1ead1f08b44dc5ae284eadc9554b1381",login="202699244",port=19744,
             sha="f33a0822d114a1594a41aa7c458a7c6221415e7b4b6bc5e3c75882951e9da30c")
}
CRM=Path("/var/lib/apex-signup/accounts.sqlite3")
RECON=Path("/var/lib/abutron-deriv-multi-native-reconciliation/latest.json")
FP1636=Path("/var/lib/abutron-fp-execution/1636/reconciliation/latest.json")
SYMS={"Volatility "+str(i)+" Index.0" for i in (10,25,50,75,100)}
H32=re.compile(r"[0-9a-f]{32}\Z")
H64=re.compile(r"[0-9a-f]{64}\Z")
NAT=re.compile(r"[1-9][0-9]{0,17}\Z")
PRICE=re.compile(r"[0-9]{1,9}(\.[0-9]{1,9})?\Z")
class Denied(Exception): pass

def trusted_bytes(path,age,maximum=5000000):
 p=Path(path)
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  st=os.fstat(fd)
  if (not stat.S_ISREG(st.st_mode) or st.st_mode&0o022 or
      st.st_size<5 or st.st_size>maximum or not -2<=time.time()-st.st_mtime<=age):
   raise Denied("UNSAFE_STALE_OR_ABSENT_EVIDENCE")
  b=os.read(fd,maximum+1)
  if len(b)!=st.st_size:raise Denied("EVIDENCE_READ_RACE")
  return b
 finally: os.close(fd)

def fresh_json(path,age=35):return json.loads(trusted_bytes(path,age))
def cfg(suffix):return ACCOUNTS[suffix]
def terminal_files(a):
 return Path("/var/lib/private/abutron-client-mt5-"+a["cid"]+"/terminal/MQL5/Files")
def source_worker(a):
 return Path("/var/lib/private/abutron-client-mt5-"+a["cid"]+"/worker-health.json")
def native_report(suffix,a):
 h=fresh_json(source_worker(a),25)
 if (h.get("id")!=a["cid"] or h.get("broker")!="Deriv" or
     h.get("server")!="Deriv-Demo" or h.get("mode")!="DEMO" or
     h.get("status")!="CONNECTED" or h.get("heartbeat_fresh") is not True or
     not H32.fullmatch(str(h.get("nonce","")))):
  raise Denied("WORKER_IDENTITY_NOT_FRESH_DEMO")
 r=fresh_json(RECON,45)
 if r.get("all_verified") is not True:raise Denied("THREE_ACCOUNT_NATIVE_RECON_NOT_COMPLETE")
 rows=[x for x in r.get("accounts",[]) if x.get("account_suffix")==suffix]
 if len(rows)!=1:raise Denied("NATIVE_RECON_ACCOUNT_AMBIGUOUS")
 z=rows[0]
 if (z.get("state")!="VERIFIED_READONLY" or
     z.get("all_current_positions_sl_tp_usd_risk_verified") is not True or
     z.get("pending_orders")!=0 or type(z.get("equity_usd")) not in (float,int) or
     z["equity_usd"]<=0):raise Denied("NATIVE_RECON_RISK_INVALID")
 # Existing positions are allowed only when independent native reconcilers
 # prove every position's protective stops and conservative USD stop-risk.
 # This replaces the obsolete flat-only bootstrap, not broker lifecycle proof.
 positions=z.get("positions")
 open_risk=z.get("open_position_usd_stop_risk")
 if (type(positions) is not int or positions<0 or
     type(open_risk) not in (float,int) or not math.isfinite(open_risk) or
     open_risk<0 or
     (positions==0 and (open_risk!=0 or z.get("current_exposure")!="ZERO_DUAL_NATIVE_PROOF")) or
     (positions>0 and (open_risk<=0 or z.get("current_exposure")!="PROTECTED_NATIVE_POSITIONS_DUAL_PROOF"))):
  raise Denied("NATIVE_OPEN_POSITIONS_OR_STOP_RISK_NOT_VERIFIED")
 if suffix=="9244":
  fp=fresh_json(FP1636,50)
  if (fp.get("broker")!="FP Markets" or
      fp.get("portfolio_risk_for_new_entries_verified") is not True or
      fp.get("broker_history_verified") is not True or
      fp.get("broker_pending_orders")!=0):
   raise Denied("SHARED_FP_OWNER_NATIVE_EXPOSURE_NOT_PROVEN")
  fp_eq=float(fp["broker_equity_usd"])
  fp_risk=float(fp["verified_open_gross_stop_risk_usd"])
  combined=fp_eq+float(z["equity_usd"])
  if not (math.isfinite(fp_eq) and math.isfinite(fp_risk) and
          fp_eq>0 and fp_risk>=0 and
          fp_risk+open_risk+float(z["equity_usd"])*.001<=combined*.20):
   raise Denied("SHARED_OWNER_PORTFOLIO_RISK_EXCEEDS_20PCT")
 else:
  if open_risk+float(z["equity_usd"])*.001>float(z["equity_usd"])*.20:
   raise Denied("OWNER_PORTFOLIO_RISK_EXCEEDS_20PCT")
 return h,z

def crm_row(db,suffix,a):
 rows=db.execute("""SELECT x.account_id,x.account_reference,x.broker_server,x.broker,
  x.environment,x.status,a.status,t.desired_enabled,t.effective_enabled,t.updated_at,
  l.plan,l.status,l.seats,l.expires_on
  FROM apex_mt5_connections x
  JOIN accounts a ON a.id=x.account_id
  JOIN apex_trade_controls t ON t.connection_id=x.id
  JOIN apex_crm_licenses l ON l.account_id=x.account_id
  WHERE x.id=?""",(a["cid"],)).fetchall()
 if len(rows)!=1:raise Denied("CRM_ACCOUNT_NOT_UNIQUE")
 r=rows[0]
 if (str(r[1])!=a["login"] or r[2:7]!=("Deriv-Demo","Deriv","DEMO","CONNECTED","approved")
     or r[7:9]!=(1,1) or r[10:13]!=("Enterprise","active",3)):
  raise Denied("CRM_OWNER_LICENSE_OR_ON_INVALID")
 if r[13] and r[13]<datetime.datetime.now(datetime.timezone.utc).date().isoformat():
  raise Denied("LICENSE_EXPIRED")
 rev=r[9]
 if type(rev) is not int or rev<1:raise Denied("INVALID_CRM_SWITCH_REVISION")
 return r[0],rev

def deployed_v4(a):
 p=Path("/var/lib/private/abutron-client-mt5-"+a["cid"]+
        "/terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_"+a["login"][-4:]+".ex5")
 if hashlib.sha256(trusted_bytes(p,86400*30,200000)).hexdigest()!=a["sha"]:
  raise Denied("PRODUCTION_V4_EA_SHA_MISMATCH")
 return True

def capability(a,h,rev):
 nonce=h["nonce"]
 p=terminal_files(a)/("ABUTRON_APEX_NATIVE_V4_CAPABILITY_"+nonce+".txt")
 ls=trusted_bytes(p,20,1024).decode("utf-8-sig").splitlines()
 if (len(ls)!=10 or ls[:5]!=["APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4",nonce,a["login"],
    "Deriv-Demo","DEMO"] or ls[5]!=str(rev) or not NAT.fullmatch(ls[6]) or
    abs(int(ls[6])-int(time.time()))>20 or
    ls[7:]!=["0.10","OFF_REVISION_CHECK_AT_CONSUME","LIVE_FORBIDDEN"]):
  raise Denied("ACCOUNT_BOUND_V4_NATIVE_CAPABILITY_MISSING")
 return True

def decode(raw,suffix,a):
 if not isinstance(raw,bytes) or not 10<len(raw)<=1024 or b"\x00" in raw:
  raise Denied("INVALID_REQUEST_BYTES")
 try:ls=raw.decode("ascii").splitlines()
 except UnicodeError:raise Denied("NON_ASCII_REQUEST")
 if len(ls)!=14 or ls[0]!="ABUTRON_V4_LOCAL_GUARD_V1":
  raise Denied("WRONG_PROTOCOL")
 _,phase,nonce,signal,login,server,symbol,side,lots,sl,tp,rev,expiry,lease=ls
 if (phase not in ("CLAIM","SEND") or not H32.fullmatch(nonce) or
     not H64.fullmatch(signal) or login!=a["login"] or server!="Deriv-Demo" or
     symbol not in SYMS or side not in ("BUY","SELL") or
     not NAT.fullmatch(rev) or not NAT.fullmatch(expiry) or
     int(expiry)<int(time.time()) or int(expiry)>int(time.time())+12 or
     (lease!="-" if phase=="CLAIM" else not H64.fullmatch(lease))):
  raise Denied("ACCOUNT_REVISION_OR_LEASE_FORMAT")
 if not all(PRICE.fullmatch(v) for v in (lots,sl,tp)):
  raise Denied("NATIVE_PRICE_FORMAT")
 try:
  v,s,t=Decimal(lots),Decimal(sl),Decimal(tp)
  if not (Decimal(".01")<=v<=Decimal("100") and s>0 and t>0 and
          ((side=="BUY" and s<t) or (side=="SELL" and t<s))):
   raise Denied("STOP_TARGET_OR_LOT_INVALID")
 except InvalidOperation:raise Denied("INVALID_DECIMAL")
 dig=hashlib.sha256("\n".join(ls[2:13]).encode("ascii")).hexdigest()
 return dict(phase=phase,nonce=nonce,signal=signal,login=login,server=server,
             symbol=symbol,side=side,lots=lots,sl=sl,tp=tp,revision=int(rev),
             expiry=int(expiry),lease=lease,digest=dig)

def native_check(a,h,q,risk):
 p=terminal_files(a)/"ABUTRON"/"execution-audit"/("apex11-check-"+q["signal"]+".txt")
 z=trusted_bytes(p,20,3000).decode("utf-8-sig").splitlines()
 if (len(z)!=24 or z[0]!="ABUTRON_APEX11_EXACT_CHECK_NATIVE_NO_SEND_V1" or
     z[1:4]!=[q["nonce"],a["login"],"Deriv-Demo"] or
     not H64.fullmatch(z[4]) or z[5:9]!=[q["signal"],q["symbol"],q["side"],q["lots"]] or
     z[10:12]!=[q["sl"],q["tp"]] or
     z[13:16]!=["CHECK_PASS_NO_SEND","BROKER_NATIVE_EXACT_CHECK_ONLY","ORDER_CHECK_CALLED"] or
     z[16] not in ("0","10009") or not NAT.fullmatch(z[12]) or
     abs(int(z[12])-int(time.time()))>15 or z[23]!="NO_ORDER_SEND;NO_CRM_CHANGE;NO_BROKER_ACK"):
  raise Denied("EXACT_BROKER_ORDERCHECK_UNVERIFIED")
 stop=float(z[18]);take=float(z[19]);margin=float(z[20])
 if (not (-stop>0 and take>0 and margin>=0 and
          -stop<=float(risk["equity_usd"])*.001*.85 and take/-stop>=1.5)):
  raise Denied("BROKER_USD_RISK_GT_010_OR_REWARD_BELOW_15")
 return hashlib.sha256("\n".join(z).encode()).hexdigest(),z[4]

def journal_match(a,q,owner,decision_id):
 # Independent authenticated account-bound strategy source, not caller input.
 p=Path("/var/lib/abutron-apex11-"+a["login"][-4:]+"/account-bound-m5-journal.sqlite3")
 with sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True,timeout=3) as db:
  db.execute("PRAGMA query_only=ON")
  row=db.execute("SELECT payload,closed_ts FROM decisions WHERE account_id=? AND symbol=? ORDER BY closed_ts DESC LIMIT 1",
                 (a["cid"],q["symbol"])).fetchone()
 if not row:raise Denied("NO_MATCHED_APEX_JOURNAL_DECISION")
 d=json.loads(row[0]);bar=row[1];n=int(time.time())
 canonical=hashlib.sha256(f'{owner}|{a["cid"]}|{q["symbol"]}|M5|{bar-300}|{q["side"]}'.encode()).hexdigest()
 if (d.get("publication_schema")!="abutron.apex11.account.shadow.v1" or
     d.get("engine")!="APEX_1_1_0" or d.get("connection_id")!=a["cid"] or
     d.get("customer_id")!=owner or d.get("decision_id")!=decision_id or
     d.get("status")!=q["side"] or d.get("symbol")!=q["symbol"] or
     d.get("timeframe")!="M5" or d.get("orders_submitted")!=0 or
     canonical!=q["signal"] or not 0<=n-int(bar)<300 or
     q["expiry"]>int(bar)+300):
  raise Denied("APEX_NATIVE_SIGNAL_MISMATCH_STALE_OR_REPLAY")
 return True

def table(suffix):
 return "abutron_v4_"+suffix+"_exact_intent"
def ddl(suffix):
 return (f"CREATE TABLE IF NOT EXISTS {table(suffix)} ("
  "signal_id TEXT PRIMARY KEY, source_decision_id TEXT NOT NULL,"
  "nonce TEXT NOT NULL, request_digest TEXT NOT NULL, native_check_digest TEXT NOT NULL,"
  "revision INTEGER NOT NULL, expires_utc INTEGER NOT NULL,"
  "state TEXT NOT NULL CHECK(state IN ('APPROVED','CLAIMED','SEND_UNKNOWN','BROKER_RECONCILED','REJECTED')),"
  "lease TEXT, created_utc INTEGER NOT NULL, updated_utc INTEGER NOT NULL)")

def transact(suffix,raw):
 a=cfg(suffix);q=decode(raw,suffix,a)
 deployed_v4(a)
 h,risk=native_report(suffix,a)
 if q["nonce"]!=h["nonce"]:raise Denied("WORKER_NONCE_CHANGED")
 dig,source_decision=native_check(a,h,q,risk)
 db=sqlite3.connect(CRM,timeout=5,isolation_level=None)
 try:
  db.execute("BEGIN IMMEDIATE")
  owner,revision=crm_row(db,suffix,a)
  if q["revision"]!=revision:raise Denied("CRM_REVISION_STALE_OR_OFF")
  capability(a,h,revision)
  journal_match(a,q,owner,source_decision)
  row=db.execute(f"SELECT source_decision_id,nonce,request_digest,native_check_digest,revision,expires_utc,state,lease,created_utc FROM {table(suffix)} WHERE signal_id=?",
                 (q["signal"],)).fetchone()
  n=int(time.time())
  if (not row or row[0]!=source_decision or
      row[1:6]!=(q["nonce"],q["digest"],dig,revision,q["expiry"]) or
      not 0<=n-row[8]<=20):
   raise Denied("NO_MATCHING_ROOT_APPROVED_EXACT_ORDER_INTENT")
  if q["phase"]=="CLAIM":
   if row[6]!="APPROVED":raise Denied("CLAIM_REPLAY_OR_UNCERTAIN")
   if db.execute(f"SELECT 1 FROM {table(suffix)} WHERE state='SEND_UNKNOWN' OR (state='CLAIMED' AND expires_utc>=?) LIMIT 1",(n,)).fetchone():
    raise Denied("EXCLUSIVE_WRITER_OR_UNKNOWN_ORDER")
   lease=secrets.token_hex(32)
   db.execute(f"UPDATE {table(suffix)} SET state='CLAIMED',lease=?,updated_utc=? WHERE signal_id=? AND state='APPROVED'",
              (lease,n,q["signal"]))
  else:
   if row[6]!="CLAIMED" or row[7]!=q["lease"]:
    raise Denied("SEND_REPLAY_OR_LEASE_MISMATCH")
   lease=q["lease"]
   if db.execute(f"UPDATE {table(suffix)} SET state='SEND_UNKNOWN',updated_utc=? WHERE signal_id=? AND state='CLAIMED'",(n,q["signal"])).rowcount!=1:
    raise Denied("UNKNOWN_SEND_RACE")
  db.execute("COMMIT")
  return ("ALLOW|"+lease+"\n").encode()
 except BaseException:
  db.execute("ROLLBACK")
  raise
 finally:db.close()

def revision_status(suffix):
 # GET only provides current account identity and switch revision to MT5;
 # it is not approval to send an order. Independent risk/ACK is POST-only.
 a=cfg(suffix)
 deployed_v4(a)
 h=fresh_json(source_worker(a),25)
 if (h.get("id")!=a["cid"] or h.get("mode")!="DEMO" or
     h.get("broker")!="Deriv" or h.get("server")!="Deriv-Demo" or
     h.get("status")!="CONNECTED" or h.get("heartbeat_fresh") is not True or
     not H32.fullmatch(str(h.get("nonce","")))):
  raise Denied("BROKER_SESSION_NOT_AUTHENTICATED")
 with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=3) as db:
  rows=db.execute("""SELECT x.account_reference,x.broker,x.environment,x.broker_server,
                  x.status,t.desired_enabled,t.updated_at
                  FROM apex_mt5_connections x JOIN apex_trade_controls t
                  ON x.id=t.connection_id WHERE x.id=?""",(a["cid"],)).fetchall()
 if (len(rows)!=1 or rows[0][:6] != (a["login"],"Deriv","DEMO","Deriv-Demo","CONNECTED",1)
     or type(rows[0][6]) is not int or rows[0][6]<1):
  raise Denied("CUSTOMER_REQUESTED_OFF_OR_ACCOUNT_DISCONNECTED")
 return rows[0][6]


def effective_order_revision(suffix):
 # Preserve the existing customer's ON/OFF at order consumption, not an
 # additional supervisor or approval workflow.
 rev=revision_status(suffix)
 a=cfg(suffix)
 with sqlite3.connect("file:"+str(CRM)+"?mode=ro",uri=True,timeout=3) as db:
  row=db.execute("SELECT desired_enabled,effective_enabled,updated_at FROM apex_trade_controls WHERE connection_id=?",(a['cid'],)).fetchone()
 if row!=(1,1,rev):raise Denied("CURRENT_CLIENT_EXECUTION_SWITCH_NOT_ON")
 return rev

def handler_for(suffix):
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*_):pass
  def answer(self,status,body):
   self.send_response(status);self.send_header("Content-Type","text/plain")
   self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)))
   self.end_headers();self.wfile.write(body)
  def do_GET(self):
   if self.path not in ("/v4/direct/status","/v4/direct/order-status"):
    return self.answer(404,b"NOT_FOUND\n")
   try:
    rev=(effective_order_revision(suffix) if self.path=="/v4/direct/order-status"
         else revision_status(suffix))
   except Exception as e:
    print(suffix,"GET_DENIED",type(e).__name__,str(e)[:100],flush=True)
    return self.answer(503,b"DENY\n")
   if self.path=="/v4/direct/order-status":
    print(suffix,"ORDER_STATUS_VERIFIED",flush=True)
   return self.answer(200,("STATUS|"+str(rev)+"\n").encode())
  def do_POST(self):
   # The existing EA requires CLAIM then SEND on this loopback-only endpoint.
   # transact() enforces DEMO account/nonce, CRM effective ON, native stop-risk,
   # current exact OrderCheck, immutable approval, one-use lease and no replay.
   if self.path!="/v4/direct/authorize":
    return self.answer(404,b"NOT_FOUND\n")
   length=self.headers.get("Content-Length","")
   if not length.isascii() or not length.isdigit() or not 10<=int(length)<=1024:
    return self.answer(400,b"INVALID_LENGTH\n")
   try:
    raw=self.rfile.read(int(length))
    if len(raw)!=int(length):raise Denied("REQUEST_TRUNCATED")
    approval=transact(suffix,raw)
    # Nonsecret audit: no nonce, ticket, signal, token or lease is logged.
    phase=raw.splitlines()[1].decode('ascii') if len(raw.splitlines())>1 else 'UNKNOWN'
    print(suffix,"POST_ALLOW",phase if phase in ("CLAIM","SEND") else "INVALID",flush=True)
    return self.answer(200,approval)
   except (Denied,ValueError,TypeError,sqlite3.Error,OSError) as e:
    print(suffix,"POST_DENIED",type(e).__name__,str(e)[:90],flush=True)
    return self.answer(503,b"DENY\n")
 return Handler

def main():
 p=argparse.ArgumentParser();p.add_argument("--account",choices=ACCOUNTS,required=True)
 p.add_argument("--self-test",action="store_true");args=p.parse_args()
 a=cfg(args.account)
 if args.self_test:
  print(json.dumps(dict(account=args.account,port=a["port"],safe_server_bind="127.0.0.1",
    compiled_release_sha_matches=deployed_v4(a),status_revision=revision_status(args.account))))
  return
 with sqlite3.connect(CRM,timeout=8) as db:db.execute(ddl(args.account))
 host=ThreadingHTTPServer(("127.0.0.1",a["port"]),handler_for(args.account))
 print("ACCOUNT_SCOPED_DERIV_DEMO_V4_GUARD_READY",args.account,a["port"],flush=True)
 host.serve_forever(poll_interval=.2)

if __name__=="__main__":main()
