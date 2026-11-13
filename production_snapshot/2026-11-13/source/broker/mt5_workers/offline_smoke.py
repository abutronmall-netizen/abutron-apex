#!/usr/bin/python3
"""Credential-free native MT5 startup script test. No broker login or order execution."""
import os,uuid,secrets,subprocess,shutil,time,json,pathlib
state=pathlib.Path(os.environ["STATE_DIRECTORY"])
root=state/"terminal"
src=pathlib.Path('/opt/abutron/client-mt5-template-v2')
shutil.copytree(src,root)
files=root/"MQL5"/"Files"
files.mkdir(parents=True)
nonce=secrets.token_hex(16)
owner=str(uuid.uuid4())
challenge=files/"ABUTRON_MT5_CUSTOMER_CHALLENGE_V6.txt"
challenge.write_text("\r\n".join(["ABUTRON_MT5_CUSTOMER_V6",nonce,owner,
 "DERIV_BVI","1234","Deriv-Demo","DEMO"])+"\r\n")
cfg=state/"test.ini"
cfg.write_text("[Experts]\r\nEnabled=1\r\nAllowLiveTrading=0\r\n"+
 "[StartUp]\r\nScript=ABUTRON\\AbutronClientHeartbeatV1\r\nSymbol=EURUSD\r\n"+
 "Period=H1\r\nShutdownTerminal=0\r\n")
env={**os.environ,"HOME":str(state),"WINEPREFIX":str(state/"prefix"),"WINEARCH":"win64",
 "WINEDEBUG":"-all","WINEDLLOVERRIDES":"mscoree,mshtml="}
argv=["/usr/bin/xvfb-run","-a","/opt/abutron/apex-wine-source/bin/wine",
 str(root/"terminal64.exe"),"/portable","/config:Z:"+str(cfg).replace("/","\\")]
p=subprocess.Popen(argv,env=env,cwd=state,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
hb=files/("ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt")
print('OFFLINE_NATIVE_SMOKE_STARTED_NO_CREDENTIALS',flush=True)
found=False
try:
 for i in range(24):
  if hb.is_file():
   lines=hb.read_text(encoding="utf-8-sig").splitlines()
   print('SMOKE_HEARTBEAT_FOUND',True,'OFFLINE_EXPECTED',lines[-2]=="OFFLINE",flush=True)
   found=True
   break
  if p.poll() is not None:print('MT5_EXITED',p.returncode,flush=True);break
  time.sleep(3)
 print('SMOKE_RESULT', 'NATIVE_SCRIPT_EXECUTED' if found else 'NATIVE_SCRIPT_NO_HEARTBEAT',flush=True)
 finally_work=False
finally:
 if p.poll() is None:
  p.terminate()
  try:p.wait(timeout=6)
  except subprocess.TimeoutExpired:p.kill()
