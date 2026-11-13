#!/usr/bin/env python3
"""Chronological no-look-ahead Deriv research replay. No broker orders or risk changes."""
from __future__ import annotations
import bisect
import datetime as dt
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import tempfile
import time

DB=Path("/var/lib/apex/precision-history/closed-candles.sqlite3")
OUT=Path("/var/lib/abutron-quant-first/validation-latest.json")
QUANT=Path("/opt/apex-client-mt5/quant-first/abutron_quant_first_v1.py")
ORIGINAL=Path("/opt/apex/runtime/apex_fast_scanner.py")
FRAMES={"M1":60,"M5":300,"M15":900,"H1":3600,"H4":14400,"D1":86400}
HOLD_BARS=3
SCHEMA="abutron.apex.quant_deriv.replay.v1"
SYMBOLS=("Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0")

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path))
    if spec is None or spec.loader is None:raise ValueError("MISSING_BROKER_STRATEGY_MODULE")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def load_market(db,symbol):
    with sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=10) as conn:
        conn.execute("PRAGMA query_only=ON")
        data={}
        for tf in FRAMES:
            raw=conn.execute("""SELECT start_time_utc,open,high,low,close FROM candles
                WHERE symbol=? AND timeframe=? ORDER BY start_time_utc""",(symbol,tf)).fetchall()
            rows=[]
            previous=0
            for t,o,h,l,c in raw:
                if (not isinstance(t,int) or t<=previous or
                    any(not math.isfinite(float(v)) or float(v)<=0 for v in (o,h,l,c)) or
                    not l<=min(o,c)<=max(o,c)<=h):
                    raise ValueError("BROKER_WAREHOUSE_CANDLE_INVALID")
                rows.append({"time":t,"open":o,"high":h,"low":l,"close":c})
                previous=t
            data[tf]=rows
    return data

def history_asof(data,m5_index,frames=FRAMES):
    """Only include bars whose close time is <= the triggering M5 close time."""
    m5=data["M5"]
    anchor=m5[m5_index]["time"]+300
    output={"M5":m5[max(0,m5_index-159):m5_index+1]}
    for tf,period in frames.items():
        if tf=="M5":continue
        rows=data[tf]
        times=[x["time"]+period for x in rows]
        last=bisect.bisect_right(times,anchor)
        output[tf]=rows[max(0,last-159):last]
        if output[tf] and output[tf][-1]["time"]+period>anchor:
            raise ValueError("BACKTEST_LOOKAHEAD_BLOCKED")
    return output,anchor

def select_trades(reports,all_m5,lo,hi):
    trades=[]
    next_index=lo
    for i,side in reports:
        if i<lo or i>=hi or i<next_index or side not in ("BUY","SELL"):
            continue
        if i+HOLD_BARS>=len(all_m5):
            continue
        enter=all_m5[i+1]["open"]
        exit_price=all_m5[i+HOLD_BARS]["close"]
        direction=1 if side=="BUY" else -1
        signed_bps=direction*10000*math.log(exit_price/enter)
        trades.append({"index":i,"direction":side,"gross_directional_move_bps":signed_bps})
        next_index=i+HOLD_BARS
    return trades

def score(trades):
    values=[x["gross_directional_move_bps"] for x in trades]
    return {"non_overlapping_signals":len(values),
        "gross_direction_hit_rate":round(sum(x>0 for x in values)/len(values),4) if values else None,
        "mean_gross_directional_move_bps":round(statistics.mean(values),4) if values else None,
        "median_gross_directional_move_bps":round(statistics.median(values),4) if values else None,
        "net_expectancy_verified":False,
        "cost_adjusted":False}

def replay(data,quant,original,symbol="Volatility 75 Index.0"):
    m5=data["M5"]
    out={"status":"HOLD_INSUFFICIENT_HISTORY","m5_history_bars":len(m5),
         "strategies":{},"data_quality":{}}
    if len(m5)<200 or min((len(data[tf]) for tf in FRAMES),default=0)<80:
        return out
    gaps=sum((b["time"]-a["time"])!=300 for a,b in zip(m5[:-1],m5[1:]))
    out["data_quality"]={
        "m5_gaps":gaps,"m5_start_utc":dt.datetime.fromtimestamp(m5[0]["time"],dt.timezone.utc).isoformat(),
        "m5_end_utc":dt.datetime.fromtimestamp(m5[-1]["time"]+300,dt.timezone.utc).isoformat(),
        "m5_bars":len(m5),
    }
    if gaps:
        out["status"]="HOLD_M5_DATA_GAPS"
        return out
    candidates={"quant":[],"original_apex":[]}
    evaluated=0
    first_evaluated=None
    for i in range(80,len(m5)-HOLD_BARS):
        asof,anchor=history_asof(data,i)
        if min((len(asof[tf]) for tf in FRAMES),default=0)<65:
            continue
        evaluated+=1
        if first_evaluated is None:first_evaluated=i
        q=quant.assess(symbol,asof,"Deriv",now=anchor+10)
        # Symbol only describes a volatility-family member; no downstream orders.
        if q.get("research_bias") in ("BUY","SELL"):
            candidates["quant"].append((i,q["research_bias"]))
        orig=original.evaluate(symbol,asof)
        if orig.get("proposal") in ("BUY","SELL"):
            candidates["original_apex"].append((i,orig["proposal"]))
    if first_evaluated is None:
        out["status"]="HOLD_NO_POINT_IN_TIME_SIX_FRAME_COVERAGE"
        return out
    lo=first_evaluated
    hi=len(m5)-HOLD_BARS
    a=lo+int((hi-lo)*0.60)
    b=lo+int((hi-lo)*0.80)
    segments={"development":(lo,a),"validation":(a,b),"untouched_holdout":(b,hi)}
    for strategy,raw in candidates.items():
        out["strategies"][strategy]={
            "raw_signal_candles":len(raw),
            "segments":{
                name:score(select_trades(raw,m5,start,end))
                for name,(start,end) in segments.items()
            },
        }
    out["status"]="EXPLORATORY_GROSS_ONLY_NOT_TRADE_CERTIFIED"
    out["evaluated_closed_candles"]=evaluated
    return out

