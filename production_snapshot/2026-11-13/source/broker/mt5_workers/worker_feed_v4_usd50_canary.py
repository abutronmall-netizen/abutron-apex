#!/usr/bin/python3
"""ABUTRON client MT5 worker: isolated UID, broker-native feed plus gated order bridge.
MT5 credentials arrive via systemd's private runtime credential mount, not argv/env/CRM.
"""
import os,sys,json,subprocess,time,shutil,secrets,uuid,signal
from pathlib import Path
SRC=Path("/opt/abutron/client-mt5-template-v3-usd-50-100-canary-20261103")
WINE="/opt/abutron/apex-wine-source/bin/wine"
ALLOWED={("Deriv","Deriv-Demo"):"DERIV_BVI",
 ("IC Markets","ICMarketsSC-Demo"):"IC_MARKETS",
 ("FP Markets","FPMarketsSC-Demo Server"):"FP_MARKETS"}
def status(path,obj):
 tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(obj,separators=(",",":")))
 tmp.chmod(0o600);os.replace(tmp,path)
def handoff_event(journal_bytes):
    """An MT5 updater handoff in exactly the newly appended journal range."""
    if not journal_bytes: return False
    try:
        text=journal_bytes.decode("utf-16-le",errors="replace") if b"\x00" in journal_bytes[:80] else journal_bytes.decode("utf-8",errors="replace")
    except UnicodeError:
        return False
    low=text.lower()
    return ("liveupdate" in low and "/update" in low and "terminal64.exe" in low)

def own_terminal_process(comm, argv, state_dir):
    """Identify only this account's MT5 terminal within its systemd cgroup."""
    if not isinstance(comm, str) or not isinstance(argv, str) or not isinstance(state_dir, str):
        return False
    if not state_dir.startswith("/var/lib/abutron-client-mt5-"):
        return False
    if comm.lower() not in ("main", "start.exe", "wine64-preloader", "wine-preloader",
                            "wine64", "terminal64.exe"):
        return False
    candidate=argv.replace(chr(92),"/").lower()
    expected=(state_dir.rstrip("/")+"/terminal/terminal64.exe").lower()
    return expected in candidate

def cgroup_terminal_running():
    """Follow a Wine LiveUpdate handoff, never a different customer's terminal."""
    try:
        state_dir=os.environ.get("STATE_DIRECTORY","")
        if not state_dir.startswith("/var/lib/abutron-client-mt5-"):
            return False
        expected_unit=Path(state_dir).name+".service"
        lines=Path("/proc/self/cgroup").read_text().splitlines()
        groups=[line.split("::",1)[1] for line in lines if line.startswith("0::")]
        if len(groups)!=1 or Path(groups[0]).name!=expected_unit:
            return False
        group=Path("/sys/fs/cgroup")/groups[0].lstrip("/")
        for raw in (group/"cgroup.procs").read_text().splitlines():
            if not raw.isdigit() or int(raw)==os.getpid():continue
            proc=Path("/proc")/raw
            try:
                comm=(proc/"comm").read_text().strip()
                argv=(proc/"cmdline").read_bytes().decode("utf-8","ignore")
                if own_terminal_process(comm,argv,state_dir):
                    return True
            except (FileNotFoundError,ProcessLookupError,PermissionError,UnicodeError):
                continue
    except (OSError,ValueError,IndexError):
        pass
    return False

def exit_action(returncode,was_connected,attached,handoff,attempt,total_elapsed):
    """No restart without fresh MT5 updater evidence; no trading permission changes."""
    if attached:return "MONITOR_CHILD"
    if was_connected:return "STOP"
    if returncode==0 and handoff and attempt<3 and total_elapsed<220:
        return "RETRY_UPDATE"
    return "STOP"

