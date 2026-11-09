#!/usr/bin/env python3
"""ABUTRONFX-owned APEX read-only signal audit; never imports order executor.

Produces a fresh monitoring heartbeat even when broker candles are stale.
Does not fake market data, authorized trading, or a broker session.
"""
import sys,json,os,hashlib,tempfile
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,"/opt/apex/runtime")
from apex_signal_router import route,read
DATA=Path("/var/lib/apex")
OUT=Path("/var/lib/apex-shadow/health.json")
now=datetime.now(timezone.utc)
sources={
 "scan":DATA/"scanner/latest.json",
 "market":DATA/"mt5-market/deriv_demo_bars.json",
 "account":DATA/"mt5-market/deriv_demo_account.json",
 "risk":DATA/"risk/latest.json",
 "policy":Path("/etc/apex/trading-policy.json")
}
items={name:read(path) for name,path in sources.items()}
result=route(items["scan"],items["market"],items["account"],items["risk"],items["policy"],now)
result["signal_source"]="ABUTRONFX_LOCAL_APEX_READONLY"
result["source_server_dependency"]=False
result["orders_submitted_by_router"]=0
result["destination_execution_enabled"]=False
result["can_fanout_to_customers"]=False
result["snapshot_sources"]={}
for name,p in sources.items():
 doc=items[name]
 result["snapshot_sources"][name]={
  "present":bool(doc),"source_timestamp":doc.get("generated_at_utc") if doc else None,
  "sha256":hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
 }
result["migration_gate"]="LOCKED_BROKER_AND_POSITIONS_UNRECONCILED"
assert result["orders_submitted_by_router"]==0
assert result["status"]!="APPROVED_FOR_DEMO_EXECUTION" or result["execution_allowed"] is True
OUT.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix=".apex-shadow-",dir=str(OUT.parent))
try:
 with os.fdopen(fd,"w") as f:json.dump(result,f,indent=2,allow_nan=False)
 os.chmod(tmp,0o640);os.replace(tmp,OUT)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print("APEX_SHADOW",result["status"],"QUALIFIED",result["qualified_count"],
      "ORDERS",result["orders_submitted_by_router"],"BLOCKERS",",".join(result["blockers"]))
