#!/usr/bin/env python3
"""ABUTRON APEX quant-first adaptive research v1.

Broker-native candles only. No MT5/API imports, order writes, license changes,
risk-policy changes or automatic trade authorization. SMC/ICT not consulted.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import statistics
import tempfile
import time

DERIV = Path("/var/lib/apex/operator-live/native-market.json")
FP_ROOT = Path("/var/lib/abutron-fpmarkets-feed")
OUTPUT = Path("/var/lib/abutron-quant-first")
DERIV_SCOPE = frozenset((
    "Volatility 10 Index.0", "Volatility 25 Index.0",
    "Volatility 50 Index.0", "Volatility 75 Index.0",
    "Volatility 100 Index.0",
))
REENTRY_CHECK = frozenset(("Volatility 10 Index.0", "Volatility 100 Index.0"))
PERMITTED_FP = re.compile(r"^[a-f0-9]{32}\.json$")
SCHEMA = "abutron.apex.quant_first.shadow.v1"

def read_json(path: Path, max_bytes=8_000_000):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or not 8 <= st.st_size <= max_bytes:
        raise ValueError("UNSAFE_OR_EMPTY_SOURCE")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        pre = os.fstat(fd)
        body = os.read(fd, max_bytes + 1)
        post = os.fstat(fd)
    finally:
        os.close(fd)
    if (len(body) > max_bytes or len(body) != pre.st_size or
        (pre.st_ino, pre.st_mtime_ns, pre.st_size) !=
        (post.st_ino, post.st_mtime_ns, post.st_size)):
        raise ValueError("CHANGING_OR_OVERSIZED_SOURCE")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("INVALID_SOURCE_JSON")
    return data

def finite_float(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("INVALID_PRICE_TYPE")
    val = float(x)
    if not math.isfinite(val) or val <= 0:
        raise ValueError("INVALID_PRICE_VALUE")
    return val

def validate_bars(rows, now=None):
    now = time.time() if now is None else float(now)
    if not isinstance(rows, list) or not 65 <= len(rows) <= 1000:
        raise ValueError("INSUFFICIENT_M5_HISTORY")
    validated = []
    previous = None
    for item in rows:
        if not isinstance(item, dict) or type(item.get("time")) is not int:
            raise ValueError("INVALID_CANDLE_TIME")
        stamp = item["time"]
        if (previous is not None and stamp <= previous) or stamp > now + 5:
            raise ValueError("NON_CHRONOLOGICAL_OR_FUTURE_BARS")
        previous = stamp
        o, h, l, c = (finite_float(item[x]) for x in ("open","high","low","close"))
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("INVALID_OHLC")
        validated.append((stamp, o, h, l, c))
    return validated

def ema(values, n):
    a = 2.0/(n+1)
    s = values[0]
    for v in values[1:]:
        s = a*v + (1-a)*s
    return s

def metrics(rows):
    closes = [r[4] for r in rows]
    logret = [math.log(b/a) for a,b in zip(closes[:-1], closes[1:])]
    vol20 = statistics.pstdev(logret[-20:])
    vol60 = statistics.pstdev(logret[-60:])
    atrs = [max(b[2]-b[3], abs(b[2]-a[4]), abs(b[3]-a[4]))
            for a,b in zip(rows[-16:-1], rows[-15:])]
    atr14 = sum(atrs[-14:])/14.0
    drift20 = math.log(closes[-1]/closes[-21])
    total_path = sum(abs(b-a) for a,b in zip(closes[-21:-1],closes[-20:]))
    efficiency = abs(closes[-1]-closes[-21])/total_path if total_path else 0.0
    trend_z = drift20/(max(vol60,1e-12)*math.sqrt(20))
    vol_ratio = vol20/vol60 if vol60 > 1e-12 else None
    last = rows[-1]
    body_pressure = (last[4]-last[1])/(last[2]-last[3]) if last[2]>last[3] else 0.0
    ema20 = ema(closes[-80:],20)
    extension = abs(closes[-1]-ema20)/atr14 if atr14 > 0 else None
    return {
        "trend_z":trend_z, "efficiency":efficiency,
        "realized_vol20":vol20, "realized_vol60":vol60,
        "volatility_ratio":vol_ratio, "atr14":atr14,
        "body_pressure":body_pressure, "ema20_atr_extension":extension,
        "last_closed_m5":last[0],
    }

def deriv_reentry_m5_quality(m5, side, atr14):
    """V10/V100 research gate: closed-candle body, EMA9 distance and close location."""
    if side not in ("BUY", "SELL"):
        return "NO_DIRECTION"
    if len(m5) < 65 or not math.isfinite(atr14) or atr14 <= 0:
        return "INVALID_ENTRY_EVIDENCE"
    t, o, h, low, c = m5[-1]
    if h <= low:
        return "INVALID_ENTRY_EVIDENCE"
    ema9 = ema([r[4] for r in m5[-80:]], 9)
    if abs(c-ema9) > 0.65*atr14:
        return "OVEREXTENDED_EMA9"
    if abs(c-o) < 0.35*atr14:
        return "WEAK_M5_BODY"
    location=(c-low)/(h-low)
    if side=="BUY" and (c <= o or location < 0.55):
        return "BUY_CANDLE_NOT_CONFIRMED"
    if side=="SELL" and (c >= o or location > 0.45):
        return "SELL_CANDLE_NOT_CONFIRMED"
    return "PASS"

def assess(symbol, frames, broker, quote=None, now=None):
    """Candidate is research-only, never a native router input."""
    now = time.time() if now is None else float(now)
    result = {
        "symbol":symbol, "broker":broker, "research_bias":"HOLD",
        "signal_status":"RESEARCH_ONLY_NOT_VALIDATED",
        "execution_authorized":False, "orders_enabled":False,
        "smc_ict_required":False, "smc_ict_veto_consulted":False,
        "institutional_order_flow_verified":False,
    }
    try:
        if not isinstance(frames,dict) or any(tf not in frames for tf in ("M5","M15","H1")):
            raise ValueError("MISSING_REQUIRED_TIMEFRAMES")
        m5 = validate_bars(frames["M5"],now)
        m15 = validate_bars(frames["M15"],now)
        h1 = validate_bars(frames["H1"],now)
        h4 = validate_bars(frames["H4"],now) if broker=="Deriv" and symbol in REENTRY_CHECK else None
        if now-(m5[-1][0]+300) > 600:
            raise ValueError("M5_FEED_STALE")
        m = metrics(m5)
        if m["volatility_ratio"] is None or m["atr14"] <= 0:
            raise ValueError("VOLATILITY_INSUFFICIENT")
        last_close = m5[-1][4]
        quote_status = "UNAVAILABLE"
        cost_atr = None
        if broker == "FP Markets":
            if not isinstance(quote,dict):
                raise ValueError("FP_BROKER_QUOTE_MISSING")
            bid = finite_float(quote.get("bid"))
            ask = finite_float(quote.get("ask"))
            tick_time = quote.get("time")
            if bid > ask or type(tick_time) is not int or not -30 <= now-tick_time <= 300:
                raise ValueError("FP_QUOTE_INVALID_OR_STALE")
            cost_atr = (ask-bid)/m["atr14"]
            quote_status = "BROKER_BID_ASK_SPREAD_ONLY_NO_TRADE_FLOW"
            # A quote spread is an execution cost, NOT true bid/ask volume.
            if cost_atr > 0.15:
                raise ValueError("FP_SPREAD_EXCEEDS_15PCT_M5_ATR")
        else:
            quote_status = "CANDLE_BODY_PRICE_FLOW_PROXY_NOT_ORDER_BOOK"
        result["flow_evidence"] = quote_status
        result["spread_to_atr"] = round(cost_atr,5) if cost_atr is not None else None
        ratio = m["volatility_ratio"]
        regime = "HIGH_VOL" if ratio > 1.4 else "LOW_VOL" if ratio < 0.7 else "NORMAL_VOL"
        result["adaptive_regime"] = regime
        result["features"] = {
            k: (round(v,7) if isinstance(v,float) else v)
            for k,v in m.items()
        }
        # A transparent, untrained research hypothesis; never claim edge/probability.
        htf15 = math.log(m15[-1][4]/m15[-8][4])
        htf1 = math.log(h1[-1][4]/h1[-6][4])
        side = "BUY" if m["trend_z"] > 1.5 else "SELL" if m["trend_z"] < -1.5 else "HOLD"
        entry_quality = deriv_reentry_m5_quality(m5,side,m["atr14"]) if h4 is not None else "PASS"
        h4_drift = math.log(h4[-1][4]/h4[-6][4]) if h4 is not None else None
        h4_ok = h4 is None or ((side=="BUY" and h4_drift>0) or (side=="SELL" and h4_drift<0))
        if h4 is not None:
            result["m5_entry_quality"]=entry_quality
            result["h4_direction_confirmed"]=h4_ok
        if (side != "HOLD" and entry_quality=="PASS" and h4_ok and regime=="NORMAL_VOL" and
            m["efficiency"]>=0.36 and m["ema20_atr_extension"] is not None and
            m["ema20_atr_extension"]<=1.2 and
            ((side=="BUY" and m["body_pressure"]>=0.2 and htf15>0 and htf1>0) or
             (side=="SELL" and m["body_pressure"]<=-0.2 and htf15<0 and htf1<0))):
            result["research_bias"] = side
            result["reason"] = "QUANT_PRICE_FEATURES_ALIGN_UNTESTED_HYPOTHESIS"
        else:
            result["reason"] = ("V10_V100_"+entry_quality if h4 is not None and entry_quality!="PASS"
                else "V10_V100_H4_CONFLICT" if h4 is not None and not h4_ok
                else "NO_QUALIFIED_QUANT_RESEARCH_BIAS")
        result["source_freshness_seconds"] = round(now-(m5[-1][0]+300),2)
    except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError) as exc:
        result["reason"] = str(exc)[:95] if isinstance(exc,ValueError) else "INVALID_BROKER_CANDLE_EVIDENCE"
        result["source_status"] = "BLOCKED"
        result["research_bias"] = "HOLD"
    return result

def build(deriv, fp_summary, fp_partials, now=None):
    """Pure aggregation: no disk access, broker calls or execution side effects."""
    now = time.time() if now is None else float(now)
    output = {
        "schema":SCHEMA,
        "checked_at_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
        "mode":"SHADOW_RESEARCH_ONLY",
        "strategy":"QUANT_FIRST_ADAPTIVE_STATISTICAL_RESEARCH_V1",
        "quantitative_finance_included":True,
        "order_flow_analysis_included":False,
        "flow_proxy_analysis_included":True,
        "verified_order_flow_capture_connected":False,
        "true_order_book_data_available":False,
        "smc_ict_mandatory":False,"smc_ict_veto_active_in_this_module":False,
        "out_of_sample_edge_verified":False,
        "forward_test_verified":False,"execution_authorized":False,
        "orders_enabled":False,"risk_settings_modified":False,
        "position_state_modified":False,
        "brokers":{},
    }
    deriv_rows=[]
    if (isinstance(deriv,dict) and deriv.get("schema")=="apex.mt5.market.v1"
            and deriv.get("source")=="Deriv DEMO MT5"
            and isinstance(deriv.get("data"),dict)
            and set(DERIV_SCOPE).issubset(deriv["data"])):
        deriv_rows=[assess(sym,deriv["data"][sym],"Deriv",now=now)
                    for sym in sorted(DERIV_SCOPE)]
        deriv_status="READONLY_RESEARCH"
    else:
        deriv_status="DERIV_SOURCE_MISSING_OR_UNTRUSTED"
    output["brokers"]["Deriv"]={
        "status":deriv_status,"scope":sorted(DERIV_SCOPE),
        "instruments":deriv_rows,"orders_enabled":False,
        "true_order_flow_status":"UNAVAILABLE_FOR_SYNTHETIC_INDEX",
    }
    fp_rows=[]
    if not isinstance(fp_summary,dict) or fp_summary.get("schema")!="abutron.fpmarkets.feed.readonly.v1":
        fp_status="FP_SOURCE_UNAVAILABLE"
    else:
        fp_complete=fp_summary.get("native_feeds_complete")==1
        fp_linked=fp_summary.get("fp_accounts_linked")
        fp_status=("FP_RESEARCH_COMPLETE" if fp_complete and fp_linked==1
                   else "FP_PARTIAL_OR_MULTI_ACCOUNT_UNVERIFIED")
        for part in fp_partials[:10]:
            if not isinstance(part,dict) or part.get("schema")!="abutron.fpmarkets.native.partial.readonly.v1" or part.get("account_mode")!="DEMO":
                continue
            cid=part.get("connection_id")
            if not isinstance(cid,str) or not re.fullmatch(r"[a-f0-9]{32}",cid):
                continue
            fingerprint=hashlib.sha256(cid.encode()).hexdigest()[:16]
            bars=part.get("bars",{})
            quotes=part.get("quotes",{})
            if not isinstance(bars,dict) or not isinstance(quotes,dict):
                continue
            for sym in sorted(bars):
                if sym not in quotes:continue
                row=assess(sym,bars[sym],"FP Markets",quote=quotes[sym],now=now)
                row["account_fingerprint"]=fingerprint
                row["fp_feed_certified"]=False
                fp_rows.append(row)
    output["brokers"]["FP Markets"]={
        "status":fp_status,"per_connection_isolation":True,
        "instruments":fp_rows,"orders_enabled":False,
        "true_order_flow_status":"NO_VERIFIED_DEPTH_OR_TRADE_PRINTS",
    }
    output["research_candidates"]=sum(
        r["research_bias"] in ("BUY","SELL") for b in output["brokers"].values()
        for r in b["instruments"])
    return output

def atomic_write(payload, output=OUTPUT):
    output.mkdir(mode=0o750, parents=True,exist_ok=True)
    if output.is_symlink():
        raise ValueError("UNSAFE_OUTPUT_DIRECTORY")
    fd,name=tempfile.mkstemp(prefix=".quant-first-",dir=str(output))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(payload,f,indent=2,allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name,0o640)
        os.replace(name,output/"latest.json")
    finally:
        if os.path.exists(name):
            os.unlink(name)

def main():
    deriv = read_json(DERIV) if DERIV.exists() else None
    summary = read_json(FP_ROOT/"summary.json") if (FP_ROOT/"summary.json").exists() else None
    parts=[]
    partdir=FP_ROOT/"partial"
    if partdir.is_dir() and not partdir.is_symlink():
        for path in sorted(partdir.iterdir()):
            if PERMITTED_FP.fullmatch(path.name):
                try:
                    parts.append(read_json(path))
                except (ValueError,OSError,json.JSONDecodeError):
                    pass
    payload=build(deriv,summary,parts)
    atomic_write(payload)
    print(json.dumps({
        "schema":payload["schema"],
        "deriv_status":payload["brokers"]["Deriv"]["status"],
        "fp_status":payload["brokers"]["FP Markets"]["status"],
        "deriv_symbols":len(payload["brokers"]["Deriv"]["instruments"]),
        "fp_rows":len(payload["brokers"]["FP Markets"]["instruments"]),
        "research_candidates":payload["research_candidates"],
        "execution_authorized":False,"orders_enabled":False,
    },sort_keys=True))

if __name__=="__main__":
    main()