def restore_6207_audit_overlay(cid, broker, server, login, terminal):
    """Only one authenticated Deriv DEMO client receives its audited EA at boot."""
    target_cid="d6fc2524ec373b8d1bc278a8be3ec635"
    if cid!=target_cid:
        return False
    if broker!="Deriv" or server!="Deriv-Demo" or not str(login).endswith("6207"):
        raise RuntimeError("AUDIT_OVERRIDE_ACCOUNT_IDENTITY_FAIL_CLOSED")
    import hashlib
    override=Path("/opt/apex-client-mt5/overrides/deriv-demo-6207-execution-audit-v1")
    binary=override/"AbutronApexNativeOrderBridgeV2.ex5"
    preset=override/"ABUTRON_APEX_USD_50_100_APPROVED.set"
    expected_binary="ff4f353b09c7db996852972e5ad1caa63717337a2234b0fb7259515eede968bb"
    expected_preset="f6bf04a4c05ee23b37573fb8a8ade16074f2f4ff822c1e91bf4c09f916016d7f"
    for path,digest in ((binary,expected_binary),(preset,expected_preset)):
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError("AUDIT_OVERRIDE_SOURCE_HASH_INVALID")
    dest_ea=terminal/"MQL5/Experts/ABUTRON/AbutronApexNativeOrderBridgeV2.ex5"
    dest_preset=terminal/"MQL5/Presets/ABUTRON_APEX_USD_50_100_APPROVED.set"
    if not dest_ea.parent.is_dir() or not dest_preset.parent.is_dir():
        raise RuntimeError("AUDIT_OVERRIDE_DESTINATION_UNAVAILABLE")
    shutil.copyfile(binary,dest_ea)
    shutil.copyfile(preset,dest_preset)
    if hashlib.sha256(dest_ea.read_bytes()).hexdigest()!=expected_binary or hashlib.sha256(dest_preset.read_bytes()).hexdigest()!=expected_preset:
        raise RuntimeError("AUDIT_OVERRIDE_COPY_INTEGRITY_FAILED")
    return True



V4_6207_EX5_SHA256="c8422e0a98f9e02570b6f8b77e5cf890fd66676e1aa3b3cf9f7e552d08322d43"

def restore_6207_v4_inert_release(cid,broker,server,login,terminal):
    """Copy exact demo-only V4 release. Does NOT attach, authorize or enable orders."""
    target="d6fc2524ec373b8d1bc278a8be3ec635"
    if cid!=target:
        return False
    if broker!="Deriv" or server!="Deriv-Demo" or str(login)!="32456207":
        raise RuntimeError("V4_RELEASE_6207_ACCOUNT_IDENTITY_MISMATCH")
    import hashlib
    binary=Path("/usr/local/lib/abutron-6207-v4/AbutronApexExistingDerivV4_6207.ex5")
    dest=terminal/"MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5"
    if binary.is_symlink() or dest.is_symlink() or not binary.is_file():
        raise RuntimeError("V4_RELEASE_SYMLINK_OR_MISSING")
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=V4_6207_EX5_SHA256:
        raise RuntimeError("V4_RELEASE_BINARY_SHA256_NOT_APPROVED")
    if not dest.parent.is_dir():
        raise RuntimeError("V4_RELEASE_DESTINATION_NOT_PREPARED")
    shutil.copy2(binary,dest)
    if hashlib.sha256(dest.read_bytes()).hexdigest()!=V4_6207_EX5_SHA256:
        raise RuntimeError("V4_RELEASE_COPY_INTEGRITY_FAILED")
    return True



