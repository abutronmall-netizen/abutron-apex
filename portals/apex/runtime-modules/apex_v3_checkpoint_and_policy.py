"""Checkpoint APEX v2, then stage owner-approved v3 DEMO-only policy.
Requires v2 timer already stopped. Does not place broker orders.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,sqlite3,os,tempfile
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
base=Path("/var/lib/apex/demo-execution")
folder=base/"v3-checkpoints"/stamp
folder.mkdir(parents=True,mode=0o700,exist_ok=False)
paths=[
 Path("/etc/apex/trading-policy.json"),
 Path("/opt/apex/runtime/apex_demo_auto_v2.py"),
 Path("/opt/apex/runtime/apex_demo_usd_profile_v1.py"),
 Path("/opt/apex/runtime/apex_demo_feed_stage.py"),
 Path("/opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json"),
 Path("/opt/apex/runtime/apex_ui/telemetry.py"),
 Path("/opt/apex/runtime/apex_ui/static/index.html"),
 Path("/opt/apex/runtime/apex_ui/static/app.js"),
 Path("/opt/apex/runtime/apex_ui/static/style.css"),
]
for p in paths:
    name=p.as_posix().lstrip("/").replace("/","__")
    shutil.copy2(p,folder/name)
ledger=base/"attempts.sqlite"
with sqlite3.connect(str(ledger),timeout=10) as src:
    with sqlite3.connect(str(folder/"attempts.before-v3.sqlite")) as dst:
        src.backup(dst)
policy=paths[0]
d=json.loads(policy.read_text())
assert d["schema"]=="apex.trading.policy.v1" and d["environment"]=="DERIV_DEMO"
assert d["live_trading"] is False and d["automated_demo_execution"] is True
assert d["max_demo_loss_usd"]==140.0
d["max_demo_loss_usd"]=None
d["max_concurrent_positions"]=13
d["max_positions_per_symbol"]=1
d["description"]="APEX v3 Deriv USD DEMO only, 13 simultaneous max, one per symbol; independently broker-attached gross USD SL/TP and broker margin checks. No account-wide dollar loss budget. LIVE disabled. Stops can slip and costs affect net result."
fd,tmp=tempfile.mkstemp(prefix=".policy-v3-",dir=str(policy.parent))
try:
    with os.fdopen(fd,"w") as f:
        json.dump(d,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
    os.chown(tmp,policy.stat().st_uid,policy.stat().st_gid)
    os.chmod(tmp,policy.stat().st_mode&0o777)
    os.replace(tmp,policy)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print("CHECKPOINT",folder)
print("LEDGER_BACKUP",folder/"attempts.before-v3.sqlite")
print("OWNER_POLICY_UPDATED",{"LIVE":d["live_trading"],
     "max_demo_loss_usd":d["max_demo_loss_usd"],
     "max_concurrent_positions":13,"max_positions_per_symbol":1})
