"""Validate and persist broker candle snapshots from the official MT5 exporter.

Forwards NO credentials/account identifiers and rejects unknown fields, source
changes, malformed OHLCV, timestamp regressions and unexpectedly large output.
"""
import datetime
import json
import math
import os
from pathlib import Path
import sys
import tempfile

DEST = Path("/var/lib/apex/mt5-market")
OUTPUT = DEST / "deriv_demo_bars.json"
MAX_BYTES = 7000000
PERIODS = frozenset(("M1","M5","M15","H1","H4","D1"))


def main():
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Market feed invalid length")
    obj = json.loads(raw)
    if set(obj) != {"schema","source","generated_at_utc","execution_enabled","data","failures"}:
        raise ValueError("Unknown snapshot keys")
    if obj["schema"] != "apex.mt5.market.v1" or obj["source"] != "Deriv DEMO MT5":
        raise ValueError("Untrusted source")
    if obj["execution_enabled"] is not False:
        raise ValueError("Trade permissions not allowed in feed")
    now = datetime.datetime.now(datetime.timezone.utc)
    ts = datetime.datetime.fromisoformat(obj["generated_at_utc"])
    if ts.tzinfo is None or abs((now - ts).total_seconds()) > 180:
        raise ValueError("Outdated export timestamp")
    data = obj["data"]
    if not isinstance(data,dict) or not 10 <= len(data) <= 13:
        raise ValueError("Unexpected synthetic instrument coverage")
    for symbol, frames in data.items():
        if not isinstance(symbol,str) or not symbol.endswith(" Index.0"):
            raise ValueError("Unexpected instrument type")
        if not isinstance(frames,dict) or not {"M5","H1"}.issubset(frames) or not set(frames).issubset(PERIODS):
            raise ValueError("Core timeframe missing")
        for period, bars in frames.items():
            if not isinstance(bars,list) or not 60 <= len(bars) <= 400:
                raise ValueError("Invalid candle count")
            previous = -1
            for bar in bars:
                if set(bar) != {"time","open","high","low","close","volume"}:
                    raise ValueError("Invalid candle shape")
                t = bar["time"]
                if type(t) is not int or t <= previous or t > int(now.timestamp()):
                    raise ValueError("Future/unsorted candle")
                previous=t
                values=[bar[k] for k in ("open","high","low","close")]
                if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):
                    raise ValueError("Invalid broker quote")
                if not (bar["high"] >= max(bar["open"],bar["close"])
                        and bar["low"] <= min(bar["open"],bar["close"])):
                    raise ValueError("Invalid OHLC relationship")
                if type(bar["volume"]) is not int or bar["volume"] < 0:
                    raise ValueError("Invalid tick volume")
    DEST.mkdir(parents=True,exist_ok=True)
    fd,name = tempfile.mkstemp(prefix=".deriv_demo_",suffix=".tmp",dir=DEST)
    try:
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),0o640)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name,OUTPUT)
    finally:
        if os.path.exists(name):os.unlink(name)
    print("APEX: verified Deriv DEMO market feed saved; instruments=%d; timeframe-sets=%d; source=broker-only; orders=disabled" %
          (len(data), sum(len(v) for v in data.values())))


if __name__ == "__main__":
    try: main()
    except Exception as e:
        sys.stderr.write("APEX feed validation failed: %s\n" % type(e).__name__)
        sys.exit(1)
