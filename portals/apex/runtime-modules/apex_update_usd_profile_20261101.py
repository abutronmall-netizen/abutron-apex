import json, tempfile, os
from pathlib import Path
from datetime import datetime, timezone
root=Path("/opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json")
p=json.loads(root.read_text())
b=json.loads(Path("/etc/apex/basket-policy.json").read_text())
assert set(b["lots"])=={row[0] for row in p["rows"]} and len(p["rows"])==13
for row in p["rows"]:
    row[1]=float(b["lots"][row[0]])
    row[2]=50.0
    row[3]=100.0
p["owner_override_at_utc"]=datetime.now(timezone.utc).isoformat()
p["owner_override_reason"]="2026-11-01: Each position TP 100 USD; SL 50 USD. No basket target."
p["definition"]="Independent broker-native USD gross SL/TP per position; fees and slippage excluded. No basket TP."
p["owner_override_lots"]=b["lots"]
fd,tmp=tempfile.mkstemp(prefix=".apex-usd-profile-",dir=root.parent)
with os.fdopen(fd,"w") as f:
    json.dump(p,f,indent=2);f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o644)
os.replace(tmp,root)
print("PROFILE_STAGED",len(p["rows"]),"SL_USD",50,"TP_USD",100,"LOTS_PRESERVED")