V4_SCOPED_DEMO={
 "9568525eee306da891258ad98c654919":("7593","6357593","ba95b6153cce90833d424cc94c3a776e0788af0bd794816ab20a5443deefa644"),
 "1ead1f08b44dc5ae284eadc9554b1381":("9244","202699244","f33a0822d114a1594a41aa7c458a7c6221415e7b4b6bc5e3c75882951e9da30c"),
}
V4_SCOPED_GUI_REPAIR_SHA={
 "7593":"b7cbd4fdc0caa12a9ed6235abe3441ba0e2b75498f1742d1dc5b37bc71216a66",
 "9244":"513af83a85f1ac7818b04e419591458a6cb3bde0756af12b743165a449d168f4",
}
def restore_scoped_deriv_v4(cid,broker,server,login,terminal):
 """Exact pinned account-bound DEMO writer, installed inert until own root guard."""
 import hashlib
 cfg=V4_SCOPED_DEMO.get(cid)
 if cfg is None:return False
 suffix,expected_login,sha=cfg
 if (broker,server,str(login))!=("Deriv","Deriv-Demo",expected_login):
  raise RuntimeError("WRONG_SCOPED_DERIV_DEMO_IDENTITY")
 source=Path("/usr/local/lib/abutron-deriv-v4")/suffix/("AbutronApexExistingDerivV4_"+suffix+".ex5")
 target=terminal/"MQL5/Experts/ABUTRON"/source.name
 if source.is_symlink() or not source.is_file() or target.is_symlink() or not target.parent.is_dir():
  raise RuntimeError("SCOPED_V4_RELEASE_PATH_INVALID")
 if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:
  raise RuntimeError("SCOPED_V4_RELEASE_SHA_INVALID")
 shutil.copy2(source,target)
 if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
  raise RuntimeError("SCOPED_V4_NATIVE_INSTALL_SHA_INVALID")
 return True

