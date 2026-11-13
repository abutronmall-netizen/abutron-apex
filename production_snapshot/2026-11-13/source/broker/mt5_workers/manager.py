#!/usr/bin/env python3
"""ABUTRONFX client MT5 manager: local-only socket, one dynamic OS identity per client.
No order submission, no signal delivery, no trading privileges. Secrets enter via
systemd LoadCredential on /run tmpfs; no broker passwords in DB, argv, or logs.
"""
import os,json,socket,struct,sqlite3,pwd,grp,re,threading,time,subprocess,secrets,stat
from pathlib import Path
ROOT=Path("/run/abutron-client-mt5-manager")
SOCK=ROOT/"manager.sock"
SECRETS=ROOT/"secrets"
SEALED=Path("/var/lib/abutron-client-mt5-manager/credentials")
RECOVERY_LAST_ATTEMPT={}
DB="/var/lib/apex-signup/accounts.sqlite3"
WORKER="/opt/apex-client-mt5/worker_feed_v4.py"
FP_WORKER="/opt/apex-client-mt5/worker_feed_v8_fp_handoff.py"
DERIV_50_100_WORKER="/opt/apex-client-mt5/worker_feed_v4_usd50_canary.py"
DERIV_LIVE_READONLY_WORKER="/opt/apex-client-mt5/worker_feed_v4_deriv_live_readonly.py"
TEMPLATE=Path("/opt/abutron/client-mt5-template-v3")
FP_MODES={"FPMarketsSC-Demo":"DEMO","FPMarketsSC-Demo Server":"DEMO",
 "FPMarketsLtd-Demo2":"DEMO","FPMarketsSC-Live":"LIVE","FPMarketsLtd-Live2":"LIVE"}
DERIV_LIVE_MODES={"DerivBVI-Server-02":"LIVE","DerivSVG-Server":"LIVE"}
ALLOWED={("Deriv","Deriv-Demo"),("IC Markets","ICMarketsSC-Demo")} | {("FP Markets",s) for s in FP_MODES} | {("Deriv",s) for s in DERIV_LIVE_MODES}
def expected_mode(broker,server):
 return (FP_MODES.get(server) if broker=="FP Markets" else
         DERIV_LIVE_MODES.get(server) if broker=="Deriv" and server in DERIV_LIVE_MODES else
         "DEMO" if (broker,server) in ALLOWED else None)
CID=re.compile(r"^[a-f0-9]{32}$")
LOGIN=re.compile(r"^[0-9]{4,20}$")
g_lock=threading.RLock()
active=set()
def db():
 c=sqlite3.connect(DB,isolation_level=None,timeout=8)
 c.execute("PRAGMA foreign_keys=ON")
 c.execute("PRAGMA busy_timeout=8000")
 return c
def unit(cid):return "abutron-client-mt5-"+cid
def state(cid):return Path("/var/lib/private")/unit(cid)
def service_active(cid):
 p=subprocess.run(["systemctl","is-active",unit(cid)+".service"],
  stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5)
 return p.returncode==0 and p.stdout.strip()==b"active"
def sealed_path(cid):
 if not CID.fullmatch(cid):raise ValueError("Invalid connection id")
 return SEALED/(cid+".cred")
def ensure_sealed_store():
 SEALED.mkdir(mode=0o700,parents=True,exist_ok=True)
 for directory in (SEALED.parent,SEALED):
  st=directory.lstat()
  if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o077:
   raise ValueError("Broker credential store ownership or permissions invalid")
 SEALED.chmod(0o700)
def sealed_available(cid):
 try:
  p=sealed_path(cid);st=p.lstat()
  return stat.S_ISREG(st.st_mode) and st.st_uid==0 and not st.st_mode&0o077 and 80<=st.st_size<=16000
 except (OSError,ValueError):return False