def verify_history_current():
    import datetime as d
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=10) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("PRECISION_HISTORY_DB_CORRUPT")
        latest=conn.execute("SELECT max(broker_generated_at_utc) FROM imports").fetchone()[0]
        stamp=d.datetime.fromisoformat(str(latest).replace("Z","+00:00"))
        age=(d.datetime.now(d.timezone.utc)-stamp).total_seconds()
        if not 0<=age<=900:raise ValueError("PRECISION_HISTORY_SOURCE_STALE")
        snapshot=json.loads(Path("/var/lib/apex/operator-live/native-market.json").read_text())
        if snapshot.get("schema")!="apex.mt5.market.v1" or snapshot.get("source")!="Deriv DEMO MT5":
            raise ValueError("CURRENT_BROKER_NATIVE_SOURCE_INVALID")
        overlaps=0;conflicts=0
        for symbol in SYMBOLS:
            for tf in FRAMES:
                for bar in snapshot["data"][symbol][tf]:
                    existing=conn.execute(
                      "SELECT open,high,low,close FROM candles WHERE symbol=? AND timeframe=? AND start_time_utc=?",
                      (symbol,tf,bar["time"])).fetchone()
                    if existing is None:continue
                    overlaps+=1
                    if any(not math.isclose(float(a),float(bar[k]),rel_tol=1e-11,abs_tol=1e-9)
                            for a,k in zip(existing,("open","high","low","close"))):
                        conflicts+=1
        if overlaps<600 or conflicts:
            raise ValueError("CURRENT_NATIVE_PRECISION_HISTORY_CANDLE_CONFLICT")
    return {"latest_import_age_seconds":round(age,1),
            "native_candles_crosschecked":overlaps,
            "mismatched_candles":conflicts}

def run():
    source_integrity=verify_history_current()
    quant=module("quant_first_backtest",QUANT)
    original=module("original_apex_backtest",ORIGINAL)
    results={s:replay(load_market(DB,s),quant,original,s) for s in SYMBOLS}
    payload={
        "schema":SCHEMA,
        "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment":"DERIV_DEMO_PRECISION_HISTORY_NATIVE_VERIFIED",
        "history_source_integrity":source_integrity,
        "methodology":"POINT_IN_TIME_CLOSED_M5_WITH_CLOSED_M15_H1_H4_ONLY",
        "strategy_hypothesis":"FIXED_QUANT_V1_NO_TUNING_ON_HOLDOUT",
        "entry":"NEXT_M5_OPEN","exit":"THIRD_M5_BAR_CLOSE",
        "costs":"UNAVAILABLE_BROKER_NATIVE_HISTORICAL_SPREAD",
        "order_size":"NOT_MODELLED",
        "holdout_edge_verified":False,"net_profitability_verified":False,
        "broker_execution_costs_verified":False,
        "smc_ict_veto_applied":False,
        "orders_enabled":False,"execution_authorized":False,
        "symbols":results,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    fd,tmp=tempfile.mkstemp(dir=str(OUT.parent),prefix=".quant-replay-")
    try:
        with os.fdopen(fd,"w") as file:
            json.dump(payload,file,indent=2,allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print(json.dumps({
       "validation":{s:{"status":r["status"],
            "history":r["m5_history_bars"],
            "quant_raw_signals":r.get("strategies",{}).get("quant",{}).get("raw_signal_candles",0),
            "apex_raw_signals":r.get("strategies",{}).get("original_apex",{}).get("raw_signal_candles",0)}
            for s,r in results.items()},
       "orders_enabled":False,
       "net_profitability_verified":False
    },sort_keys=True))
    return payload

if __name__=="__main__":
    run()
