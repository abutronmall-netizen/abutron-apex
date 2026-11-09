"""Strict validation and atomic save of Deriv MT5 DEMO M3/M30 closed candles."""
from datetime import datetime,timezone
from pathlib import Path
import json,math,os,sys,tempfile
from apex_fast_scanner import EXPECTED
OUT=Path("/var/lib/apex/mt5-market/deriv_demo_extra_candles.json")
FRAMES={"M3":180,"M30":1800}

def verify(data,now=None):
    now=now or datetime.now(timezone.utc)
    if (not isinstance(data,dict) or data.get("schema")!="apex.mt5.extra_candles.v1"
        or data.get("source")!="Deriv DEMO MT5"
        or data.get("execution_enabled") is not False
        or data.get("live_enabled") is not False
        or data.get("orders_placed")!=0):
        raise ValueError("Invalid broker source or unsafe status")
    stamped=datetime.fromisoformat(str(data.get("generated_at_utc","")).replace("Z","+00:00"))
    age=(now-stamped).total_seconds()
    if stamped.tzinfo is None or not -30<=age<=120:
        raise ValueError("Stale snapshot")
    x=data.get("data")
    if not isinstance(x,dict) or set(x)!=set(EXPECTED):
        raise ValueError("Incorrect 13-symbol coverage")
    for symbol,frames in x.items():
        if not isinstance(frames,dict) or set(frames)!=set(FRAMES):
            raise ValueError("M3/M30 timeframe coverage incomplete")
        for frame,seconds in FRAMES.items():
            candles=frames[frame]
            if not isinstance(candles,list) or not 2<=len(candles)<=5:
                raise ValueError("Too few broker bars")
            prior=-1
            for b in candles:
                t=b.get("time")
                if type(t) is not int or t<=prior or t%seconds:
                    raise ValueError("Unaligned or duplicate candle")
                prior=t
                o,h,l,c=(b.get(k) for k in ("open","high","low","close"))
                if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (o,h,l,c)):
                    raise ValueError("Invalid broker OHLC")
                if h<max(o,c) or l>min(o,c) or t+seconds>now.timestamp()-1:
                    raise ValueError("Incomplete candle or inconsistent OHLC")
            if now.timestamp()-(prior+seconds)>seconds+600:
                raise ValueError("Unreasonably stale timeframe")
    return data

def save(data,path=OUT):
    verify(data)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".extra-candle.")
    try:
        with os.fdopen(fd,"w",encoding="utf8") as output:
            json.dump(data,output,allow_nan=False,separators=(",",":"))
            output.flush();os.fsync(output.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

if __name__=="__main__":
    try:
        raw=sys.stdin.read(1_000_000)
        if len(raw)>=1_000_000:raise ValueError("Payload oversized")
        data=json.loads(raw)
        save(data)
        print(json.dumps({"status":"OK","source":data["source"],"symbols":len(data["data"]),
                         "frames":2,"orders":0,"generated_at_utc":data["generated_at_utc"]}))
    except (OSError,ValueError,KeyError,TypeError) as ex:
        print("APEX extra candles REJECTED "+type(ex).__name__,file=sys.stderr)
        raise SystemExit(1)
