#!/usr/bin/python3
"""ABUTRON client MT5 worker: isolated UID, broker-native feed plus gated order bridge.
MT5 credentials arrive via systemd's private runtime credential mount, not argv/env/CRM.
"""
import os,sys,json,subprocess,time,shutil,secrets,uuid,signal
from pathlib import Path
SRC=Path("/opt/abutron/client-mt5-template-v3")
WINE="/opt/abutron/apex-wine-source/bin/wine"
ALLOWED={("Deriv","DerivBVI-Server-02"):"DERIV_BVI",
 ("Deriv","DerivSVG-Server"):"DERIV_SVG"}
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

def main():
 # Keep a single isolated Xvfb display alive across the ENTIRE MT5 update
 # lifecycle. xvfb-run shuts down its X server when the launched command exits;
 # it must wrap this supervisor, not each individual terminal launch.
 if os.environ.get("ABUTRON_MT5_XVFB_CHILD") != "1":
  env = dict(os.environ)
  env["ABUTRON_MT5_XVFB_CHILD"] = "1"
  cmd = ["/usr/bin/xvfb-run", "-a", "-s", "-screen 0 1280x800x24 -nolisten tcp",
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
 if len(cid)!=32 or (broker,server) not in ALLOWED or doc["mode"]!="LIVE":
  raise RuntimeError("Invalid broker identity")
 if not str(login).isdigit() or not str(doc["password"]):raise RuntimeError("Invalid MT5 credentials")
 terminal=state/"terminal";prefix=state/"wine";health=state/"worker-health.json"
 status(health,{"status":"STARTING","id":cid,"heartbeat_fresh":False})
 # The manager only starts this worker after the previous service is stopped.
 # Never reuse a failed terminal profile carrying stale or inherited broker cache.
 if terminal.exists():
  shutil.rmtree(terminal)
 shutil.copytree(SRC,terminal,symlinks=False)
 # LIVE isolation: drop all inherited order EA binaries and ABUTRON presets.
 experts=terminal/"MQL5"/"Experts"/"ABUTRON"
 if experts.is_dir():
  for f in experts.glob("*.ex5"):f.unlink()
 presets=terminal/"MQL5"/"Presets"
 if presets.is_dir():
  for f in presets.glob("*ABUTRON*.set"):f.unlink()
 if experts.is_dir() and list(experts.glob("*.ex5")):
  raise RuntimeError("LIVE_ORDER_EA_NOT_REMOVED")
 assert terminal.joinpath("terminal64.exe").is_file()
 assert terminal.joinpath("Config/servers.dat").is_file()
 # Only an exact pinned, orderless EA is permitted in this LIVE terminal.
 # Startup scripts exit after one run and cannot sustain the broker heartbeat.
 import hashlib
 trusted=Path("/usr/local/lib/abutron-deriv-live-proof/AbutronDerivLiveReadonlyEvidenceV1.ex5")
 expected_sha="5bc1d33b39c19a3d4eb31822e272c2a856ded512121a42ee8465e29d2d0dee6e"
 if not trusted.is_file() or trusted.is_symlink() or hashlib.sha256(trusted.read_bytes()).hexdigest()!=expected_sha:
  raise RuntimeError("DERIV_LIVE_READONLY_EA_PIN_MISSING_OR_CHANGED")
 experts.mkdir(parents=True,exist_ok=True)
 target=experts/"AbutronDerivLiveReadonlyEvidenceV1.ex5"
 shutil.copy2(trusted,target)
 if hashlib.sha256(target.read_bytes()).hexdigest()!=expected_sha or list(experts.glob("*.ex5"))!=[target]:
  raise RuntimeError("DERIV_LIVE_EXCLUSIVE_NO_ORDER_EA_CERTIFICATION_FAILED")
 # LIVE 0178 only: existing-position SL trailing (TRADE_ACTION_SLTP), no entries.
 trailing0178=(cid=="d43ff966c0c1bef5ec005fbd6ad4c0cf"
               and server=="DerivSVG-Server" and str(login).endswith("0178"))
 if trailing0178:
  trailing_sha="1fae63a5eb92a0adc249a23d2bfddd8af1e00aed397f737e69284610fd442caa"
  trusted_trailing=Path("/usr/local/lib/abutron-deriv-live-trailing-0178/AbutronLive0178TrailingOnly.ex5")
  if (not trusted_trailing.is_file() or trusted_trailing.is_symlink()
      or hashlib.sha256(trusted_trailing.read_bytes()).hexdigest()!=trailing_sha):
   raise RuntimeError("LIVE0178_TRAILING_RELEASE_UNVERIFIED")
  trailing_target=experts/"AbutronLive0178TrailingOnly.ex5"
  shutil.copy2(trusted_trailing,trailing_target)
  if (hashlib.sha256(trailing_target.read_bytes()).hexdigest()!=trailing_sha or
      set(experts.glob("*.ex5"))!={target,trailing_target}):
   raise RuntimeError("LIVE0178_TRAILING_INSTALL_FAILED")
  charts=terminal/"MQL5"/"Profiles"/"Charts"/"Default"
  charts.mkdir(parents=True,exist_ok=True)
  original=charts/"chart01.chr"
  if not original.exists():
   base=Path("/usr/local/lib/abutron-deriv-live-trailing-0178/BaseChart01.chr")
   if (not base.is_file() or base.is_symlink() or
       hashlib.sha256(base.read_bytes()).hexdigest()!="da614ed8e15c943977efd76ba06108d298f48cfa07cf372e539a4410bb9bcf71"):
    raise RuntimeError("LIVE0178_TRAILING_BASE_CHART_MISSING_OR_CHANGED")
   shutil.copy2(base,original)
  text=original.read_bytes().decode("utf-16le")
  if text.count("</chart>")!=1 or "<expert>" in text:
   raise RuntimeError("LIVE0178_BASE_CHART_UNEXPECTED")
  name="AbutronLive0178TrailingOnly"
  expert=("<expert>\r\nname="+name+"\r\npath=Experts\\\\ABUTRON\\\\"+name+
          ".ex5\r\nexpertmode=1\r\n<inputs>\r\nEnableTrailingStop=true\r\n</inputs>\r\n</expert>\r\n")
  text=text.replace("id=0\r\n","id=17982026\r\n",1)
  (charts/"chart02.chr").write_bytes(text.replace("</chart>",expert+"</chart>").encode("utf-16le"))
  (charts/"order.wnd").write_bytes("\ufeffchart01.chr\r\nchart02.chr\r\n".encode("utf-16le"))
 # Retire all bundled startup order-capable scripts from this LIVE profile.
 scripts=terminal/"MQL5"/"Scripts"/"ABUTRON"
 if scripts.is_dir():
  for f in scripts.glob("*.ex5"):f.unlink()
 files=terminal/"MQL5"/"Files";files.mkdir(parents=True,exist_ok=True)
 nonce=secrets.token_hex(16);challenge_owner=str(uuid.uuid4())
 challenge=files/"ABUTRON_MT5_CUSTOMER_CHALLENGE_V6.txt"
 challenge.write_text("\r\n".join(["ABUTRON_MT5_CUSTOMER_V6",nonce,challenge_owner,
  ALLOWED[(broker,server)],login,server,"LIVE"])+"\r\n")
 auth=runtime/"auth.ini"
 auth.write_text("[Common]\r\nLogin="+login+"\r\nPassword="+doc["password"]+
  "\r\nServer="+server+"\r\nKeepPrivate=0\r\nProxyEnable=0\r\n"+
  "[Experts]\r\nEnabled=1\r\nAllowLiveTrading="+("1" if trailing0178 else "0")+"\r\nAllowDllImport=0\r\n"+
  "[StartUp]\r\n"+"Expert=ABUTRON\\AbutronDerivLiveReadonlyEvidenceV1\r\n"+
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
 proof={"nonce":nonce,"proof_owner":challenge_owner,"broker":broker,"server":server,"mode":"LIVE"}
 started=time.monotonic();last_ok=0.0;was_connected=False
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
      ALLOWED[(broker,server)],server,"LIVE","CONNECTED","NO_ORDER_FUNCTIONS"]
     authenticated=bool(fresh and lines==expected)
    else:authenticated=False
    if authenticated:
     was_connected=True;last_ok=time.monotonic()
     if auth.exists():auth.unlink()
     status(health,{**proof,"status":"CONNECTED","id":cid,
        "heartbeat_fresh":True,"verified_at":int(time.time())})
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
         ALLOWED[(broker,server)],server,"LIVE","CONNECTED","NO_ORDER_FUNCTIONS"]
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