def main():
 # Keep a single isolated Xvfb display alive across the ENTIRE MT5 update
 # lifecycle. xvfb-run shuts down its X server when the launched command exits;
 # it must wrap this supervisor, not each individual terminal launch.
 if os.environ.get("ABUTRON_MT5_XVFB_CHILD") != "1":
  env = dict(os.environ)
  env["ABUTRON_MT5_XVFB_CHILD"] = "1"
  # Retain scoped DEMO X11 authorization for broker-verified MT5 options repair.
  scoped_name=Path(os.environ.get("STATE_DIRECTORY", "")).name.removeprefix("abutron-client-mt5-")
  scoped=(scoped_name in V4_SCOPED_DEMO)
  auth_arg=["-f",str(Path(os.environ["RUNTIME_DIRECTORY"])/"deriv-mt5-xauthority")] if scoped else []
  cmd = ["/usr/bin/xvfb-run", "-a", *auth_arg, "-s", "-screen 0 1280x800x24 -nolisten tcp",
         "/usr/bin/python3", "-B", os.path.abspath(__file__)]
  return subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        check=False).returncode
 if not os.environ.get("DISPLAY"):
  raise RuntimeError("Isolated MT5 X display missing")
 state=Path(os.environ["STATE_DIRECTORY"]);runtime=Path(os.environ["RUNTIME_DIRECTORY"])
 cred=Path(os.environ["CREDENTIALS_DIRECTORY"])/"mt5"
 if not cred.is_file():raise RuntimeError("Missing private systemd credential")
 doc=json.loads(cred.read_text())
 if set(doc)!={"id","broker","server","login","password","mode"}:raise RuntimeError("Invalid broker credential payload")
 cid=doc["id"];broker=doc["broker"];server=doc["server"];login=doc["login"]
 if len(cid)!=32 or (broker,server) not in ALLOWED or doc["mode"]!="DEMO":
  raise RuntimeError("Invalid broker identity")
 if not str(login).isdigit() or not str(doc["password"]):raise RuntimeError("Invalid MT5 credentials")
 terminal=state/"terminal";prefix=state/"wine";health=state/"worker-health.json"
 status(health,{"status":"STARTING","id":cid,"heartbeat_fresh":False})
 # The manager only starts this worker after the previous service is stopped.
 # Never reuse a failed terminal profile carrying stale or inherited broker cache.
 if terminal.exists():
  # Rename the stopped session as a unit: MT5 can leave files that a fresh
  # DynamicUser cannot unlink. Never recursively delete a broker session.
  if terminal.is_symlink() or not terminal.is_dir():
   raise RuntimeError("UNSAFE_EXISTING_BROKER_TERMINAL")
  retired=state/("terminal-retired-"+str(time.time_ns()))
  terminal.rename(retired)
 shutil.copytree(SRC,terminal,symlinks=False)
 restore_6207_audit_overlay(cid,broker,server,login,terminal)
 # Guarded 6207 DEMO bootstrap: local V4 inputs may be ON, but native
 # orders remain denied until authenticated guardian CLAIM/SEND, CRM ACK,
 # current broker risk and portfolio attestation pass independently.
 is_v4_6207=(cid=="d6fc2524ec373b8d1bc278a8be3ec635" and
             broker=="Deriv" and server=="Deriv-Demo" and doc["mode"]=="DEMO")
 is_v4_extra=(cid in V4_SCOPED_DEMO and broker=="Deriv" and
              server=="Deriv-Demo" and doc["mode"]=="DEMO")
 is_v4_target=is_v4_6207 or is_v4_extra
 v4_suffix="6207" if is_v4_6207 else (V4_SCOPED_DEMO[cid][0] if is_v4_extra else "")
 if is_v4_target:
  if is_v4_6207: restore_6207_v4_inert_release(cid,broker,server,login,terminal)
  else: restore_scoped_deriv_v4(cid,broker,server,login,terminal)
  # This is an MT5 INPUT preset, not an order authorization. The compiled EA
  # has no legacy V2/V3 order handler and its V4 guard fails closed.
  preset=terminal/"MQL5/Presets"/("ABUTRON_APEX11_V4_GUARDED_"+v4_suffix+".set")
  if preset.is_symlink():raise RuntimeError("V4_PRESET_SYMLINK_DENIED")
  preset.parent.mkdir(parents=True,exist_ok=True)
  preset.write_text(
      "EnableNativeDemoOrders=true||false||0||true||N\r\n"
      "EnableAdaptiveEquityV2=true||false||0||true||N\r\n"
      "AdaptiveV2ReconcilerApproved=true||false||0||true||N\r\n"
      "EnableApex11V4DemoOrders=true||false||0||true||N\r\n")
  preset.chmod(0o600)
 assert terminal.joinpath("terminal64.exe").is_file()
 assert terminal.joinpath("Config/servers.dat").is_file()
 # Update the read-only proof script even when reusing an existing client profile.
 # Otherwise failed accounts continue to run the older EX5 on their next attempt.
 trusted=SRC/"MQL5"/"Scripts"/"ABUTRON"/"AbutronBrokerNativeFeedV2.ex5"
 scripts=terminal/"MQL5"/"Scripts"/"ABUTRON"
 scripts.mkdir(parents=True,exist_ok=True)
 shutil.copy2(trusted,scripts/"AbutronBrokerNativeFeedV2.ex5")
 files=terminal/"MQL5"/"Files";files.mkdir(parents=True,exist_ok=True)
 nonce=secrets.token_hex(16);challenge_owner=str(uuid.uuid4())
 challenge=files/"ABUTRON_MT5_CUSTOMER_CHALLENGE_V6.txt"
 challenge.write_text("\r\n".join(["ABUTRON_MT5_CUSTOMER_V6",nonce,challenge_owner,
  ALLOWED[(broker,server)],login,server,"DEMO"])+"\r\n")
 auth=runtime/"auth.ini"
 auth.write_text("[Common]\r\nLogin="+login+"\r\nPassword="+doc["password"]+
  "\r\nServer="+server+"\r\nKeepPrivate=0\r\nProxyEnable=0\r\n"+
  "[Experts]\r\nEnabled=1\r\nAllowLiveTrading="+("1" if broker=="Deriv" and doc["mode"]=="DEMO" else "0")+"\r\nAllowDllImport=0\r\n"+
  "[StartUp]\r\n"+("Expert=ABUTRON\\AbutronApexExistingDerivV4_"+v4_suffix+"\r\n" if is_v4_target else ("Expert=ABUTRON\\AbutronApexNativeOrderBridgeV2\r\n" if broker=="Deriv" else ""))+("ExpertParameters=ABUTRON_APEX11_V4_GUARDED_"+v4_suffix+".set\r\n" if is_v4_target else ("ExpertParameters=ABUTRON_APEX_USD_50_100_APPROVED.set\r\n" if broker=="Deriv" else ""))+"Script=ABUTRON\\AbutronBrokerNativeFeedV2\r\n"+
  "Symbol="+("Volatility 10 Index.0" if broker=="Deriv" else "EURUSD")+
  "\r\nPeriod=M1\r\nShutdownTerminal=0\r\n")
 auth.chmod(0o600)
 doc["password"]=None
 env={**os.environ,"HOME":str(state),"WINEPREFIX":str(prefix),
    "WINEARCH":"win64","WINEDEBUG":"-all",
    "WINEDLLOVERRIDES":"mscoree,mshtml="}
 exe=terminal/"terminal64.exe"
 winconfig="Z:"+str(auth).replace("/","\\")
 args=[WINE,str(exe),"/portable","/config:"+winconfig]
 # MT5 may exit with code 0 to hand off an automatic LiveUpdate process.
 # Restart only if this specific event appears in the current launch's journal.
 # The official Python IPC bridge is not used. The native EA only accepts authorized per-account requests.
 heartbeat=files/("ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt")
 proof={"nonce":nonce,"proof_owner":challenge_owner,"broker":broker,"server":server,"mode":"DEMO"}
 started=time.monotonic();last_ok=0.0;was_connected=False
 # Only the authenticated Deriv DEMO 6207 worker may repair its own isolated
 # MT5 WebRequest allowlist after a fresh portable terminal profile rebuild.
 # This process does not authorize a broker order, CRM ON, or any other account.
 v4_webrequest_repair_attempts=0
 v4_webrequest_repair_last=started-60
 v4_webrequest_repair_proc=None
 process=None
 journal=terminal/"logs"/(time.strftime("%Y%m%d")+".log")
 try:
  # Bounded startup attempts; one session nonce, challenge and credential mount.
  # The Wine launcher may exit while LiveUpdate hands the real MT5 terminal
  # to a child within THIS systemd cgroup. Follow it without spawning another.
  for attempt in range(4):
   previous_bytes=journal.stat().st_size if journal.is_file() else 0
   process=subprocess.Popen(args,env=env,cwd=str(state),stdin=subprocess.DEVNULL,
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=False)
   post_exit_since=None
   while True:
    elapsed=time.monotonic()-started
    if heartbeat.is_file():
     try:lines=heartbeat.read_text(encoding="utf-8-sig").splitlines()
     except (OSError,UnicodeError):lines=[]
     try:fresh=time.time()-heartbeat.stat().st_mtime<13
     except OSError:fresh=False
     expected=["ABUTRON_MT5_NATIVE_HEARTBEAT_V1",nonce,challenge_owner,
      ALLOWED[(broker,server)],server,"DEMO","CONNECTED","NO_ORDER_FUNCTIONS"]
     authenticated=bool(fresh and lines==expected)
    else:authenticated=False
    if authenticated:
     was_connected=True;last_ok=time.monotonic()
     if auth.exists():auth.unlink()
     status(health,{**proof,"status":"CONNECTED","id":cid,
        "heartbeat_fresh":True,"verified_at":int(time.time())})
     if is_v4_target:
      cap=files/("ABUTRON_APEX_NATIVE_V4_CAPABILITY_"+nonce+".txt")
      try:cap_fresh=cap.is_file() and time.time()-cap.stat().st_mtime<12
      except OSError:cap_fresh=False
      if (time.monotonic()-started>15 and
          not cap_fresh and
          time.monotonic()-v4_webrequest_repair_last>=120 and
          (v4_webrequest_repair_proc is None or
           v4_webrequest_repair_proc.poll() is not None)):
       helper=Path("/opt/apex-client-mt5/abutron_mt5_"+v4_suffix+"_webrequest_recovery.py")
       import hashlib
       expected_repair_sha=("fa273a28a19d45d5eb6920c6a979c6da1803bf805e784125a9a834e3aa6c2f13"
                            if is_v4_6207 else V4_SCOPED_GUI_REPAIR_SHA[v4_suffix])
       if (helper.is_symlink() or not helper.is_file() or
           hashlib.sha256(helper.read_bytes()).hexdigest()!=expected_repair_sha):
        raise RuntimeError("V4_WEBREQUEST_REPAIR_HELPER_HASH_CHANGED")
       repair_log=state/("v4-webrequest-recovery-"+v4_suffix+".log")
       fd=os.open(repair_log,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
       with os.fdopen(fd,"ab") as repair_out:
        v4_webrequest_repair_proc=subprocess.Popen(
         ["/usr/bin/python3","-B",str(helper),"--nonce",nonce],
         cwd=str(state),env=env,stdin=subprocess.DEVNULL,
         stdout=repair_out,stderr=subprocess.STDOUT)
       v4_webrequest_repair_attempts+=1
       v4_webrequest_repair_last=time.monotonic()
    elif was_connected:
     status(health,{**proof,"status":"BROKER_SESSION_LOST","id":cid,
        "heartbeat_fresh":False})
    elif elapsed<240:
     status(health,{**proof,"status":"CONNECTING","id":cid,"heartbeat_fresh":False})
    else:
     status(health,{**proof,"status":"AUTH_TIMEOUT","id":cid,"heartbeat_fresh":False})
     return 2
    if process.poll() is None:
     post_exit_since=None
     time.sleep(2)
     continue
    if cgroup_terminal_running():
     # Wine's original Popen returned but the MT5 terminal is still alive.
     # Never detach this worker or mark Connected without fresh native proof.
     post_exit_since=None
     time.sleep(2)
     continue
    # A bounded grace allows the Wine updater to spawn its child after the
    # launcher exits. This must not be mistaken for a successful broker login.
    if post_exit_since is None:post_exit_since=time.monotonic()
    if process.returncode==0 and not was_connected and time.monotonic()-post_exit_since<12:
     time.sleep(1)
     continue
    break
   if process.returncode!=0 or was_connected or attempt>=3 or time.monotonic()-started>=220:
    break
   try:
    data=journal.read_bytes()
    tail=data[previous_bytes:] if len(data)>previous_bytes else b""
   except OSError:
    tail=b""
   decision=exit_action(process.returncode,was_connected,
              cgroup_terminal_running(),handoff_event(tail),attempt,time.monotonic()-started)
   if decision=="MONITOR_CHILD":
    # A late child appeared after the launcher exit. Monitor its proof using
    # the same exact account/session nonce; never spawn a competing terminal.
    while cgroup_terminal_running() and time.monotonic()-started<240:
     if heartbeat.is_file():
      try:
       lines=heartbeat.read_text(encoding="utf-8-sig").splitlines()
       fresh=time.time()-heartbeat.stat().st_mtime<13
      except (OSError,UnicodeError):
       lines=[];fresh=False
      expected=["ABUTRON_MT5_NATIVE_HEARTBEAT_V1",nonce,challenge_owner,
         ALLOWED[(broker,server)],server,"DEMO","CONNECTED","NO_ORDER_FUNCTIONS"]
      if fresh and lines==expected:
       was_connected=True
       if auth.exists():auth.unlink()
       status(health,{**proof,"status":"CONNECTED","id":cid,
              "heartbeat_fresh":True,"verified_at":int(time.time())})
      else:
       status(health,{**proof,"status":"BROKER_SESSION_LOST" if was_connected else "CONNECTING",
          "id":cid,"heartbeat_fresh":False})
     time.sleep(2)
    break
   if decision!="RETRY_UPDATE":break
   status(health,{**proof,"status":"CONNECTING","id":cid,
          "heartbeat_fresh":False,"restart_reason":"MT5_LIVE_UPDATE","attempt":attempt+1})
   time.sleep(4)
  status(health,{**proof,"status":"PROCESS_EXITED","id":cid,"heartbeat_fresh":False,
                 "process_exit_code":process.returncode})
  return 1
 finally:
  auth.unlink(missing_ok=True)
  if process is not None and process.poll() is None:
   process.terminate()
   try:process.wait(timeout=7)
   except subprocess.TimeoutExpired:process.kill()
if __name__=="__main__":
 try:sys.exit(main() or 0)
 except Exception:
  print("ISOLATED_MT5_WORKER_FAILED",file=sys.stderr)
  sys.exit(1)
