#!/usr/bin/env python3
"""FP Markets account-isolated, broker-attested QUANT research, never an order source."""
from __future__ import annotations
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import time

ROOT=Path("/opt/apex-client-mt5")
QMOD=ROOT/"quant-first/abutron_quant_first_v1.py"
FMOD=ROOT/"fpmarkets-scanner/fp_apex_readonly_scanner.py"
FEED=Path("/var/lib/abutron-fpmarkets-feed")
DB=Path("/var/lib/apex-signup/accounts.sqlite3")
OUT=Path("/var/lib/abutron-fp-scanner/quant-per-account")
SCHEMA="abutron.fpmarkets.quant.account_research.v1"

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path))
    if spec is None or spec.loader is None:raise ValueError("MISSING_ORIGINAL_BROKER_RESEARCH_MODULE")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def validate_identity(doc,summary,connection_id,original,now):
    def check(cond,reason):
        if not cond:raise ValueError(reason)
    check(isinstance(connection_id,str) and len(connection_id)==32 and
          all(c in "0123456789abcdef" for c in connection_id),"INVALID_ACCOUNT_ID")
    check(doc.get("schema")=="abutron.fpmarkets.native.partial.readonly.v1"
          and doc.get("status")=="PARTIAL_NOT_CERTIFIED"
          and doc.get("source")=="FP Markets DEMO MT5 native"
          and doc.get("broker_server")=="FPMarketsSC-Demo"
          and doc.get("account_mode")=="DEMO"
          and doc.get("connection_id")==connection_id
          and doc.get("orders_submitted")==0
          and doc.get("execution_enabled") is False,"FP_PARTIAL_NATIVE_IDENTITY_FAILED")
    check(-30 <= now-original.timestamp(doc.get("checked_at_utc"))<=130,
          "FP_PARTIAL_SNAPSHOT_STALE")
    check(doc.get("timeframes")==list(original.FRAMES),"FP_NATIVE_FRAMESET_MISMATCH")
    check(summary.get("schema")=="abutron.fpmarkets.feed.readonly.v1"
          and summary.get("execution_enabled") is False
          and summary.get("orders_submitted")==0
          and -30<=now-original.timestamp(summary.get("checked_at_utc"))<=130,
          "FP_SUMMARY_UNTRUSTED_OR_STALE")
    matches=[c for c in summary.get("connections",[]) if isinstance(c,dict) and
             c.get("connection_id")==connection_id]
    check(len(matches)==1 and matches[0].get("mode")=="DEMO"
          and matches[0].get("status") in ("BROKER_NATIVE_DATA_PARTIAL","BROKER_NATIVE_DATA_COMPLETE")
          and matches[0].get("orders_submitted")==0,
          "FP_ACCOUNT_COLLECTOR_PROOF_INVALID")
    return True

def make_account_report(doc,summary,connection_id,original,quant,now):
    validate_identity(doc,summary,connection_id,original,now)
    expected=original.universe()
    mapping=doc.get("mapping")
    quotes=doc.get("quotes")
    bars=doc.get("bars")
    if not all(isinstance(x,dict) for x in (mapping,quotes,bars)):
        raise ValueError("FP_UNTRUSTED_SYMBOL_MAP")
    if set(mapping)!=set(expected) or set(quotes)!=set(bars):
        raise ValueError("FP_COVERAGE_INCONSISTENT")
    fingerprint=hashlib.sha256(connection_id.encode()).hexdigest()[:24]
    rows=[]
    for symbol in expected:
        m=mapping[symbol]
        if not isinstance(m,dict) or m.get("status") not in ("MAPPED","MISSING","AMBIGUOUS"):
            raise ValueError("FP_UNTRUSTED_MAPPING_STATUS")
        if symbol not in bars:
            if m["status"]=="MAPPED": raise ValueError("FP_MAPPED_SYMBOL_MISSING_BARS")
            rows.append({"symbol":symbol,"available":False,
                "broker_mapping_status":m["status"],"research_bias":"HOLD",
                "reason":"BROKER_SYMBOL_"+m["status"],"smc_ict_required":False,
                "orders_enabled":False,"execution_authorized":False})
            continue
        if m["status"]!="MAPPED" or m.get("actual") not in expected[symbol]:
            raise ValueError("FP_UNVERIFIED_BROKER_SYMBOL")
        if quotes[symbol].get("symbol")!=m["actual"]:
            raise ValueError("FP_QUOTE_MAPPING_CONFLICT")
        frames=bars[symbol]
        if not isinstance(frames,dict) or set(frames)!=set(original.FRAMES):
            raise ValueError("FP_FRAMESET_INVALID")
        for tf in original.FRAMES:
            seq=frames[tf]
            if not isinstance(seq,list) or len(seq)<65:
                raise ValueError("FP_FRAME_HISTORY_INSUFFICIENT")
            if seq[-1].get("time") is None:raise ValueError("FP_BAR_TIME_MISSING")
        row=quant.assess(symbol,frames,"FP Markets",quote=quotes[symbol],now=now)
        row["available"]=True
        row["broker_mapping_status"]="MAPPED"
        rows.append(row)
    if (len(rows)!=13 or sum(r["available"] for r in rows)!=doc.get("symbol_count")
        or set(bars)!={r["symbol"] for r in rows if r["available"]}):
        raise ValueError("FP_PARTIAL_RESEARCH_COUNT_MISMATCH")
    return {
        "schema":SCHEMA, "checked_at_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
        "broker":"FP Markets","environment":"DEMO","account_fingerprint":fingerprint,
        "source":"FP Markets DEMO MT5 authenticated partial candles",
        "status":"PARTIAL_BROKER_DATA_RESEARCH_ONLY",
        "symbols_total":13,"symbols_verified":sum(r["available"] for r in rows),
        "symbols_unavailable":[r["symbol"] for r in rows if not r["available"]],
        "instruments":rows,"quant_research_candidates":sum(r["research_bias"]!="HOLD" for r in rows),
        "true_orderflow_connected":False,"smc_ict_mandatory":False,
        "orders_enabled":False,"execution_authorized":False,
        "quant_strategy_certified":False,
        "risk_settings_modified":False,"existing_orders_modified":False,
    }

