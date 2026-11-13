#!/usr/bin/python3
"""Deriv/FP customer-wide broker inventory; read-only and fail-closed.

No OrderCalcProfit, broker-deal reconciliation or durable daily/peak
cashflow baselines are available here. This cannot certify executable risk.
"""
from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal, InvalidOperation
import sqlite3
import time
from datetime import datetime, timezone

CID="d6fc2524ec373b8d1bc278a8be3ec635"
DB="/var/lib/apex-signup/accounts.sqlite3"
PRIVATE=Path("/var/lib/private")
DEMO_ID="32456207"
RISK_CAPS={"per_trade":"0.001","aggregate":"0.02","daily_loss":"0.03","peak_drawdown":"0.20"}

def decimal(s):
    try:
        v=Decimal(str(s))
        if not v.is_finite():raise ValueError
        return v
    except (TypeError,InvalidOperation,ValueError):
        raise ValueError("INVALID_NATIVE_DECIMAL") from None

def quote_owner():
    with sqlite3.connect("file:"+DB+"?mode=ro",uri=True,timeout=8) as conn:
        conn.execute("PRAGMA query_only=ON")
        owner=conn.execute("SELECT account_id FROM apex_mt5_connections WHERE id=?",(CID,)).fetchone()
        if not owner:raise ValueError("DERIV_6207_NOT_LINKED")
        rows=conn.execute("""SELECT id,broker,environment,status,account_reference,
            broker_server FROM apex_mt5_connections WHERE account_id=?
            ORDER BY broker,id""",(owner[0],)).fetchall()
    return rows

def worker(cid,now,ttl=30):
    p=PRIVATE/("abutron-client-mt5-"+cid)
    f=p/"worker-health.json"
    obj=json.loads(f.read_text())
    if obj.get("id")!=cid or obj.get("status")!="CONNECTED" or not obj.get("heartbeat_fresh"):
        raise ValueError("WORKER_NOT_CONNECTED")
    if not -2<=now-f.stat().st_mtime<=ttl:
        raise ValueError("WORKER_HEALTH_STALE")
    nonce=obj.get("nonce")
    if not isinstance(nonce,str) or len(nonce)!=32 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("WORKER_NONCE_INVALID")
    return p,nonce,obj

def deriv_inventory(cid,now):
    root,nonce,health=worker(cid,now)
    if health.get("broker")!="Deriv" or health.get("mode")!="DEMO" or health.get("server")!="Deriv-Demo":
        raise ValueError("DERIV_SESSION_IDENTITY_INVALID")
    f=root/"terminal/MQL5/Files"/("ABUTRON_NATIVE_ACCOUNT_V2_"+nonce+".txt")
    x=f.read_text(encoding="utf-8-sig").splitlines()
    if (len(x)!=7 or x[:3]!=["ABUTRON_NATIVE_ACCOUNT_V2",nonce,DEMO_ID] or
        x[5]!="USD" or not -2<=now-f.stat().st_mtime<=20):
        raise ValueError("DERIV_ACCOUNT_EXPORT_INVALID_OR_STALE")
    side=PRIVATE/"abutron-native-readonly-mt5-6207"/"worker-health.json"
    broker=json.loads(side.read_text())
    if (broker.get("broker_session_identity_verified") is not True or
        broker.get("execution_authority") is not False or
        broker.get("orders_submitted")!=0 or
        not -2<=now-float(broker.get("broker_checked_utc",0))<=35):
        raise ValueError("DERIV_INDEPENDENT_BROKER_PROOF_UNAVAILABLE")
    return {"broker":"Deriv","account_suffix":"6207","environment":"DEMO",
       "equity_usd_observed":str(decimal(x[4])),
       "balance_usd_observed":str(decimal(x[3])),
       "native_account_position_count":int(x[6]),
       "independent_session_readonly":True,
       "complete_all_orders_and_stops_reconciled":False}

