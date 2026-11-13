#!/usr/bin/python3
"""ABUTRON 6207/FP0512 account-bound exact-proposal readiness and realized-cost ledger.

READ ONLY. Never manufactures native MT5 OrderCheck, hypothetical signals,
broker execution ACK, SL/TP, commissions or slippage. Consumes broker-native
live quotes/profit-margin attestation and independent realized broker deals.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

CID_DERIV="d6fc2524ec373b8d1bc278a8be3ec635"
CID_FP="35b81a287b6a030f2f46ff426b135e6c"
DB=Path("/var/lib/apex-signup/accounts.sqlite3")
RISK=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/customer-wide-risk-evidence.json")
COST=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/v4-native-execution-cost-6207.json")
HISTORY=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/six-broker-native-history-reconciliation.json")
JOURNAL=Path("/var/lib/abutron-apex11-6207/account-bound-m5-journal.sqlite3")
OUT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/two-broker-exact-preflight-cost-ledger.json")
DERIV_SOURCE=Path("/var/lib/private/abutron-native-readonly-mt5-6207")
FP_SOURCE=Path("/var/lib/apex-signup/fp-native-history")/(CID_FP+".json")
FP_WORKER=Path("/var/lib/private")/("abutron-client-mt5-"+CID_FP)
FP_QUOTE_CLOCK_OFFSET_SECONDS=7200

def read(path,limit=3000000,ttl=175):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or
            st.st_mode&0o022 or st.st_size<3 or st.st_size>limit or
            not -5<=time.time()-st.st_mtime<=ttl):
            raise ValueError("UNTRUSTED_STALE_OR_OVERSIZED_SOURCE")
        blob=os.read(fd,limit+1)
        end=os.fstat(fd)
        if (len(blob)!=st.st_size or
            (st.st_ino,st.st_dev,st.st_mtime_ns,st.st_size)!=
            (end.st_ino,end.st_dev,end.st_mtime_ns,end.st_size)):
            raise ValueError("SOURCE_RACE")
        return blob
    finally:os.close(fd)

def load(path,ttl=175):
    d=json.loads(read(path,ttl=ttl))
    if not isinstance(d,dict):raise ValueError("EVIDENCE_NOT_OBJECT")
    return d

def money(v):
    try:
        d=Decimal(str(v))
        if not d.is_finite():raise ValueError("NONFINITE_NATIVE_VALUE")
        return d
    except (ValueError,TypeError,InvalidOperation):
        raise ValueError("INVALID_NATIVE_MONEY_VALUE")

def data_rows():
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=6) as c:
        c.execute("PRAGMA query_only=ON")
        rows=c.execute("""SELECT x.id,x.account_id,x.account_reference,x.broker,
                           x.environment,x.broker_server,x.status,
                           coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0)
                           FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t
                           ON t.connection_id=x.id
                           WHERE x.id in (?,?)""",(CID_DERIV,CID_FP)).fetchall()
        revision=c.execute("""SELECT revision,desired_enabled,effective_enabled,
                                ack_revision,ack_expires_utc FROM abutron_v4_6207_activation_revision
                                WHERE connection_id=?""",(CID_DERIV,)).fetchone()
    byid={r[0]:r for r in rows}
    if len(byid)!=2 or revision is None or any(r[7]!=1 or r[8]!=0 for r in rows):
        raise ValueError("TWO_DEMO_ACCOUNTS_NOT_PRESENT_AND_EFFECTIVE_OFF")
    d=byid[CID_DERIV]
    f=byid[CID_FP]
    if d[2:7]!=("32456207","Deriv","DEMO","Deriv-Demo","CONNECTED"):
        raise ValueError("DERIV_CRM_ACCOUNT_IDENTITY_CHANGED")
    if f[2:7]!=("7410512","FP Markets","DEMO","FPMarketsSC-Demo","CONNECTED"):
        raise ValueError("FP_CRM_ACCOUNT_IDENTITY_CHANGED")
    if d[1]!=f[1]:
        raise ValueError("TWO_BROKERS_NOT_SAME_CUSTOMER")
    return revision

def commission_stats(pairs):
    grouped=defaultdict(lambda:{"count":0,"total_lots":Decimal("0"),
                                "total_commission_usd":Decimal("0")})
    for sym,volume,commission in pairs:
        lots=money(volume); fee=money(commission)
        if lots<=0 or abs(fee)>100000:
            raise ValueError("NATIVE_VOLUME_OR_COMMISSION_INVALID")
        rec=grouped[sym]
        rec["count"]+=1
        rec["total_lots"]+=lots
        rec["total_commission_usd"]+=fee
    ans={}
    for sym,v in sorted(grouped.items()):
        lots=v["total_lots"]
        ans[sym]={"broker_deal_observations":v["count"],
                  "historical_total_lots":float(lots),
                  "historical_commission_cashflow_usd":float(v["total_commission_usd"]),
                  "observed_commission_cashflow_usd_per_deal_lot":float(v["total_commission_usd"]/lots)}
    return ans

def deriv_history_costs():
    worker=load(DERIV_SOURCE/"worker-health.json",50)
    nonce=worker.get("nonce")
    if (worker.get("status")!="CONNECTED"
        or worker.get("broker")!="Deriv" or worker.get("environment")!="DEMO"
        or worker.get("account_suffix")!="6207"
        or worker.get("broker_session_identity_verified") is not True
        or worker.get("native_history_source_authenticated") is not True
        or type(nonce)!=str or len(nonce)!=32):
        raise ValueError("DERIV_NATIVE_HISTORY_ACCOUNT_NOT_CURRENT")
    data=read(DERIV_SOURCE/"terminal/MQL5/Files"/
              ("ABUTRON_APEX_DEAL_HISTORY_V2_"+nonce+".tsv"),limit=6000000,ttl=200)
    lines=data.decode("utf-8-sig").splitlines()
    if len(lines)<7 or lines[:4]!=[
        "ABUTRON_APEX_DEAL_HISTORY_V2",nonce,"32456207","Deriv-Demo"]:
        raise ValueError("DERIV_SELECTED_WINDOW_HISTORY_IDENTITY_UNVERIFIED")
    items=[]
    for row in lines[7:]:
        f=row.split("\t")
        if len(f)!=15 or not f[0].isdigit():
            raise ValueError("DERIV_HISTORY_CELLS_INVALID")
        if int(f[4]) not in (0,1):continue
        items.append((f[8],f[9],f[12]))
    return {"historical_window_deal_count":len(items),
            "realized_broker_commission_by_symbol":commission_stats(items),
            "execution_ordercheck_for_exact_proposal":False,
            "historical_commission_is_not_prospective_fee_guarantee":True,
            "realized_price_slippage_verified":False}

def fp_history_costs():
    h=load(FP_SOURCE,185)
    if (h.get("schema")!="abutron.fpmarkets.native.account_history.readonly.v1"
        or h.get("account_masked")!="••••0512"
        or h.get("history_verified_from_mt5") is not True
        or h.get("history_complete_within_selected_window") is not True
        or h.get("environment")!="DEMO"
        or h.get("open_positions_count")!=0
        or h.get("pending_orders_count")!=0):
        raise ValueError("FP_ACCOUNT_BOUND_HISTORY_NOT_VERIFIED")
    rows=h.get("trade_deals")
    if not isinstance(rows,list) or len(rows)!=98 or h.get("trade_deals_count")!=len(rows):
        raise ValueError("FP_NATIVE_HISTORY_LENGTH_CHANGED")
    pairs=[]
    seen=set()
    for x in rows:
        if not isinstance(x,dict) or not str(x["ticket"]).isdigit() or x["ticket"] in seen:
            raise ValueError("FP_BROKER_DEAL_TICKET_DUPLICATE")
        seen.add(x["ticket"])
        pairs.append((x["symbol"],x["volume"],x["commission_usd"]))
    return {"historical_window_deal_count":len(pairs),
            "realized_broker_commission_by_symbol":commission_stats(pairs),
            "historical_total_trade_cashflow_usd":h.get("total_trade_deal_cashflow_usd"),
            "realized_price_slippage_verified":False,
            "historical_commission_is_not_prospective_fee_guarantee":True}

def fp_native_quotes():
    health=load(FP_WORKER/"worker-health.json",45)
    nonce=health.get("nonce")
    if (health.get("id")!=CID_FP or health.get("broker")!="FP Markets"
        or health.get("mode")!="DEMO" or health.get("status")!="CONNECTED"
        or health.get("heartbeat_fresh") is not True
        or health.get("server")!="FPMarketsSC-Demo"
        or type(nonce)!=str or len(nonce)!=32):
        raise ValueError("FP_QUOTE_WORKER_IDENTITY_NOT_VERIFIED")
    p=FP_WORKER/"terminal/MQL5/Files"/("ABUTRON_FP_QUOTES_V305_"+nonce+".txt")
    lines=read(p,3000,155).decode("utf-8-sig").splitlines()
    if len(lines)<8 or lines[:6]!=["ABUTRON_FP_QUOTES_V1",nonce,
        lines[2],"FPMarketsSC-Demo","7410512","DEMO"]:
        raise ValueError("FP_NATIVE_QUOTE_HEADER_INVALID")
    if not lines[2] or len(lines[2])!=36:
        raise ValueError("FP_NATIVE_WORKER_ACCOUNT_NONCE_INVALID")
    now=time.time()
    quotes={}
    if lines[-1]!="END\t13":
        raise ValueError("FP_QUOTE_COUNT_FOOTER_INVALID")
    for row in lines[7:-1]:
        f=row.split("\t")
        if len(f)!=5 or f[0] in quotes:
            raise ValueError("FP_QUOTE_ROW_INVALID")
        display,symbol,ts,bid,ask=f
        qt=int(ts)-FP_QUOTE_CLOCK_OFFSET_SECONDS
        bp=money(bid);ap=money(ask)
        if (not -3<=now-qt<=180 or bp<=0 or ap<bp or
            ap-bp>ap*Decimal("0.03")):
            raise ValueError("FP_QUOTE_BROKER_CLOCK_OR_SPREAD_INVALID")
        quotes[display]={"native_symbol":symbol,"bid":float(bp),"ask":float(ap),
                         "spread_price_units":float(ap-bp),
                         "broker_tick_utc_after_verified_offset":qt,
                         "broker_clock_offset_seconds_estimated_not_certified":7200}
    if len(quotes)<6:
        raise ValueError("FP_QUOTE_UNIVERSE_INCOMPLETE")
    return quotes

def proposals(revision,cost):
    # Read actual account-scoped APEX journal. This is shadow-only and cannot
    # replace a real quantity/SL/TP/validity/market request.
    now=time.time()
    with sqlite3.connect("file:"+str(JOURNAL)+"?mode=ro",uri=True,timeout=6) as c:
        c.execute("PRAGMA query_only=ON")
        records=c.execute("""SELECT publication_id,customer_id,account_id,broker,
                             symbol,closed_ts,payload
                             FROM decisions
                             WHERE closed_ts>=? ORDER BY closed_ts DESC LIMIT 35""",
                          (int(now)-660,)).fetchall()
    decisions=[]
    for pid,owner,cid,broker,symbol,closed,payload in records:
        if cid!=CID_DERIV or broker.lower()!="deriv" or not 0<=now-closed<=660:
            raise ValueError("APEX_JOURNAL_ACCOUNT_FENCING_FAILED")
        obj=json.loads(payload)
        if obj.get("publication_schema")!="abutron.apex11.account.shadow.v1":
            raise ValueError("APEX_JOURNAL_NOT_SHADOW_RELEASE")
        if obj.get("connection_id")!=CID_DERIV or obj.get("customer_id")!=owner:
            raise ValueError("APEX_DECISION_CUSTOMER_BINDING_FAILED")
        side=obj.get("status")
        if side not in ("BUY","SELL"):continue
        inst=cost["instruments"].get(symbol)
        if inst is None:raise ValueError("APEX_SYMBOL_NOT_IN_NATIVE_BROKER_COSTS")
        order=obj.get("order")
        lots=obj.get("position_size")
        sl=obj.get("stop_loss")
        tp=obj.get("take_profit")
        reasons=[]
        if order is None:reasons.append("NO_NATIVE_ORDER_OBJECT")
        if lots is None:reasons.append("NO_NATIVE_BROKER_LOT_VOLUME")
        if sl is None:reasons.append("NO_NATIVE_STOP_LOSS_PRICE")
        if tp is None:reasons.append("NO_NATIVE_TAKE_PROFIT_PRICE")
        if obj.get("broker_order_authorized") is not True:
            reasons.append("SHADOW_SIGNAL_NOT_BROKER_AUTHORIZED")
        if obj.get("orders_submitted")!=0:raise ValueError("PUBLISHED_SHADOW_ORDER_SUBMISSION_UNEXPECTED")
        decisions.append({"publication_id":pid,"symbol":symbol,"side":side,
                          "closed_bar_age_s":round(now-closed,1),
                          "native_quote_age_ms_at_broker_sample":inst["tick_age_ms"],
                          "minimum_lots":inst["min_lots"],
                          "native_stops_level_points":inst["stops_level_points"],
                          "exact_broker_ordercheck_passed":False,
                          "broker_execution_ack":False,
                          "preflight_unresolved":reasons,
                          "crm_revision":revision[0]})
    return decisions

def inspect():
    revision=data_rows()
    risk=load(RISK,175)
    history=load(HISTORY,205)
    deriv=load(COST,80)
    if (risk.get("linked_accounts")!=6 or risk.get("native_flat_accounts_verified")!=6
        or risk.get("native_current_open_exposure_reconciled") is not True
        or risk.get("native_current_open_stop_risk_usd")!=0.0
        or risk.get("customer_wide_risk_certified") is not False
        or history.get("five_demo_native_trade_windows_reconciled") is not True
        or history.get("all_six_all_time_history_certified") is not False
        or deriv.get("account_suffix")!="6207"
        or deriv.get("native_bid_ask_and_ordercalcprofit_verified") is not True
        or deriv.get("native_minlot_ordercalcmargin_verified") is not True
        or deriv.get("full_execution_costs_certified") is not False):
        raise ValueError("CURRENT_NATIVE_COST_AND_RISK_SOURCE_INVALID")
    fpquotes=fp_native_quotes()
    dh=deriv_history_costs()
    fh=fp_history_costs()
    fresh=proposals(revision,deriv)
    return {"schema":"abutron.6207.fp0512.exact_execution_preflight_costs.readonly.v1",
            "checked_utc":datetime.now(timezone.utc).isoformat(),
            "crm_6207_revision":revision[0],
            "crm_6207_effective_enabled":False,
            "crm_6207_execution_ack_revision_matched":(
                revision[3] is not None and revision[3]==revision[0]
                and revision[2]==1),
            "broker_execution_ack_6207":False,
            "broker_execution_ack_fp0512":False,
            "read_only":True,"orders_submitted":0,
            "deriv_6207":{
              "native_ordercalcprofit_and_margin_verified":True,
              "native_account_equity_usd":deriv["account_equity_usd"],
              "native_instrument_quotes_and_profit":deriv["instruments"],
              "realized_history_costs":dh,
              "recent_account_bound_apex_directional_shadows":fresh,
              "exact_ordercheck_broker_verified":False,
              "proposal_ready_for_native_ordercheck":False},
            "fp_0512":{
              "native_quotes":fpquotes,
              "realized_history_costs":fh,
              "current_approved_quant_trade_proposal":False,
              "native_ordercalcprofit_for_exact_proposal":False,
              "exact_ordercheck_broker_verified":False,
              "proposal_ready_for_native_ordercheck":False},
            "all_customer_daily_equity_peaks_verified":False,
            "full_lifetime_history_verified":False,
            "full_executable_costs_verified":False,
            "blockers":[
              "DERIV_APEX_SHADOW_HAS_NO_NATIVE_QUANTITY_SL_TP_OR_ORDER_OBJECT",
              "FP_FRESH_APPROVED_QUANT_PROPOSAL_MISSING",
              "BROKER_NATIVE_EXACT_PROPOSAL_ORDERCHECK_NOT_PERFORMED",
              "FUTURE_COMMISSION_SCHEDULE_AND_REALIZED_ORDER_SLIPPAGE_UNVERIFIED",
              "REVISION_FENCED_CRM_EXECUTION_ACK_AND_NEW_BROKER_ORDER_ACK_MISSING",
              "TRUE_DAYSTART_PEAK_EQUITY_AND_LIFETIME_HISTORY_UNVERIFIED"]}

def main():
    if OUT.parent.is_symlink() or not OUT.parent.is_dir() or OUT.parent.stat().st_uid!=0:
        raise RuntimeError("UNTRUSTED_REPORT_LOCATION")
    data=inspect()
    tmp=OUT.parent/(".two-broker-native-costs-"+str(os.getpid())+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(data,f,sort_keys=True,indent=2,allow_nan=False)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,OUT)
    finally:tmp.unlink(missing_ok=True)
    print(json.dumps({"state":"READONLY_NATIVE_COST_LEDGER_WITH_NO_EXACT_ORDER",
         "deriv_realized_commission_symbols":len(
             data["deriv_6207"]["realized_history_costs"]["realized_broker_commission_by_symbol"]),
         "fp_realized_commission_symbols":len(
             data["fp_0512"]["realized_history_costs"]["realized_broker_commission_by_symbol"]),
         "fp_live_quote_symbols":len(data["fp_0512"]["native_quotes"]),
         "current_exact_ordercheck_completed":False,"current_broker_execution_ack":False,
         "orders":0},sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
