#!/usr/bin/env python3
"""V25/V50/V75 evidence-only forward research, NOT a broker order system."""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import sqlite3
import statistics
import hashlib
import random
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT=Path("/var/lib/abutron-quant-first")
DB=ROOT/"entry-model-causal-v2.sqlite3"
COST=ROOT/"broker-native-cost-evidence-latest.json"
SOURCE=ROOT/"entry-model-causal-v2-latest.json"
OUT=ROOT/"prospective-v25-v50-v75-readiness-v1.json"
SYMS=("Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0")
MODELS=("trend_pullback","failed_breakout","ema_reversion","range_sweep","trend_breakout","streak_fade")
MIN_NONOVERLAPPING=200
MAX_OUTCOME_HORIZON_SEC=12*300
REQUIRED_DATA_FIELDS=("net_0bps","net_1bps","net_5bps","net_10bps")

def iso(ts):
    d=dt.datetime.fromisoformat(ts.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("NAIVE_UTC_TIMESTAMP")
    return d.astimezone(dt.timezone.utc)

def max_dd(values):
    cur=hi=worst=0.0
    for x in values:
        cur+=x
        hi=max(hi,cur)
        worst=max(worst,hi-cur)
    return round(worst,6)

def select_nonoverlap(records):
    """Disallow reuse of an overlapping 12-bar position in statistical sample."""
    retained=[];last_entry=None
    for rec in sorted(records,key=lambda r:r["entry"]):
        if last_entry is not None and rec["entry"] < last_entry+MAX_OUTCOME_HORIZON_SEC:
            continue
        retained.append(rec); last_entry=rec["entry"]
    return retained

def ci_day_block(records,field,seed=4207):
    """Resample entire UTC trading days; avoid IID trade variance assumption."""
    days=defaultdict(list)
    for row in records: days[row["observed_day"]].append(row[field])
    if len(days)<2: return None
    blocks=list(days.values())
    rng=random.Random(seed)
    means=[]
    for _ in range(1000):
        picks=[blocks[rng.randrange(len(blocks))] for __ in range(len(blocks))]
        vals=[v for block in picks for v in block]
        means.append(sum(vals)/len(vals))
    # Conservative familywise 95% lower bound for 18 simultaneous hypotheses.
    means.sort()
    index=max(0,int(1000*(0.05/18))-1)
    return round(means[index],6)

def summarize(records):
    chosen=select_nonoverlap(records)
    valid=[r for r in chosen if all(math.isfinite(r[k]) for k in REQUIRED_DATA_FIELDS)]
    dates=len(set(r["observed_day"] for r in valid))
    metrics={}
    for field in REQUIRED_DATA_FIELDS:
        vals=[r[field] for r in valid]
        metrics[field]={
            "mean_bps":round(statistics.mean(vals),6) if vals else None,
            "median_bps":round(statistics.median(vals),6) if vals else None,
            "win_fraction":round(sum(v>0 for v in vals)/len(vals),6) if vals else None,
            "max_sequential_drawdown_bps":max_dd(vals) if vals else None,
            "day_block_bootstrap_familywise_95_lower_mean_bps":ci_day_block(valid,field)
        }
    eligible=(len(valid)>=MIN_NONOVERLAPPING and
              all(metrics[f]["day_block_bootstrap_familywise_95_lower_mean_bps"] is not None
              and metrics[f]["day_block_bootstrap_familywise_95_lower_mean_bps"]>0
              for f in ("net_5bps","net_10bps")))
    return {
        "all_matured_records":len(records),
        "independent_nonoverlapping_matured_records":len(valid),
        "rejected_for_overlap_or_invalid":len(records)-len(valid),
        "distinct_utc_observation_days":dates,
        "min_nonoverlap_required":MIN_NONOVERLAPPING,
        "min_days_required":None,
        "fixed_14_day_wait_removed":True,
        "hypothetical_5_and_10bps_stress_pass":eligible,
        "scenarios":metrics,
        "broker_real_fill_outcomes":0
    }

def get_data(db=DB):
    with sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=5) as c:
        c.execute("PRAGMA query_only=ON")
        data=c.execute("""SELECT symbol,model,first_observed_utc,planned_entry_m5_start,
                           status,net_0bps,net_1bps,net_5bps,net_10bps FROM observed
                           WHERE symbol IN (?,?,?) ORDER BY planned_entry_m5_start""",SYMS).fetchall()
    groups=defaultdict(list)
    states=defaultdict(lambda:defaultdict(int))
    for sym,model,observed,entry,status,n0,n1,n5,n10 in data:
        if sym not in SYMS or model not in MODELS:continue
        states[(sym,model)][status]+=1
        if status!="PROSPECTIVE_MARKET_OUTCOME_MEASURED":continue
        if any(v is None for v in (n0,n1,n5,n10)) or not entry:continue
        timestamp=iso(observed)
        if entry<=timestamp.timestamp(): raise ValueError("NONCAUSAL_ENTRY_IN_FORWARD_SOURCE")
        groups[(sym,model)].append({
            "entry":int(entry),"observed_day":timestamp.date().isoformat(),
            "net_0bps":float(n0),"net_1bps":float(n1),
            "net_5bps":float(n5),"net_10bps":float(n10)})
    return groups,states

