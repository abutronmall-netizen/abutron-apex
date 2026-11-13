#!/usr/bin/env python3
"""ABUTRON APEX quant-first read-only operator evidence summarizer.

Never returns an executable signal, account identifier, or order request.
"""
from datetime import datetime,timezone
from pathlib import Path
import json
import stat
import time

QUANT=Path("/var/lib/abutron-quant-first/latest.json")
FP=Path("/var/lib/abutron-fp-scanner/quant-per-account/latest.json")
REPLAY=Path("/var/lib/abutron-quant-first/validation-latest.json")
SCHEMA="abutron.apex.quant_first.dashboard.readonly.v1"

def safe_read(path):
    try:
        s=path.lstat()
        if (not stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode)
            or not 10<=s.st_size<=2_000_000):
            return None
        with path.open(encoding="utf-8") as f:
            data=json.load(f)
        return data if isinstance(data,dict) else None
    except (OSError,ValueError,TypeError,UnicodeError,json.JSONDecodeError):
        return None

def utc_timestamp(value):
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return dt.timestamp() if dt.tzinfo is not None else None
    except (ValueError,TypeError,OverflowError,AttributeError):
        return None

def build(quant=None,fp=None,replay=None,now=None):
    now=time.time() if now is None else float(now)
    report={
        "schema":SCHEMA,
        "checked_at_utc":datetime.fromtimestamp(now,timezone.utc).isoformat(),
        "mode":"SHADOW_RESEARCH_ONLY",
        "execution_authorized":False,
        "orders_enabled":False,
        "smc_ict_mandatory":False,
        "verified_institutional_order_flow":False,
        "price_quote_flow_proxy_only":True,
        "deriv":{"status":"UNVERIFIED","symbols":0,"research_candidates":0},
        "fp_markets":{"status":"UNVERIFIED","accounts":0,"coverage":[]},
        "validation":{"status":"UNVERIFIED","net_profitability_verified":False,
                      "out_of_sample_edge_verified":False,"symbols":[]},
    }
    if (isinstance(quant,dict)
        and quant.get("schema")=="abutron.apex.quant_first.shadow.v1"
        and quant.get("orders_enabled") is False
        and quant.get("execution_authorized") is False
        and quant.get("smc_ict_mandatory") is False):
        stamp=utc_timestamp(quant.get("checked_at_utc"))
        if stamp is not None and -30<=now-stamp<=300:
            row=quant.get("brokers",{}).get("Deriv",{})
            if (isinstance(row,dict) and row.get("status")=="READONLY_RESEARCH"
                and isinstance(row.get("instruments"),list)
                and all(isinstance(x,dict) and x.get("execution_authorized") is False
                        for x in row["instruments"])):
                report["deriv"]={"status":"RESEARCH_ACTIVE","symbols":len(row["instruments"]),
                   "research_candidates":sum(x.get("research_bias") in ("BUY","SELL") for x in row["instruments"]),
                   "source_age_seconds":round(now-stamp)}
    if (isinstance(fp,dict)
        and fp.get("schema")=="abutron.fpmarkets.quant.multi_account.readonly.v1"
        and fp.get("orders_enabled") is False and fp.get("execution_authorized") is False):
        stamp=utc_timestamp(fp.get("checked_at_utc"))
        rows=fp.get("accounts")
        if stamp is not None and -30<=now-stamp<=300 and isinstance(rows,list):
            if all(isinstance(x,dict) and x.get("status")=="PARTIAL_BROKER_DATA_RESEARCH_ONLY"
                and isinstance(x.get("verified_symbols"),int) and 0<=x["verified_symbols"]<=13
                for x in rows):
                report["fp_markets"]={
                    "status":"PARTIAL_ACCOUNT_SCOPED_RESEARCH",
                    "accounts":len(rows),
                    "coverage":[{"verified":x["verified_symbols"],"required":13} for x in rows],
                    "source_age_seconds":round(now-stamp),
                }
    if (isinstance(replay,dict)
        and replay.get("schema")=="abutron.apex.quant_deriv.replay.v1"
        and replay.get("orders_enabled") is False
        and replay.get("net_profitability_verified") is False
        and replay.get("holdout_edge_verified") is False
        and replay.get("history_source_integrity",{}).get("mismatched_candles")==0):
        stamp=utc_timestamp(replay.get("checked_at_utc"))
        if stamp is not None and -30<=now-stamp<=7200:
            symbols=replay.get("symbols",{})
            if isinstance(symbols,dict):
                rows=[]
                for name in ("Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0"):
                    x=symbols.get(name,{})
                    if isinstance(x,dict):
                        candidate=x.get("strategies",{}).get("quant",{})
                        rows.append({"symbol":name,"m5_bars":x.get("m5_history_bars",0),
                          "quant_raw_research_signals":candidate.get("raw_signal_candles",0),
                          "replay_status":x.get("status","UNVERIFIED")})
                report["validation"]={
                   "status":"GROSS_ONLY_NOT_TRADE_CERTIFIED",
                   "net_profitability_verified":False,
                   "out_of_sample_edge_verified":False,
                   "symbols":rows,
                   "source_crosschecked_candles":replay["history_source_integrity"].get("native_candles_crosschecked",0),
                   "source_age_seconds":round(now-stamp),
                }
    return report

def current():
    return build(safe_read(QUANT),safe_read(FP),safe_read(REPLAY))
