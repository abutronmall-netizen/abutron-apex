"""Safety and correctness checks for the APEX shadow scanner."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from apex_fast_scanner import scan, validate_snapshot, EXPECTED, evaluate, frame_state

SNAP=Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
data=json.loads(SNAP.read_text())
now=datetime.now(timezone.utc)
r=scan(data,now)
assert r["symbol_count"]==13
assert len(r["instruments"])==13
assert all(len(x["indicators"])==6 for x in r["instruments"])
assert all(x["trade_ready"] is False and x["execution_authorized"] is False for x in r["instruments"])
assert all(x["proposal"] in ("HOLD","BUY","SELL") for x in r["instruments"])
assert all(x["proposal"]=="HOLD" for x in r["instruments"] if x["family"] in ("Boom","Crash"))
print("PASS exact 13 symbols and 6 timeframes")
print("PASS explicit trading and Crash/Boom gates")

for field,val in (("source","Yahoo Finance"),("execution_enabled",True)):
    mutated=copy.deepcopy(data);mutated[field]=val
    try:scan(mutated,now)
    except ValueError:pass
    else:raise AssertionError("untrusted source accepted: "+field)
print("PASS rejected nonbroker and broker-execution-enabled snapshots")

mutated=copy.deepcopy(data);mutated["data"].pop(EXPECTED[0])
try:scan(mutated,now)
except ValueError:pass
else:raise AssertionError("missing symbol accepted")
print("PASS missing symbols rejected")

mutated=copy.deepcopy(data);mutated["data"][EXPECTED[0]]["M5"][-1]["close"]=float("nan")
try:scan(mutated,now)
except ValueError:pass
else:raise AssertionError("nan accepted")
print("PASS invalid price rejected")

mutated=copy.deepcopy(data);mutated["data"][EXPECTED[0]]["M5"][-1]["time"]=mutated["data"][EXPECTED[0]]["M5"][-2]["time"]
try:scan(mutated,now)
except ValueError:pass
else:raise AssertionError("duplicate candle accepted")
print("PASS duplicated bars rejected")

mutated=copy.deepcopy(data);mutated["data"][EXPECTED[0]]["M1"][-1]["time"]=int(now.timestamp())-4000
try:scan(mutated,now)
except ValueError:pass
else:raise AssertionError("stale M1 accepted")
print("PASS stale timeframe rejected")

mutated=copy.deepcopy(data);mutated["generated_at_utc"]="2026-01-01T00:00:00+00:00"
try:scan(mutated,now)
except ValueError:pass
else:raise AssertionError("stale snapshot accepted")
print("PASS stale broker snapshot rejected")
print("RESULT: 8/8 categories PASS")