def fp_inventory(cid,login,server,now):
    root,nonce,health=worker(cid,now)
    if (health.get("broker")!="FP Markets" or health.get("mode")!="DEMO"
        or health.get("server")!=server or server!="FPMarketsSC-Demo"):
        raise ValueError("FP_BROKER_ACCOUNT_IDENTITY_INVALID")
    f=root/"terminal/MQL5/Files"/("ABUTRON_FP_ACCOUNT_HISTORY_V1_"+nonce+".txt")
    lines=f.read_text(encoding="utf-8-sig").splitlines()
    if (len(lines)<21 or lines[:6]!=["ABUTRON_FP_ACCOUNT_HISTORY_V1",nonce,
        health.get("proof_owner"),server,login,"DEMO"] or
        lines[19]!="BROKER_NATIVE_NO_ORDER_FUNCTIONS" or
        len(lines)>15000 or not -2<=now-f.stat().st_mtime<=140):
        raise ValueError("FP_HISTORY_BINDING_INVALID")
    positions=int(lines[14]);pending=int(lines[15]);deals=int(lines[16])
    records=[s.split("\t") for s in lines[20:-1]]
    if positions+pending+deals!=len(records) or records and len(records)>15000:
        raise ValueError("FP_ACCOUNT_RECORDS_INCOMPLETE")
    open_positions=[r for r in records if r[0]=="P"]
    if len(open_positions)!=positions:raise ValueError("FP_OPEN_POSITIONS_MISMATCH")
    summary=[]
    for r in open_positions:
        if len(r)!=13 or r[3] not in ("0","1"):raise ValueError("POSITION_FIELDS_INVALID")
        entry,current,sl,tp=[decimal(n) for n in r[5:9]]
        is_buy=r[3]=="0"
        geometry=sl<entry<tp if is_buy else tp<entry<sl
        crossed=current<=sl if is_buy else current>=sl
        summary.append({"symbol":r[2],"side":"BUY" if is_buy else "SELL",
          "native_stop_geometry_valid":geometry,
          "reported_price_beyond_sl":crossed})
    end=int(lines[18])-int(lines[7])
    offset=int(lines[7])
    end_age=round(now-end)
    return {"broker":"FP Markets","account_suffix":login[-4:],"environment":"DEMO",
      "equity_usd_observed":str(decimal(lines[10])),
      "balance_usd_observed":str(decimal(lines[9])),
      "positions_reported":positions,"pending_orders_reported":pending,
      "deals_reported":deals,"native_stop_geometry_all_valid":all(z["native_stop_geometry_valid"] for z in summary),
      "reported_prices_beyond_sl_count":sum(z["reported_price_beyond_sl"] for z in summary),
      "position_observations":summary,"history_end_age_seconds":end_age,
      "history_end_current":offset==7200 and -5<=end_age<=86400,
      "complete_all_orders_and_stops_reconciled":False}

def inspect(now=None):
    now=time.time() if now is None else float(now)
    reports=[];problems=[]
    rows=quote_owner()
    for cid,broker,env,state,login,server in rows:
        if env!="DEMO" or state!="CONNECTED":continue
        try:
            if broker=="Deriv" and cid==CID:
                reports.append(deriv_inventory(cid,now))
            elif broker=="FP Markets":
                reports.append(fp_inventory(cid,login,server,now))
            else:
                problems.append("CONNECTED_DEMO_ACCOUNT_NOT_IN_SUPPORTED_BROKER_INVENTORY")
        except (ValueError,OSError,UnicodeError,TypeError,IndexError) as err:
            reports.append({"broker":broker,"account_suffix":login[-4:],
                    "environment":"DEMO","verified":False,"error":str(err)[:85]})
            problems.append("BROKER_PROOF_INCOMPLETE_"+broker)
    if not reports:problems.append("NO_CONNECTED_DEMO_ACCOUNT_PROOFS")
    if any(not r.get("history_end_current",True) for r in reports):
        problems.append("FP_BROKER_HISTORY_CLOCK_STALE")
    if any(not r.get("native_stop_geometry_all_valid",True) for r in reports):
        problems.append("FP_STOP_GEOMETRY_INVALID")
    if any(r.get("reported_prices_beyond_sl_count",0)>0 for r in reports):
        problems.append("BROKER_PRICES_BEYOND_REPORTED_STOP_REQUIRES_RECONCILIATION")
    problems+=["CASHFLOW_ADJUSTED_DAILY_AND_PEAK_BASELINES_NOT_PROVEN",
         "BROKER_ORDER_CALC_PROFIT_FULL_CUSTOMER_RISK_NOT_PROVEN",
         "INDEPENDENT_ORDER_POSITION_STOP_EXIT_RECONCILIATION_NOT_PROVEN"]
    return {"schema":"abutron.v4.account_portfolio.readonly.v1",
      "checked_utc":datetime.fromtimestamp(now,timezone.utc).isoformat(),
      "accounts":reports,"connected_demo_count":sum(e=="DEMO" and st=="CONNECTED" for _,_,e,st,_,_ in rows),
      "limits":RISK_CAPS,"blockers":sorted(set(problems)),
      "portfolio_risk_certified":False,"order_authorized":False,
      "orders_submitted":0}

if __name__=="__main__":
    print(json.dumps(inspect(),sort_keys=True,separators=(",",":")))
