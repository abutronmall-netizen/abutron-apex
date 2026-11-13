"""APEX broker data warehouse idempotency, quality, source validation tests."""
from datetime import datetime,timezone
from pathlib import Path
import tempfile,json,copy
from apex_broker_warehouse import connect,ingest
SOURCE=Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
source=json.loads(SOURCE.read_text())
with tempfile.TemporaryDirectory(prefix="apex-market-warehouse-test-") as td:
 c=connect(Path(td)/"test.sqlite")
 one=ingest(c,source)
 assert one["status"]=="OK"
 assert one["total_bars"]==13*6*400,one
 print("PASS 31,200 broker completed candles ingested")
 two=ingest(c,source)
 assert two["new_bars"]==0 and two["total_bars"]==one["total_bars"]
 print("PASS identical snapshot idempotent")
 updated=copy.deepcopy(source)
 name=next(iter(updated["data"]))
 bar=updated["data"][name]["M5"][10]
 bar["close"]=bar["open"] if bar["open"]!=bar["close"] else (bar["open"]+bar["high"])/2
 assert bar["close"] != source["data"][name]["M5"][10]["close"]
 three=ingest(c,updated)
 assert three["status"]=="CONFLICT" and three["conflicting_bar_count"]>=1
 assert three["new_bars"]==0
 print("PASS broker historical corrections flagged, never silently overwritten")
 bad=copy.deepcopy(source);bad["source"]="Yahoo Finance"
 try:ingest(c,bad)
 except ValueError:pass
 else:raise AssertionError("Nonbroker market data accepted")
 print("PASS other data sources rejected")
 bad=copy.deepcopy(source);bad["generated_at_utc"]="2026-01-01T00:00:00+00:00"
 try:ingest(c,bad)
 except ValueError:pass
 else:raise AssertionError("Stale broker snapshot accepted")
 print("PASS stale data rejected")
 assert c.execute("SELECT COUNT(*) FROM bars").fetchone()[0]==one["total_bars"]
 assert c.execute("SELECT COUNT(DISTINCT symbol) FROM bars").fetchone()[0]==13
 print("PASS source-backed, complete, 13-instrument historical query")
 c.close()
print("RESULT: 6/6 categories PASS")