def main():
    now=dt.datetime.now(dt.timezone.utc)
    reference=json.loads(SOURCE.read_text())
    micro=json.loads(COST.read_text())
    if reference.get("schema")!="abutron.quant.causal_forward_market_outcome.v2":
        raise ValueError("UNTRUSTED_FORWARD_SOURCE")
    if micro.get("collection")!="REAL_AUTHENTICATED_DERIV_DEMO_NATIVE_MQL5_TICKS":
        raise ValueError("UNTRUSTED_NATIVE_TICK_SOURCE")
    for sym in SYMS:
        if sym not in micro["spreads"]:raise ValueError("MISSING_NATIVE_SPREAD_"+sym)
    groups,states=get_data()
    pairs={}
    for sym in SYMS:
        for model in MODELS:
            recs=groups.get((sym,model),[])
            stat=summarize(recs)
            stat["statuses"]=dict(states[(sym,model)])
            stat["spread_p95_bps_observed_two_hour_window"]=micro["spreads"][sym]["spread_bps_p95"]
            stat["historical_roundtrip_commission_reference_bps"]=micro["spreads"][sym].get("historical_broker_deal_roundtrip_commission_bps_at_prior_quote")
            stat["risk_adjusted_equity_drawdown_verified"]=False
            pairs[sym+"|"+model]=stat
    passed=sum(v["hypothetical_5_and_10bps_stress_pass"] for v in pairs.values())
    report={
        "schema":"abutron.apex.prospective.v25_v50_v75.v1",
        "checked_at_utc":now.isoformat(),
        "mode":"READONLY_SHADOW_RESEARCH_NO_ORDERS",
        "prioritized_symbols":list(SYMS),
        "families_tested":18,
        "matured_total_raw":sum(v["all_matured_records"] for v in pairs.values()),
        "passed_stress_test_not_execution_approval":passed,
        "order_submission_allowed":False,
        "new_orders_submitted":0,
        "actual_execution_slippage_distribution_verified":False,
        "actual_client_requested_order_price_in_native_broker_logs_verified":False,
        "fresh_tick_capture_is_not_automated_by_this_report":True,
        "historical_holdout_already_inspected":True,
        "evidence_source":"CAUSAL_TIMESTAMPED_FUTURE_M5_PRICE_PATH_NOT_REAL_ORDER_FILLS",
        "cost_basis":"BROKER_NATIVE_TWO_HOUR_SPREAD_P95_PLUS_PRIOR_REAL_DEAL_COMMISSION_AND_EXPLICIT_HYPOTHETICAL_SLIPPAGE",
        "uncertainty":"UTC_DAY_BLOCK_BOOTSTRAP_1000_RESAMPLES_FAMILYWISE_95_LOWER_OVER_18_PREDEFINED_TESTS",
        "equity_drawdown_verified":False,
        "promotion_locked":True,
        "promotion_blockers":[
            "NO_INDEPENDENT_FRESH_PROSPECTIVE_POSITIVE_NET_EDGE",
            "ACTUAL_EXECUTION_SLIPPAGE_NOT_MEASURED",
            "REQUEST_PRICE_ACK_FILL_AND_PROTECTION_AUDIT_NOT_YET_WIRED",
            "MODEL_NOT_CONNECTED_TO_ORDER_ROUTER"
        ],
        "per_model":pairs,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.is_symlink():raise ValueError("OUTPUT_SYMLINK_REJECTED")
    fd,p=tempfile.mkstemp(prefix=".v25v50v75-",dir=OUT.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(report,f,indent=2,allow_nan=False);f.write("\n");f.flush();os.fsync(f.fileno())
        os.chmod(p,0o640)
        os.replace(p,OUT)
    finally:
        if os.path.exists(p):os.unlink(p)
    print("PROSPECTIVE_V25_V50_V75",report["matured_total_raw"],
          "MATURED",passed,"STRESS_PASSES","PROMOTION_LOCKED_NO_ORDERS")
if __name__=="__main__":main()
