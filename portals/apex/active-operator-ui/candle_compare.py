"""APEX eight-timeframe candle-bias comparison for Deriv MT5 DEMO.

Differentiate one CLOSED candle open/close bias from EMA/RSI trend.
Uses only the connected APEX Deriv USD DEMO MT5 market data.
No data, credentials or service calls to other trading platforms.
"""
from datetime import datetime,timezone
from pathlib import Path
import json
from apex_fast_scanner import EXPECTED,FRAMES as SCANNER_FRAMES,frame_state,evaluate as evaluate_strategy
DERIV_VISIBLE_SYMBOLS=frozenset(("Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0"))

MAIN=Path("/var/lib/apex/operator-live/native-market.json")
# All comparison sources are native broker verified and current.
SCANNER=Path("/var/lib/apex/operator-live/native-scanner.json")
FRAMES=(("M1",60),("M3",180),("M5",300),("M15",900),("M30",1800),
        ("H1",3600),("H4",14400),("D1",86400))

def read(path):
    try:
        if path.stat().st_size>8_000_000:return None
        obj=json.loads(path.read_text(encoding="utf8"))
        return obj if isinstance(obj,dict) else None
    except (OSError,ValueError,UnicodeError):
        return None

def age(raw,now):
    try:
        t=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        return (now-t).total_seconds() if t.tzinfo is not None else None
    except (TypeError,ValueError):return None

