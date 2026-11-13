#!/usr/bin/env python3
"""Independent original TradingAgents/Qwen review of PRODUCTION APEX Strategy Scanner.

INPUT: verified native MT5 market and deterministic scanner snapshots.
OUTPUT: private /var/lib/abutron-scanner-llm only. No signal/order/executor writes.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

from apex_fast_scanner import EXPECTED, validate_snapshot
import apex_broker_agent as original
sys.path.insert(0,"/opt/apex-client-mt5")
import abutron_selective_tradingagents_v1 as selective
import apex_fast_scanner as fast
from apex_deriv_trade_symbol_scope import TRADE_SYMBOLS

MARKET=Path("/var/lib/apex/operator-live/native-market.json")
SCANNER=Path("/var/lib/apex/operator-live/native-scanner.json")
OUT=Path("/var/lib/abutron-scanner-llm")
MODEL=original.MODEL
FULL_GRAPH=False
# Ensure original upstream TradingAgents reports stay in isolated sidecar storage.
original.OUT=OUT

def utcnow():
    return datetime.now(timezone.utc)

def age_seconds(stamp):
    parsed=datetime.fromisoformat(str(stamp).replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_DATA_TIME")
    return (utcnow()-parsed.astimezone(timezone.utc)).total_seconds()

def safe_read(path):
    if path.stat().st_size > 7_000_000:
        raise ValueError("INPUT_TOO_LARGE")
    return json.loads(path.read_text(encoding="utf-8"))

def atomic(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".abutron-llm-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            json.dump(payload,handle,indent=2,allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name,0o640)
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def get_inputs():
    market=safe_read(MARKET)
    scan=safe_read(SCANNER)
    validate_snapshot(market,utcnow())
    original.read_snapshot(MARKET)
    if age_seconds(market["generated_at_utc"]) > 180:
        raise ValueError("NATIVE_MARKET_STALE")
    if scan.get("schema")!="apex.scanner.shadow.v1" or scan.get("source")!="Deriv DEMO MT5":
        raise ValueError("SCANNER_PROVENANCE_FAILED")
    if scan.get("orders_enabled") is not False or scan.get("symbol_count")!=13:
        raise ValueError("SCANNER_PROVENANCE_FAILED")
    if age_seconds(scan.get("generated_at_utc")) > 180:
        raise ValueError("SCANNER_STALE")
    if len(scan.get("instruments",[])) != len(EXPECTED):
        raise ValueError("SCANNER_COUNT_MISMATCH")
    for x in scan["instruments"]:
        symbol=x.get("symbol")
        if symbol not in EXPECTED or x.get("proposal") not in ("BUY","SELL","HOLD"):
            raise ValueError("SCANNER_SYMBOL_OR_PROPOSAL_INVALID")
        m5=market["data"][symbol]["M5"][-1]["time"]
        if x.get("last_closed_m5") != m5:
            raise ValueError("SCANNER_MARKET_M5_MISMATCH")
    return market,scan

def candidate_evidence(market,candidate):
    symbol=candidate['symbol']
    indicators={tf:fast.frame_state(market['data'][symbol][tf])
        for tf in selective.FRAMES}
    return indicators

def fast_broker_only_review(market,candidate):
    """Selective official TradingAgents/Qwen analysis; only source broker candles."""
    symbol=candidate['symbol']
    indicators=candidate_evidence(market,candidate)
    outcome=selective.review('Deriv DEMO MT5',symbol,
        candidate['last_closed_m5'],candidate['proposal'],indicators)
    direction=outcome['direction']
    rating={'BUY':'Buy','SELL':'Sell'}.get(direction,'Hold')
    return rating,outcome['analysis'],outcome


def one_pass():
    market,scan=get_inputs()
    existing={}
    try:
        old=safe_read(OUT/"latest.json")
        existing={x["symbol"]:x for x in old.get("reviews",[]) if x.get("symbol") in EXPECTED}
    except (OSError,ValueError,TypeError,KeyError):
        pass
    eligible=[x for x in scan["instruments"] if x["symbol"] in TRADE_SYMBOLS and x["proposal"] in ("BUY","SELL") and
       type(x.get("last_closed_m5")) is int and
       0<=utcnow().timestamp()-(x["last_closed_m5"]+300)<=225]
    # No synthetic trade signal: only inspect scanner's authentic candidate set.
    if not eligible:
        outcome={"schema":"abutron.scanner.llm.v1","checked_at_utc":utcnow().isoformat(),
                 "status":"NO_SCAN_CANDIDATES","model":MODEL,"candidate_count":0,
                 "reviews":list(existing.values()),"order_execution_modified":False}
        atomic(OUT/"latest.json",outcome)
        return outcome
    # An unchanged M5 candle and unchanged scanner direction already have an
    # evidence-backed model decision. Avoid another identical inference.
    # Scanner BUY/SELL/HOLD and live order execution are never modified here.
    def valid_cached(x):
        previous=existing.get(x["symbol"],{})
        try:
            evidence,digest=selective.validate_evidence('Deriv DEMO MT5',
                x['symbol'],x['last_closed_m5'],x['proposal'],candidate_evidence(market,x))
        except (ValueError,KeyError,TypeError):
            return False
        return (previous.get('m5_bar_time')==x['last_closed_m5'] and
                previous.get('scanner_proposal')==x['proposal'] and
                previous.get('evidence_sha256')==digest and
                previous.get('framework')=='TradingAgentsGraph selective broker-only analyst' and
                previous.get('evidence_status') in ('MODEL_REVIEW_COMPLETED','MODEL_RESPONSE_INVALID'))
    if all(valid_cached(x) for x in eligible):
        outcome={"schema":"abutron.scanner.llm.v1",
                 "checked_at_utc":utcnow().isoformat(),
                 "status":"MODEL_REVIEW_COMPLETED",
                 "model":MODEL,"candidate_count":len(eligible),
                 "last_symbol":next((s for s in EXPECTED if s in existing),None),
                 "cache_hit":True,
                 "reviews":[existing[s] for s in EXPECTED if s in existing],
                 "order_execution_modified":False}
        atomic(OUT/"latest.json",outcome)
        return outcome
    # Prioritize unreviewed M5 candles, then oldest review, one model run per cycle.
    def ordering(x):
        old=existing.get(x["symbol"],{})
        is_current=(old.get("m5_bar_time")==x["last_closed_m5"] and
                    old.get("scanner_proposal")==x["proposal"])
        return (1 if is_current else 0,old.get("reviewed_at_utc",""),x["symbol"])
    candidate=min(eligible,key=ordering)
    symbol=candidate["symbol"]
    if FULL_GRAPH:
        rating,narrative=original.run_original_agent_graph(market,{},symbol)
        outcome=None
    else:
        rating,narrative,outcome=fast_broker_only_review(market,candidate)
    direction={"Buy":"BUY","Sell":"SELL"}.get(rating,"HOLD")
    record={"symbol":symbol,"reviewed_at_utc":utcnow().isoformat(),
            "native_market_at_utc":market["generated_at_utc"],
            "scanner_at_utc":scan["generated_at_utc"],
            "m5_bar_time":candidate["last_closed_m5"],
            "scanner_proposal":candidate["proposal"],
            "model":MODEL,"framework":("FULL_GRAPH_RESEARCH_ONLY" if FULL_GRAPH else "TradingAgentsGraph selective broker-only analyst"),
            "evidence_sha256":outcome["evidence_sha256"] if outcome else None,
            "latency_seconds":outcome["latency_seconds"] if outcome else None,
            "rating":rating,"llm_direction":direction,
            "agreement":direction==candidate["proposal"],
            "evidence_status":("MODEL_REVIEW_COMPLETED" if outcome and
                outcome["raw_model_direction"] in ("BUY","SELL","HOLD") and
                outcome["latency_seconds"]<=90 and
                outcome["analysis"].strip() in ("BUY","SELL","HOLD")
                else "MODEL_RESPONSE_INVALID"),
            "analysis":str(narrative)[:3500],
            "execution_authorized_by_llm":False}
    existing[symbol]=record
    outcome={"schema":"abutron.scanner.llm.v1","checked_at_utc":utcnow().isoformat(),
             "status":"MODEL_REVIEW_COMPLETED","model":MODEL,
             "candidate_count":len(eligible),"last_symbol":symbol,
             "reviews":[existing[x] for x in EXPECTED if x in existing],
             "order_execution_modified":False}
    atomic(OUT/"latest.json",outcome)
    return outcome

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--full-graph",action="store_true",help="slow original TradingAgentsGraph; not for scheduled production")
    args=p.parse_args()
    global FULL_GRAPH
    FULL_GRAPH=args.full_graph
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"review.lock").open("a+") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("ALREADY_RUNNING");return 0
        try:
            market,scanner=get_inputs()
            if args.preflight:
                print(json.dumps({"status":"PREFLIGHT_OK","source":market["source"],
                    "symbols":len(scanner["instruments"]),"candidates":scanner["candidates"],
                    "model":MODEL,"order_execution_modified":False}))
                return 0
            result=one_pass()
            print(json.dumps({k:result[k] for k in ("status","model","candidate_count","order_execution_modified")}))
            return 0
        except Exception as exc:
            error={"status":"ERROR","checked_at_utc":utcnow().isoformat(),
                   "error_type":type(exc).__name__,"message":str(exc)[:250],
                   "order_execution_modified":False}
            atomic(OUT/"last_error.json",error)
            print(json.dumps(error),file=sys.stderr)
            return 1

if __name__=="__main__":
    raise SystemExit(main())
