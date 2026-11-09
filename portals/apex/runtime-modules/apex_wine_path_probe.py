from pathlib import Path
import os
print("os.name",os.name)
for v in [r"Z:\etc\apex\trading-policy.json",r"Z:\var\lib\apex\scanner\latest.json",r"Z:\home\apexmt5\mt5-work\mt5-ui-final.log",r"Z:\opt\apex\runtime\apex_demo_gate_v2.py",r"C:\windows\system.ini"]:
 try:
  p=Path(v);print("PATH",v,"exists",p.exists(),"type",p.is_file())
  if p.is_file(): print("READ OK",len(p.read_bytes()))
 except Exception as e:print("ERR",type(e).__name__,str(e)[:100])
