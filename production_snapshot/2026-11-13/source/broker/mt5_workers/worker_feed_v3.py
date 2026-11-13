#!/usr/bin/python3
"""ABUTRON client MT5 worker: isolated dynamic UID, native broker heartbeat, no orders.
MT5 credentials arrive via systemd's private runtime credential mount, not argv/env/CRM.
"""
import os,sys,json,subprocess,time,shutil,secrets,uuid,signal
from pathlib import Path
SRC=Path("/opt/abutron/client-mt5-template-v3")
WINE="/opt/abutron/apex-wine-source/bin/wine"
ALLOWED={("Deriv","Deriv-Demo"):"DERIV_BVI",
 ("IC Markets","ICMarketsSC-Demo"):"IC_MARKETS",
 ("FP Markets","FPMarketsSC-Demo Server"):"FP_MARKETS"}
def status(path,obj):
 tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(obj,separators=(",",":")))
 tmp.chmod(0o600);os.replace(tmp,path)
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
 if len(cid)!=32 or (broker,server) not in ALLOWED or doc["mode"]!="DEMO":
  raise RuntimeError("Invalid broker identity")
 if not str(login).isdigit() or not str(doc["password"]):raise RuntimeError("Invalid MT5 credentials")
 terminal=state/"terminal";prefix=state/"wine";health=state/"worker-health.json"
 status(health,{"status":"STARTING","id":cid,"heartbeat_fresh":False})
 # The manager only starts this worker after the previous service is stopped.
 # Never reuse a failed terminal profile carrying stale or inherited broker cache.
 if terminal.exists():
  shutil.rmtree(terminal)
 shutil.copytree(SRC,terminal,symlinks=False)
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
  "[Experts]\r\nEnabled=1\r\nAllowLiveTrading=0\r\nAllowDllImport=0\r\n"+
  "[StartUp]\r\nScript=ABUTRON\\AbutronBrokerNativeFeedV2\r\n"+
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
 # The official Python IPC bridge is not used here, and this never submits orders.
 heartbeat=files/("ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt")
 proof={"nonce":nonce,"proof_owner":challenge_owner,"broker":broker,"server":server,"mode":"DEMO"}
 started=time.monotonic();last_ok=0.0;was_connected=False
 process=None
 journal=terminal/"logs"/(time.strftime("%Y%m%d")+".log")
 try:
  for attempt in range(3):
   previous_bytes=journal.stat().st_size if journal.is_file() else 0
   process=subprocess.Popen(args,env=env,cwd=str(state),stdin=subprocess.DEVNULL,
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=False)
   while process.poll() is None:
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
    elif was_connected:
     status(health,{**proof,"status":"BROKER_SESSION_LOST","id":cid,
        "heartbeat_fresh":False})
    elif elapsed<240:
     status(health,{**proof,"status":"CONNECTING","id":cid,"heartbeat_fresh":False})
    else:
     status(health,{**proof,"status":"AUTH_TIMEOUT","id":cid,"heartbeat_fresh":False})
     return 2
    time.sleep(2)
   # A clean MT5 shutdown without the LiveUpdate handoff is not a login success.
   if process.returncode!=0 or was_connected or attempt==2 or time.monotonic()-started>220:
    break
   try:
    data=journal.read_bytes()
    if len(data)>previous_bytes:
     tail=data[previous_bytes:]
    else:
     tail=b""
    logtext=tail.decode("utf-16-le",errors="replace") if b"\x00" in tail[:80] else tail.decode("utf-8",errors="replace")
    # This must match an actual new per-attempt update-start journal event.
    update_handoff=("LiveUpdate" in logtext and "/update" in logtext and
                    "terminal64.exe" in logtext.lower())
   except (OSError,UnicodeError):
    update_handoff=False
   if not update_handoff:break
   status(health,{**proof,"status":"CONNECTING","id":cid,
        "heartbeat_fresh":False,"restart_reason":"MT5_LIVE_UPDATE","attempt":attempt+1})
   # Wait for MetaTrader's own updater to finish before relaunching.
   time.sleep(5)
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