def completed_native_m1(m1,seconds,now):
    """Assemble only complete UTC-aligned M3/M30 periods from native broker M1."""
    import math
    if not isinstance(m1,list) or len(m1)<seconds//60:
        return []
    groups={}
    last_t=-1
    for b in m1:
        if not isinstance(b,dict):
            return []
        try:
            t=int(b["time"])
            o,h,l,c=(float(b[k]) for k in ("open","high","low","close"))
        except (KeyError,TypeError,ValueError,OverflowError):
            return []
        if (t%60 or t<=last_t or (last_t>=0 and t-last_t!=60)
            or not all(math.isfinite(v) and v>0 for v in (o,h,l,c))
            or h<max(o,c) or l>min(o,c) or l>h):
            return []
        last_t=t
        groups.setdefault(t//seconds*seconds,[]).append((t,o,h,l,c))
    completed=[]
    for start,bars in sorted(groups.items()):
        if start+seconds>now.timestamp()-1:
            continue
        if len(bars)!=seconds//60 or [b[0] for b in bars]!=list(range(start,start+seconds,60)):
            continue
        completed.append({"time":start,"open":bars[0][1],
                          "high":max(b[2] for b in bars),
                          "low":min(b[3] for b in bars),
                          "close":bars[-1][4]})
    return completed


def native_supplements(main,now):
    """Fail closed if any symbol lacks complete native M1-derived M3/M30 bars."""
    if (not isinstance(main,dict) or main.get("schema")!="apex.mt5.market.v1"
        or main.get("source")!="Deriv DEMO MT5" or main.get("execution_enabled") is not False):
        return None
    data=main.get("data")
    if not isinstance(data,dict) or set(data)!=set(EXPECTED):
        return None
    derived={}
    for sym,frames in data.items():
        if not isinstance(frames,dict):
            return None
        m1=frames.get("M1",[])
        m3=completed_native_m1(m1,180,now)
        m30=completed_native_m1(m1,1800,now)
        if not m3 or not m30:
            return None
        derived[sym]={"M3":m3,"M30":m30}
    return {"schema":"apex.mt5.extra_candles.v1",
            "source":"Deriv DEMO MT5",
            "generated_at_utc":main.get("generated_at_utc"),
            "execution_enabled":False,"orders_placed":0,
            "derivation":"COMPLETE_CONSECUTIVE_NATIVE_M1",
            "data":derived}


def compare(symbol,main=None,extra=None,scanner=None,now=None):
    now=now or datetime.now(timezone.utc)
    if symbol not in DERIV_VISIBLE_SYMBOLS:raise ValueError("Symbol not approved for new ABUTRON Deriv DEMO entries")
    if main is None:main=read(MAIN)
    if extra is None:extra=native_supplements(main,now)
    if scanner is None:scanner=read(SCANNER)
    if (not isinstance(main,dict) or main.get("schema")!="apex.mt5.market.v1"
        or main.get("source")!="Deriv DEMO MT5"
        or main.get("execution_enabled") is not False):
        raise ValueError("Primary broker feed unverified")
    main_age=age(main.get("generated_at_utc"),now)
    if main_age is None or not -30<=main_age<=660:
        raise ValueError("Primary broker feed stale")
    if (not isinstance(extra,dict)
        or extra.get("schema")!="apex.mt5.extra_candles.v1"
        or extra.get("source")!="Deriv DEMO MT5"
        or extra.get("orders_placed")!=0
        or extra.get("execution_enabled") is not False):
        raise ValueError("M3/M30 broker feed unverified")
    extra_age=age(extra.get("generated_at_utc"),now)
    if extra_age is None or not -30<=extra_age<=660:
        raise ValueError("M3/M30 broker feed stale")
    primary=main.get("data",{}).get(symbol,{})
    supplements=extra.get("data",{}).get(symbol,{})
    # Recalculate strategy on the same six completed candles used below.
    # Never imply that the single candle direction alone authorizes an order.
    if set(primary)!=set(SCANNER_FRAMES):
        raise ValueError("Primary six timeframe broker candles missing")
    recomputed=evaluate_strategy(symbol,primary)
    scan_status="UNAVAILABLE"
    observed=None
    scan_age=None
    if (isinstance(scanner,dict) and scanner.get("schema")=="apex.scanner.shadow.v1"
        and scanner.get("source")=="Deriv DEMO MT5"
        and scanner.get("orders_enabled") is False):
        scan_age=age(scanner.get("generated_at_utc"),now)
        if scan_age is not None and -30<=scan_age<=240:
            observed=next((x for x in scanner.get("instruments",[])
                           if x.get("symbol")==symbol),None)
            if observed is not None:
                if observed.get("last_closed_m5")!=recomputed["last_closed_m5"]:
                    scan_status="DIFFERENT_CANDLE"
                else:
                    actual=observed.get("indicators",{})
                    frames_match=all(
                        actual.get(tf,{}).get("bar_time")==recomputed["indicators"][tf]["bar_time"]
                        and actual.get(tf,{}).get("trend")==recomputed["indicators"][tf]["trend"]
                        for tf in SCANNER_FRAMES)
                    same=(frames_match
                          and observed.get("m5_signal")==recomputed["m5_signal"]
                          and observed.get("proposal")==recomputed["proposal"])
                    scan_status=("MATCHED" if same else "DIFFERENT_SNAPSHOT" if scanner.get("broker_generated_at_utc")!=main.get("generated_at_utc") else "CALCULATION_MISMATCH")
        else:
            scan_status="STALE"
    rows=[]
    for frame,seconds in FRAMES:
        arr=(supplements if frame in ("M3","M30") else primary).get(frame,[])
        if not isinstance(arr,list) or not arr:
            raise ValueError("Missing completed "+frame+" candles")
        b=arr[-1]
        start=int(b["time"]); end=start+seconds
        if end>now.timestamp()-1:
            raise ValueError("Incomplete "+frame+" candle")
        opening=float(b["open"]);closing=float(b["close"])
        bias="BUY" if closing>opening else "SELL" if closing<opening else "NEUTRAL"
        # Read EMA9/21 and RSI14 from exactly the same completed candles as
        # the displayed close-vs-open bias. Do not mix scanner/bar vintages.
        trend=frame_state(arr)["trend"] if frame not in ("M3","M30") and len(arr)>=60 else "UNAVAILABLE"
        rows.append({
            "timeframe":frame,"candle_open_utc":datetime.fromtimestamp(start,timezone.utc).isoformat(),
            "candle_closed_utc":datetime.fromtimestamp(end,timezone.utc).isoformat(),
            "open":opening,"close":closing,
            "candle_bias":bias,"basis":"LAST_CLOSED_CANDLE_CLOSE_MINUS_OPEN",
            "ema_rsi_trend":trend,
            "origin":("VERIFIED_NATIVE_M1_AGGREGATION" if frame in ("M3","M30") else "VERIFIED_NATIVE_BROKER"),
            "strategy_proposal_is_not_candle_bias":True,
            "closed":True,
            "closed_age_seconds":round((now.timestamp()-end),1),
        })
    return {
        "schema":"apex.candle_comparison.v1","generated_at_utc":now.isoformat(),
        "symbol":symbol,"source":"Deriv DEMO MT5",
        "main_snapshot_age_seconds":round(main_age,1),
        "extra_snapshot_age_seconds":round(extra_age,1),
        "supplemental_frame_origin":"COMPLETE_NATIVE_M1_AGGREGATION",
        "timeframe_count":len(rows),"rows":rows,
        "scanner_comparison":{
            "status":scan_status,
            "scanner_generated_at_utc":scanner.get("generated_at_utc") if isinstance(scanner,dict) else None,
            "scanner_m5_closed_utc":(
                datetime.fromtimestamp(observed["last_closed_m5"]+300,timezone.utc).isoformat()
                if observed and type(observed.get("last_closed_m5")) is int else None),
            "m5_candle_closed_utc":datetime.fromtimestamp(
                recomputed["last_closed_m5"]+300,timezone.utc).isoformat(),
            "m5_direction":recomputed["m5_signal"],
            "strategy_gate":recomputed["proposal"],
            "strategy_reason":recomputed["reason"],
            "higher_tf_signal":recomputed["higher_tf_signal"],
            "strategy_recalculated_on_matching_broker_candles":True
        },
        "orders_enabled":False,"live_enabled":False,
        "disclaimer":"Candle bias is close-vs-open of ONE completed broker candle; EMA/RSI is a multi-candle calculation. Neither is a certified trade signal.",
    }
