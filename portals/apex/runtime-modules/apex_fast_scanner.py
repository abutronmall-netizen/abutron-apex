"""APEX deterministic Deriv 13-instrument scanner. No trading or LLM dependency.

Uses strictly broker-provided completed candles from the MT5 exporter.
The strategy is experimental, not validated for profitable or live trading.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import math
import os
import tempfile

MARKET = Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
OUT = Path("/var/lib/apex/scanner")
EXPECTED = (
    "Volatility 10 Index.0", "Volatility 25 Index.0", "Volatility 50 Index.0",
    "Volatility 75 Index.0", "Volatility 100 Index.0",
    "Crash 150 Index.0", "Crash 300 Index.0", "Crash 600 Index.0",
    "Crash 1000 Index.0", "Boom 150 Index.0", "Boom 300 Index.0",
    "Boom 600 Index.0", "Boom 1000 Index.0",
)
FRAMES = ("M1", "M5", "M15", "H1", "H4", "D1")
FRAME_SECS = {"M1":60,"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}
MAX_SOURCE_AGE = 660
MAX_CLOSE_AGE = 900
MIN_HISTORY = 60


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def validate_snapshot(doc, now):
    if not isinstance(doc, dict) or doc.get("schema") != "apex.mt5.market.v1" or doc.get("source") != "Deriv DEMO MT5":
        raise ValueError("untrusted broker source")
    if doc.get("execution_enabled") is not False:
        raise ValueError("execution enabled in source; refusing")
    created = parse_time(doc["generated_at_utc"])
    if created.tzinfo is None or not -30 <= (now-created).total_seconds() <= MAX_SOURCE_AGE:
        raise ValueError("stale or future broker snapshot")
    data = doc.get("data", {})
    if not isinstance(data, dict) or set(data) != set(EXPECTED):
        raise ValueError("missing or unknown Deriv symbols")
    for symbol, frames in data.items():
        if not isinstance(frames, dict) or set(frames) != set(FRAMES):
            raise ValueError(f"incomplete timeframes: {symbol}")
        for frame in FRAMES:
            records = frames[frame]
            if not isinstance(records, list) or len(records) < MIN_HISTORY:
                raise ValueError(f"insufficient candles: {symbol} {frame}")
            previous_ts = -1
            for bar in records:
                ts = bar.get("time")
                if not isinstance(ts, int) or isinstance(ts, bool) or ts <= previous_ts:
                    raise ValueError(f"unsorted or duplicate candles: {symbol} {frame}")
                previous_ts = ts
                vals = [bar.get(k) for k in ("open","high","low","close")]
                if not all(finite(v) and v > 0 for v in vals):
                    raise ValueError(f"invalid bar price: {symbol} {frame}")
                o,h,l,c = (float(v) for v in vals)
                if h < max(o,c) or l > min(o,c):
                    raise ValueError(f"invalid OHLC range: {symbol} {frame}")
                if ts + FRAME_SECS[frame] > now.timestamp() + 1:
                    raise ValueError(f"incomplete or future candle: {symbol} {frame}")
            # H4/D1 may legitimately update less frequently; M1/M5 must be recent.
            if frame in ("M1", "M5") and now.timestamp()-records[-1]["time"] > MAX_CLOSE_AGE:
                raise ValueError(f"stale short timeframe: {symbol} {frame}")
    return data


def ema(values, period):
    current=sum(values[:period])/period
    alpha=2/(period+1)
    for value in values[period:]:
        current=alpha*value+(1-alpha)*current
    return current


def rsi(values, length=14):
    changes=[values[i]-values[i-1] for i in range(1,len(values))]
    gains=[max(0.0,v) for v in changes]
    losses=[max(0.0,-v) for v in changes]
    up=sum(gains[:length])/length
    dn=sum(losses[:length])/length
    for i in range(length,len(changes)):
        up=(up*(length-1)+gains[i])/length
        dn=(dn*(length-1)+losses[i])/length
    if up==dn==0:return 50.0
    if dn==0:return 100.0
    return 100 - 100/(1+up/dn)


def atr(rows,length=14):
    values=[]
    for i in range(1,len(rows)):
        r=rows[i]; prev=rows[i-1]["close"]
        values.append(max(r["high"]-r["low"],abs(r["high"]-prev),abs(r["low"]-prev)))
    current=sum(values[:length])/length
    for value in values[length:]:
        current=(current*(length-1)+value)/length
    return current


def frame_state(rows):
    closes=[float(x["close"]) for x in rows[-160:]]
    fast,slow=ema(closes,9),ema(closes,21)
    momentum=rsi(closes)
    a=atr(rows[-160:])
    direction="UP" if fast>slow and momentum>=50 else "DOWN" if fast<slow and momentum<=50 else "MIXED"
    return {"close":round(closes[-1],6),"ema9":round(fast,6),"ema21":round(slow,6),
            "rsi14":round(momentum,2),"atr14":round(a,6),"trend":direction,
            "bar_time":int(rows[-1]["time"])}


def m5_entry_quality(bar,indicator,side):
    """Conservative Deriv DEMO entry-only gate; never creates proposals."""
    try:
        atr=float(indicator["atr14"])
        close=float(bar["close"]);open_price=float(bar["open"])
        high=float(bar["high"]);low=float(bar["low"])
        ema9=float(indicator["ema9"])
        if (not all(math.isfinite(v) for v in (atr,close,open_price,high,low,ema9))
            or atr<=0 or high<=low or low<=0 or
            not low<=min(close,open_price)<=max(close,open_price)<=high):
            return "M5_ENTRY_EVIDENCE_INVALID"
        if abs(close-ema9)>0.65*atr:
            return "M5_ENTRY_OVEREXTENDED_FROM_EMA9"
        if abs(close-open_price)<0.35*atr:
            return "M5_ENTRY_CANDLE_BODY_TOO_WEAK"
        location=(close-low)/(high-low)
        if side=="BUY" and (close<=open_price or location<0.55):
            return "M5_ENTRY_BUY_NOT_CANDLE_CONFIRMED"
        if side=="SELL" and (close>=open_price or location>0.45):
            return "M5_ENTRY_SELL_NOT_CANDLE_CONFIRMED"
        return "PASS"
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
        return "M5_ENTRY_EVIDENCE_UNAVAILABLE"


def evaluate(symbol,frames):
    indicators={name:frame_state(frames[name]) for name in FRAMES}
    m5,m15,h1,h4=(indicators[x] for x in ("M5","M15","H1","H4"))
    alignment=(m15["trend"],h1["trend"],h4["trend"])
    family="Crash" if symbol.startswith("Crash ") else "Boom" if symbol.startswith("Boom ") else "Volatility"
    # M5 is the *primary* directional research timeframe. Higher TFs are
    # separate confirmation filters; a veto is not evidence that M5 has no signal.
    m5_signal={"UP":"BUY","DOWN":"SELL"}.get(m5["trend"],"HOLD")
    htf_signal="BUY" if alignment==("UP",)*3 else "SELL" if alignment==("DOWN",)*3 else "MIXED"
    proposal="HOLD"
    if m5_signal=="HOLD":
        reason=(f"M5 mixed: EMA9/EMA21 + RSI14={m5['rsi14']:.2f} do not confirm direction; "
                f"M15/H1/H4={alignment[0]}/{alignment[1]}/{alignment[2]}")
    elif htf_signal=="MIXED":
        reason=(f"M5 research {m5_signal}; higher TF conflict: "
                f"M15/H1/H4={alignment[0]}/{alignment[1]}/{alignment[2]}")
    elif m5_signal!=htf_signal:
        reason=f"M5 {m5_signal} conflicts with aligned M15/H1/H4 {htf_signal}"
    elif m5["atr14"]<=0:
        reason="M5 ATR unavailable: research setup not validated"
    elif m5_signal=="BUY" and not 53<=m5["rsi14"]<=70:
        reason=f"M5 BUY direction aligned but RSI14={m5['rsi14']:.2f} outside 53–70 entry filter"
    elif m5_signal=="SELL" and not 30<=m5["rsi14"]<=47:
        reason=f"M5 SELL direction aligned but RSI14={m5['rsi14']:.2f} outside 30–47 entry filter"
    elif family in ("Crash","Boom"):
        reason=f"M5 {m5_signal} confirmed; {family} spike-model requires separate testing"
    else:
        # Retain strict M15/H1/H4 alignment and RSI. Reject weak, opposite
        # or overextended completed M5 candles on Deriv synthetic indices.
        quality=m5_entry_quality(frames["M5"][-1],m5,m5_signal)
        if quality=="PASS":
            proposal=m5_signal
            reason=f"M5 {m5_signal} quality-confirmed; M15/H1/H4 and RSI14 aligned"
        else:
            reason=quality
    return {
        "symbol":symbol,"family":family,"proposal":proposal,"reason":reason,
        "m5_signal":m5_signal,"higher_tf_signal":htf_signal,
        "m5_confirmation":m5_signal!="HOLD" and m5_signal==htf_signal,
        "last_closed_m5":m5["bar_time"],"source":"Deriv MT5 completed candles",
        "indicators":indicators,
        "execution_authorized":False,"trade_ready":False,
        "risk_status":"NOT_CERTIFIED",
        "strategy":"apex_ema_rsi_mtf_research_v1",
    }


def scan(doc,now=None):
    now=now or utc_now()
    data=validate_snapshot(doc,now)
    results=[evaluate(symbol,data[symbol]) for symbol in EXPECTED]
    return {
        "schema":"apex.scanner.shadow.v1",
        "generated_at_utc":now.isoformat(),
        "broker_generated_at_utc":doc["generated_at_utc"],
        "source":"Deriv DEMO MT5",
        "strategy_status":"RESEARCH_ONLY_NOT_BACKTEST_CERTIFIED",
        "orders_enabled":False,"live_enabled":False,
        "symbol_count":len(results),"timeframes_per_symbol":len(FRAMES),
        "candidates":sum(x["proposal"]!="HOLD" for x in results),
        "instruments":results,
    }


def atomic_json(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix="."+path.name+".")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(content,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--snapshot",type=Path,default=MARKET)
    parser.add_argument("--out",type=Path,default=OUT)
    args=parser.parse_args()
    try:
        snapshot=json.loads(args.snapshot.read_text(encoding="utf-8"))
        result=scan(snapshot)
        atomic_json(args.out/"latest.json",result)
        print(json.dumps({"status":"OK","symbols":result["symbol_count"],"candidates":result["candidates"],
            "orders_enabled":False,"generated_at_utc":result["generated_at_utc"]}),flush=True)
    except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
        invalid={"schema":"apex.scanner.shadow.v1","generated_at_utc":utc_now().isoformat(),
                 "status":"BLOCKED","reason":str(exc)[:160],"orders_enabled":False,
                 "live_enabled":False,"instruments":[]}
        try:atomic_json(args.out/"latest.json",invalid)
        except OSError:pass
        print(json.dumps(invalid),flush=True)
        raise SystemExit(1)


if __name__=="__main__":
    main()