def seal_credential(cid,plaintext):
 ensure_sealed_store()
 destination=sealed_path(cid)
 temporary=SEALED/("."+cid+"."+secrets.token_hex(8)+".cred")
 try:
  subprocess.run(["/usr/bin/systemd-creds","--with-key=host","--name=mt5",
                  "encrypt",str(plaintext),str(temporary)],check=True,timeout=15,
                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  st=temporary.lstat()
  if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or not 80<=st.st_size<=16000:
   raise ValueError("Encrypted credential verification failed")
  temporary.chmod(0o600)
  os.replace(temporary,destination)
  if not sealed_available(cid):raise ValueError("Encrypted credential not durable")
  return destination
 finally:
  temporary.unlink(missing_ok=True)
def launch_worker(cid,broker,mode,encrypted):
 if (broker not in ("Deriv","FP Markets","IC Markets")
     or mode not in ("DEMO","LIVE")
     or (mode=="LIVE" and broker not in ("FP Markets","Deriv"))
     or not sealed_available(cid) or encrypted!=sealed_path(cid)):
  raise ValueError("Unverified approved broker encrypted credential")
 chosen=(FP_WORKER if broker=="FP Markets" else
         DERIV_LIVE_READONLY_WORKER if broker=="Deriv" and mode=="LIVE" else
         DERIV_50_100_WORKER if broker=="Deriv" else WORKER)
 # A previous transient failed unit is not reused, and new unit metadata is
 # retained rather than automatically garbage-collected.
 subprocess.run(["systemctl","reset-failed",unit(cid)+".service"],timeout=6,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run(["systemd-run","--collect","--unit="+unit(cid),
     "--property=Type=exec","--property=DynamicUser=yes",
     "--property=StateDirectory="+unit(cid),
     "--property=RuntimeDirectory="+unit(cid),
     "--property=LoadCredentialEncrypted=mt5:"+str(encrypted),
     "--property=ProtectSystem=strict","--property=ProtectHome=yes",
     "--property=PrivateTmp=yes","--property=PrivateDevices=yes",
     "--property=NoNewPrivileges=yes",
     "--property=MemoryMax=1800M","--property=TasksMax=170",
     "--property=UMask=0077",
     *(["--property=SupplementaryGroups=abutron-fp-boot-assets"]
       if (broker,mode)==("FP Markets","DEMO") else []),
     "/usr/bin/python3","-B",chosen],check=True,timeout=20,
     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def maintenance_reexec_seen():
 # A user-initiated STOP must remain stopped. Recover only when a recent
 # unattended OS maintenance event caused systemd to reexec its manager.
 try:
  eventlog=subprocess.run(["/usr/bin/journalctl","_PID=1","--since=30 minutes ago",
        "--grep=Reexecuting requested from client PID","--no-pager","--output=cat"],
        timeout=6,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  return eventlog.returncode==0 and b"apt-daily-upgrade.service" in eventlog.stdout[-12000:]
 except (OSError,subprocess.SubprocessError):return False
def recover_offline_demo(cid,owner,broker,server):
 # Only user-authorized DEMO accounts with an existing host-encrypted
 # credential and a confirmed worker-loss error may reconnect. Never restore
 # automatic order permissions or recreate a LIVE trading account.
 if expected_mode(broker,server)!="DEMO" or not sealed_available(cid):return
 if service_active(cid):return
 now=time.time()
 if now-RECOVERY_LAST_ATTEMPT.get(cid,0)<300:return
 if not maintenance_reexec_seen():
  RECOVERY_LAST_ATTEMPT[cid]=now
  return
 with g_lock:
  if cid in active or service_active(cid):return
  with db() as c:
   r=c.execute("""SELECT a.status,a.worker_binding,t.effective_enabled,t.last_error
     FROM apex_mt5_connections a JOIN apex_trade_controls t ON a.id=t.connection_id
     WHERE a.id=? AND a.account_id=? AND a.broker=? AND a.broker_server=?""",
     (cid,owner,broker,server)).fetchone()
  if not r or r[0]!="ERROR" or r[2]!=0 or r[3]!="MT5_WORKER_NOT_RUNNING":
   return
  RECOVERY_LAST_ATTEMPT[cid]=now
  active.add(cid)
  try:
   launch_worker(cid,broker,"DEMO",sealed_path(cid))
   with db() as c:
    c.execute("BEGIN IMMEDIATE")
    status=c.execute("SELECT status FROM apex_mt5_connections WHERE id=? AND account_id=?",
                     (cid,owner)).fetchone()
    if not status or status[0]!="ERROR":
     c.execute("ROLLBACK")
     subprocess.run(["systemctl","stop",unit(cid)+".service"],timeout=9,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     return
    stamp=int(time.time())
    c.execute("""UPDATE apex_mt5_connections SET status='CONNECTING',worker_binding=?,
      broker_verified_at=NULL,updated_at=? WHERE id=? AND account_id=?""",
      (unit(cid),stamp,cid,owner))
    c.execute("""UPDATE apex_trade_controls SET effective_enabled=0,
      last_error='RECOVERY_BROKER_HEARTBEAT_PENDING',updated_at=?
      WHERE connection_id=?""",(stamp,cid))
    event(c,cid,owner,"ENCRYPTED_DEMO_SESSION_RESTARTED",
          "fresh_broker_proof_required_trading_disabled")
    c.execute("COMMIT")
  except (OSError,ValueError,subprocess.SubprocessError,sqlite3.Error):
   pass
  finally:active.discard(cid)
def out(status,msg,**kw):return {"status":status,"ok":status<300,"message":msg,**kw}
def event(c,cid,owner,kind,detail):
 c.execute("""INSERT INTO apex_mt5_connection_events
 (connection_id,account_id,event,occurred_at,detail) VALUES(?,?,?,?,?)""",
 (cid,owner,kind,int(time.time()),detail))
def revoke(cid,owner,kind,detail):
 with db() as c:
  c.execute("BEGIN IMMEDIATE")
  row=c.execute("SELECT status FROM apex_mt5_connections WHERE id=? AND account_id=?",(cid,owner)).fetchone()
  if not row or row[0]=="DISCONNECTED":c.execute("ROLLBACK");return
  now=int(time.time())
  c.execute("""UPDATE apex_mt5_connections SET status='ERROR',
   worker_binding=NULL,broker_verified_at=NULL,updated_at=? WHERE id=? AND account_id=?""",
   (now,cid,owner))
  c.execute("""UPDATE apex_trade_controls SET desired_enabled=0,effective_enabled=0,
    last_error=?,updated_at=? WHERE connection_id=?""",(detail,now,cid))
  event(c,cid,owner,kind,detail)
  c.execute("COMMIT")
def attest(cid,broker,server):
 p=state(cid);health=p/"worker-health.json"
 if not service_active(cid) or not health.is_file():return False
 try:
  h=json.loads(health.read_text())
  if (h.get("status")!="CONNECTED" or h.get("id")!=cid or
      h.get("broker")!=broker or h.get("server")!=server or
      h.get("mode")!=expected_mode(broker,server) or h.get("heartbeat_fresh") is not True or
      not isinstance(h.get("verified_at"),int) or
      time.time()-h["verified_at"]>17):return False
  nonce=h.get("nonce");proof_owner=h.get("proof_owner")
  if not isinstance(nonce,str) or not re.fullmatch("[a-f0-9]{32}",nonce):return False
  if not isinstance(proof_owner,str) or len(proof_owner)!=36:return False
  path=p/"terminal"/"MQL5"/"Files"/("ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt")
  if not path.is_file() or time.time()-path.stat().st_mtime>17:return False
  b=("DERIV_SVG" if broker=="Deriv" and server=="DerivSVG-Server" else
     {"Deriv":"DERIV_BVI","IC Markets":"IC_MARKETS","FP Markets":"FP_MARKETS"}[broker])
  expected=["ABUTRON_MT5_NATIVE_HEARTBEAT_V1",nonce,proof_owner,b,server,expected_mode(broker,server),
            "CONNECTED","NO_ORDER_FUNCTIONS"]
  return path.read_text(encoding="utf-8-sig").splitlines()==expected
 except (OSError,ValueError,TypeError,KeyError):return False
def update_state(cid,owner,broker,server):
 # A missed native heartbeat must fail closed, but must NEVER orphan a live
 # authenticated terminal by deleting its binding. Recover only with fresh proof.
 healthy=attest(cid,broker,server)
 running=service_active(cid)
 with db() as c:
  c.execute("BEGIN IMMEDIATE")
  row=c.execute("""SELECT status,worker_binding,updated_at FROM apex_mt5_connections
    WHERE id=? AND account_id=?""",(cid,owner)).fetchone()
  if not row or row[0]=="DISCONNECTED" or row[1]!=unit(cid):
   c.execute("ROLLBACK");return
  old,binding,updated=row
  now=int(time.time())
  if healthy:
   # A fresh exact broker-native heartbeat supersedes this account's offline error.
   # This does not change desired/effective trading switches or order authority.
   if cid=="38f731a629055234670f5a86f5409eba" and broker=="FP Markets" and server=="FPMarketsSC-Live":
    c.execute("""UPDATE apex_trade_controls SET last_error=NULL,updated_at=?
      WHERE connection_id=? AND effective_enabled=0
      AND last_error IN ('MT5_WORKER_NOT_RUNNING','BROKER_HEARTBEAT_TEMPORARILY_MISSING','BROKER_HEARTBEAT_TIMEOUT')""",(now,cid))
   if old!="CONNECTED":
    c.execute("""UPDATE apex_mt5_connections SET status='CONNECTED',
       broker_verified_at=?,updated_at=? WHERE id=? AND account_id=?""",
       (now,now,cid,owner))
    # Recovery does not grant permissions or change an effective kill switch.
    event(c,cid,owner,"NATIVE_HEARTBEAT_CONNECTED","fresh_broker_session_no_trading")
  elif not running:
   c.execute("""UPDATE apex_mt5_connections SET status='ERROR',
     broker_verified_at=NULL,worker_binding=NULL,updated_at=?
     WHERE id=? AND account_id=?""",(now,cid,owner))
   c.execute("""UPDATE apex_trade_controls SET effective_enabled=0,
     last_error='MT5_WORKER_NOT_RUNNING',updated_at=? WHERE connection_id=?""",(now,cid))
   if old!="ERROR":
    event(c,cid,owner,"NATIVE_HEARTBEAT_LOST","worker_no_longer_active")
  elif old=="CONNECTED":
   # Immediately retract Connected, but allow transient broker reconnection.
   c.execute("""UPDATE apex_mt5_connections SET status='CONNECTING',
     broker_verified_at=NULL,updated_at=? WHERE id=? AND account_id=?""",
     (now,cid,owner))
   c.execute("""UPDATE apex_trade_controls SET effective_enabled=0,
     last_error='BROKER_HEARTBEAT_TEMPORARILY_MISSING',updated_at=? WHERE connection_id=?""",
     (now,cid))
   event(c,cid,owner,"NATIVE_HEARTBEAT_REVERIFYING","worker_kept_alive_trading_off")
  # FP Markets terminals can spend up to 240 seconds authenticating. Do not
  # report ERROR while an isolated FP broker session is still attempting login.
  # Preserve the existing Deriv/IC 60-second startup gate unchanged.
  elif old=="CONNECTING" and now-updated>(300 if broker=="FP Markets" else 60):
   c.execute("""UPDATE apex_mt5_connections SET status='ERROR',
     broker_verified_at=NULL,updated_at=? WHERE id=? AND account_id=?""",
     (now,cid,owner))
   c.execute("""UPDATE apex_trade_controls SET effective_enabled=0,
     last_error='BROKER_HEARTBEAT_TIMEOUT',updated_at=? WHERE connection_id=?""",(now,cid))
   event(c,cid,owner,"NATIVE_HEARTBEAT_LOST","worker_active_but_unverified")
  c.execute("COMMIT")
def monitoring():
 while True:
  try:
   with db() as c:
    rows=c.execute("""SELECT id,account_id,broker,broker_server FROM apex_mt5_connections
      WHERE (worker_binding LIKE 'abutron-client-mt5-%' OR status='ERROR')
      AND status IN ('CONNECTING','CONNECTED','ERROR')""").fetchall()
   for cid,owner,broker,server in rows:
    try:
     update_state(cid,owner,broker,server)
     recover_offline_demo(cid,owner,broker,server)
    except Exception:pass
  except Exception:pass
  time.sleep(5)

def seats(c,owner):
 row=c.execute("""SELECT plan,status FROM apex_crm_licenses WHERE account_id=?""",(owner,)).fetchone()
 if row and row[1]=="active":
  return {"Starter":1,"Professional":2,"Enterprise":3}.get(row[0],1)
 return 1 # One non-trading DEMO connection for approved, unlicensed customer
def connect(x):
 needed={"op","owner","broker","server","login","password","mode","connection_id"}
 if set(x)!=needed:return out(422,"Invalid MT5 request fields")
 owner=x.get("owner");broker=x.get("broker");server=x.get("server")
 login=x.get("login");passwd=x.get("password");cid=x.get("connection_id")
 if not all(isinstance(v,str) for v in (owner,broker,server,login,passwd)):
  return out(422,"Invalid MT5 field types")
 if not CID.fullmatch(owner) or not LOGIN.fullmatch(login) or (broker,server) not in ALLOWED or x["mode"]!=expected_mode(broker,server):
  return out(422,"Approved MT5 account mode and exact broker server required")
 if len(passwd)<1 or len(passwd)>160 or any(ord(ch)<32 for ch in passwd):
  return out(422,"Invalid broker password format")
 if cid is not None and (not isinstance(cid,str) or not CID.fullmatch(cid)):
  return out(422,"Invalid existing connection")
 proof_script=("AbutronFPMarketsNativeFeedV2.ex5" if broker=="FP Markets" else "AbutronBrokerNativeFeedV2.ex5")
 if not TEMPLATE.joinpath("terminal64.exe").is_file() or not TEMPLATE.joinpath("MQL5/Scripts/ABUTRON",proof_script).is_file():
  return out(503,"Isolated MT5 terminal installation is not ready")
 with g_lock:
  if len(active)>=3:return out(503,"All dedicated terminal startup slots are busy")
  with db() as c:
   status=c.execute("SELECT status FROM accounts WHERE id=?",(owner,)).fetchone()
   if not status or status[0]!="approved":return out(403,"ABUTRON account email verification required")
   existing=c.execute("""SELECT id,status FROM apex_mt5_connections WHERE account_id=?
    AND broker=? AND environment=? AND account_reference=? AND broker_server=?""",
    (owner,broker,x["mode"],login,server)).fetchone()
   if existing:
    if cid is not None and cid!=existing[0]:return out(409,"Selected MT5 account does not match")
    cid=existing[0]
    if existing[1]=="CONNECTED" and attest(cid,broker,server):
     return out(200,"MT5 account already authenticated and connected",
      connection_id=cid,connection_status="CONNECTED",persistent_broker_session=True,trading_enabled=False)
   elif cid is not None:return out(409,"Existing account details do not match the selected MT5 account")
   else:cid=secrets.token_hex(16)
   if cid in active or service_active(cid):return out(409,"This MT5 terminal is already starting")
   used=c.execute("""SELECT COUNT(*) FROM apex_mt5_connections
     WHERE account_id=? AND status IN ('CONNECTING','CONNECTED')
       AND worker_binding LIKE 'abutron-client-mt5-%' AND id!=?""",(owner,cid)).fetchone()[0]
   if used>=seats(c,owner):return out(409,"Maximum connected MT5 accounts for this plan reached")
   attempts=c.execute("""SELECT COUNT(*) FROM apex_mt5_direct_attempts WHERE account_id=?
     AND created_at>?""",(owner,int(time.time())-900)).fetchone()[0]
   if attempts>=5:return out(429,"Too many broker login attempts; retry later")
  active.add(cid)
 started=False
 secretfile=SECRETS/(cid+"-"+secrets.token_hex(6))
 try:
  secretfile.write_text(json.dumps({"id":cid,"broker":broker,"server":server,
   "login":login,"password":passwd,"mode":x["mode"]},separators=(",",":")))
  secretfile.chmod(0o600)
  encrypted=seal_credential(cid,secretfile)
  launch_worker(cid,broker,x["mode"],encrypted)
  started=True
  now=int(time.time())
  with db() as c:
   c.execute("BEGIN IMMEDIATE")
   c.execute("INSERT INTO apex_mt5_direct_attempts(account_id,connection_id,created_at) VALUES(?,?,?)",
             (owner,cid,now))
   if existing:
    c.execute("""UPDATE apex_mt5_connections SET status='CONNECTING',
      broker_verified_at=NULL,worker_binding=?,updated_at=? WHERE id=? AND account_id=?""",
      (unit(cid),now,cid,owner))
   else:
    c.execute("""INSERT INTO apex_mt5_connections (id,account_id,broker,environment,
      account_reference,broker_server,status,broker_verified_at,worker_binding,created_at,updated_at)
      VALUES(?,?,?,?,?,?,'CONNECTING',NULL,?,?,?)""",
      (cid,owner,broker,x["mode"],login,server,unit(cid),now,now))
   c.execute("""INSERT INTO apex_trade_controls
     (connection_id,desired_enabled,effective_enabled,updated_at)
     VALUES(?,0,0,?) ON CONFLICT(connection_id) DO UPDATE SET
     desired_enabled=0,effective_enabled=0,updated_at=excluded.updated_at""",(cid,now))
   event(c,cid,owner,"DEDICATED_MT5_CONNECT_STARTED","no_trading_permissions")
   c.execute("COMMIT")
  return out(202,"Dedicated MT5 terminal launched. Checking broker session.",
     connection_id=cid,connection_status="CONNECTING",persistent_broker_session=False,trading_enabled=False)
 except Exception:
  if started:
   subprocess.run(["systemctl","stop",unit(cid)+".service"],
    timeout=12,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  # Requiring an explicit fresh login after a failed startup is safer than
  # retaining an encrypted credential from an unverified broker session.
  if not started:sealed_path(cid).unlink(missing_ok=True)
  return out(503,"Dedicated MT5 terminal could not start; no broker connection confirmed")
 finally:
  secretfile.unlink(missing_ok=True)
  active.discard(cid)
def disconnect(x):
 if set(x)!={"op","owner","connection_id"}:return out(422,"Invalid disconnect fields")
 owner=x["owner"];cid=x["connection_id"]
 if not isinstance(owner,str) or not isinstance(cid,str) or not CID.fullmatch(owner) or not CID.fullmatch(cid):
  return out(422,"Invalid account reference")
 with db() as c:
  row=c.execute("SELECT status FROM apex_mt5_connections WHERE account_id=? AND id=?",(owner,cid)).fetchone()
  if not row:return out(404,"Trading account not found")
  eff=c.execute("SELECT effective_enabled FROM apex_trade_controls WHERE connection_id=?",(cid,)).fetchone()
  if eff and eff[0]:return out(409,"Disable trading before disconnect")
 try:
  subprocess.run(["systemctl","stop",unit(cid)+".service"],timeout=30,
    check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  if service_active(cid):return out(503,"Terminal shutdown not confirmed; no disconnect committed")
 except (OSError,subprocess.TimeoutExpired):
  return out(503,"Terminal shutdown not confirmed")
 with db() as c:
  now=int(time.time());c.execute("BEGIN IMMEDIATE")
  c.execute("""UPDATE apex_mt5_connections SET status='DISCONNECTED',broker_verified_at=NULL,
    worker_binding=NULL,updated_at=? WHERE id=? AND account_id=?""",(now,cid,owner))
  c.execute("""UPDATE apex_trade_controls SET desired_enabled=0,effective_enabled=0,
    updated_at=? WHERE connection_id=?""",(now,cid))
  event(c,cid,owner,"MT5_TERMINAL_DISCONNECTED","worker_stopped")
  c.execute("COMMIT")
 # A deliberate disconnect revokes the only host-encrypted restart credential.
 sealed_path(cid).unlink(missing_ok=True)
 return out(200,"MT5 terminal disconnected",connection_status="DISCONNECTED",trading_enabled=False)
def status_for(x):
 if set(x)!={"op","owner","connection_id"}:return out(422,"Invalid status request")
 owner=x.get("owner");cid=x.get("connection_id")
 if not isinstance(owner,str) or not isinstance(cid,str) or not CID.fullmatch(owner) or not CID.fullmatch(cid):
  return out(422,"Invalid account")
 with db() as c:
  row=c.execute("SELECT broker,broker_server,status FROM apex_mt5_connections WHERE id=? AND account_id=?",(cid,owner)).fetchone()
 if not row:return out(404,"Account not found")
 broker,server,current=row
 verified=current=="CONNECTED" and attest(cid,broker,server)
 running=service_active(cid)
 reported=("CONNECTED" if verified else
           ("ERROR" if current=="ERROR" or (current=="CONNECTING" and not running) else
            ("CONNECTING" if current=="CONNECTING" and running else "NOT_CONNECTED")))
 category="NONE"
 if reported=="ERROR":
  category="BROKER_SESSION_UNVERIFIED"
  try:
   hp=state(cid)/"worker-health.json"
   if hp.is_file():
    health=json.loads(hp.read_text())
    raw=health.get("status")
    category={"STARTING":"WORKER_STARTUP_ERROR",
      "PROCESS_EXITED":"MT5_TERMINAL_EXITED",
      "AUTH_TIMEOUT":"BROKER_AUTH_TIMEOUT",
      "BROKER_SESSION_LOST":"BROKER_SESSION_LOST"}.get(raw,"BROKER_SESSION_UNVERIFIED")
  except (OSError,ValueError,TypeError):
   pass
 return out(200,"MT5 connection state",connection_id=cid,
  connection_status=reported,failure_category=category,
  persistent_broker_session=verified,trading_enabled=False)

def dispatch(conn):
 with conn:
  response=None
  try:
   pid,uid,gid=struct.unpack("3i",conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
   if uid!=pwd.getpwnam("apexsignup").pw_uid:response=out(403,"Unauthorized local caller")
   else:
    conn.settimeout(5);buf=b""
    while not buf.endswith(b"\n") and len(buf)<2048:
     chunk=conn.recv(2048-len(buf))
     if not chunk:break
     buf+=chunk
    if not buf.endswith(b"\n") or len(buf)>=2048:response=out(413,"Invalid request size")
    else:
     doc=json.loads(buf)
     if doc=={"op":"probe"}:response=out(200,"MT5 local supervisor ready",
       persistent_client_sessions_ready=True,private_gateway_ready=True,
       customer_password_login_enabled=True,live_mt5_login_enabled=True,trading_authorized=False)
     elif isinstance(doc,dict) and doc.get("op")=="connect":response=connect(doc)
     elif isinstance(doc,dict) and doc.get("op")=="disconnect":response=disconnect(doc)
     elif isinstance(doc,dict) and doc.get("op")=="status":response=status_for(doc)
     else:response=out(422,"Unsupported MT5 operation")
  except Exception:response=out(503,"MT5 terminal service error")
  try:conn.sendall(json.dumps(response,separators=(",",":")).encode()+b"\n")
  except OSError:pass
def main():
 ROOT.mkdir(parents=True,exist_ok=True)
 SECRETS.mkdir(parents=True,exist_ok=True,mode=0o700)
 SECRETS.chmod(0o700)
 ensure_sealed_store()
 if SOCK.exists():SOCK.unlink()
 sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
 sock.bind(str(SOCK));sock.listen(12)
 os.chown(SOCK,0,grp.getgrnam("apexsignup").gr_gid);os.chmod(SOCK,0o660)
 threading.Thread(target=monitoring,daemon=True).start()
 while True:
  conn,_=sock.accept()
  threading.Thread(target=dispatch,args=(conn,),daemon=True).start()
if __name__=="__main__":main()