def run():
    now=time.time()
    original=module("fp_original_for_account_isolation",FMOD)
    quant=module("abutron_quant_for_account_isolation",QMOD)
    summary=original.read(FEED/"summary.json",300000)
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=6) as c:
        c.execute("PRAGMA query_only=ON")
        connected=c.execute("""SELECT id FROM apex_mt5_connections WHERE
            broker='FP Markets' AND environment='DEMO'
            AND broker_server='FPMarketsSC-Demo' AND status='CONNECTED'
            ORDER BY id""").fetchall()
    if not 1<=len(connected)<=10:raise ValueError("FP_CONNECTED_DEMO_ACCOUNTS_MISSING_OR_EXCESSIVE")
    reports=[]
    for (cid,) in connected:
        source=original.read(FEED/"partial"/(cid+".json"))
        original.account_check(source,db=DB,now=now)
        item=make_account_report(source,summary,cid,original,quant,now)
        reports.append(item)
    index={"schema":"abutron.fpmarkets.quant.multi_account.readonly.v1",
           "checked_at_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
           "status":"FP_MULTI_ACCOUNT_QUANT_PARTIAL_RESEARCH",
           "accounts":[{"account_fingerprint":r["account_fingerprint"],
                        "status":r["status"],"verified_symbols":r["symbols_verified"],
                        "quant_research_candidates":r["quant_research_candidates"]}
                       for r in reports],
           "broker":"FP Markets","connected_demo_accounts":len(reports),
           "orders_enabled":False,"execution_authorized":False,
           "smc_ict_mandatory":False,"true_orderflow_connected":False}
    OUT.mkdir(parents=True,exist_ok=True,mode=0o750)
    import grp
    gid=grp.getgrnam("apexagent").gr_gid
    for item in reports:
        target=OUT/(item["account_fingerprint"]+".json")
        original.atomic(target,item)
        os.chown(target,0,gid)
    index_path=OUT/"latest.json"
    original.atomic(index_path,index)
    os.chown(index_path,0,gid)
    # Preserve the global single-account scanner's fail-closed execution
    # contract. Multi-account partial research MUST NOT masquerade as a
    # complete 13-symbol/one-account order-approved feed.
    legacy={"schema":original.SCHEMA,"checked_at_utc":index["checked_at_utc"],
            "status":"BLOCKED","reason":"FP_MULTI_ACCOUNT_PARTIAL_BROKER_COVERAGE",
            "broker":"FP Markets","symbols":0,"instruments":[],
            "account_scoped_research":str(index_path),
            "connected_demo_accounts":len(reports),
            "orders_enabled":False,"execution_authorized":False,
            "smc_ict_mandatory":False}
    legacy_path=OUT.parent/"latest.json"
    original.atomic(legacy_path,legacy)
    os.chown(legacy_path,0,gid)
    print(json.dumps({"status":index["status"],"accounts":len(reports),
                      "coverage":[r["symbols_verified"] for r in reports],
                      "quant_candidates":sum(r["quant_research_candidates"] for r in reports),
                      "orders_enabled":False},sort_keys=True))
    return index

if __name__=="__main__":
    run()
