#!/usr/bin/python3
"""ABUTRON verified native day-start cash balance reconstruction; NOT equity peaks.
READ ONLY. Day-start balance at 00:00 UTC is derived from sampled broker-native
deal cashflows and current balance. Deriv trade-only export cannot prove
missing funding events, thus Deriv numbers are estimates, not certified.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207")
OUT=ROOT/"six-account-native-daystart-cash-audit.json"
RISK=ROOT/"customer-wide-risk-evidence.json"
FIN=ROOT/"six-broker-native-history-reconciliation.json"
PRIV=Path("/var/lib/private")
FP_ACCTS=[("0512","35b81a287b6a030f2f46ff426b135e6c","7410512"),
          ("1636","80cf848587fcec6311dd93560c1c46c6","7411636")]
DERIV_ACCTS=[("6207","32456207"),("7593","6357593"),("9244","202699244")]

def load(p,ttl=205):
    if p.is_symlink() or not p.is_file() or not -4<=time.time()-p.stat().st_mtime<=ttl:
        raise ValueError("NATIVE_SOURCE_MISSING_STALE_OR_LINKED")
    j=json.loads(p.read_text())
    if not isinstance(j,dict):raise ValueError("INVALID_NATIVE_JSON")
    return j

def native_file(p,ttl=205):
    if p.is_symlink() or not p.is_file() or not -5<=time.time()-p.stat().st_mtime<=ttl:
        raise ValueError("NATIVE_FILE_MISSING_OR_STALE")
    return p.read_text(encoding="utf-8-sig").splitlines()

def money(s):
    x=Decimal(str(s))
    if not x.is_finite():raise ValueError("NATIVE_MONEY_NOT_FINITE")
    return x

def native_deriv(suffix,login,report,day_start):
    base=PRIV/("abutron-native-readonly-mt5-"+suffix)
    h=load(base/"worker-health.json",70)
    n=h.get("nonce")
    if (h.get("account_suffix")!=suffix or h.get("status")!="CONNECTED"
        or h.get("broker_session_identity_verified") is not True
        or h.get("native_history_source_authenticated") is not True
        or type(n)!=str or len(n)!=32):
        raise ValueError("DERIV_INDEPENDENT_BROKER_HISTORY_NOT_CONNECTED")
    lines=native_file(base/"terminal/MQL5/Files"/
          ("ABUTRON_APEX_DEAL_HISTORY_V2_"+n+".tsv"))
    if lines[:4]!=["ABUTRON_APEX_DEAL_HISTORY_V2",n,login,"Deriv-Demo"]:
        raise ValueError("DERIV_DEAL_HEADER_NOT_ACCOUNT_BOUND")
    rows=[]
    for l in lines[7:]:
        f=l.split("\t")
        if len(f)!=15 or int(f[4]) not in (0,1):
            raise ValueError("DERIV_HISTORY_FILE_NONTRADE_UNEXPECTED")
        event_time=int(f[3])
        amount=sum((money(f[i]) for i in [11,12,13,14]),Decimal("0"))
        rows.append((event_time,amount))
    if len(rows)!=report["native_deals_in_window"] or not report["selected_window_entry_exit_reconciled"]:
        raise ValueError("DERIV_NATIVE_CLOSED_DEALS_DIVERGED")
    balance=money(report["current_broker_balance_usd"])
    since=sum((val for stamp,val in rows if stamp>=day_start),Decimal("0"))
    return {"broker":"Deriv","account_suffix":suffix,
            "selected_window_deals":len(rows),
            "selected_window_trades_after_utc_daystart":sum(t>=day_start for t,_ in rows),
            "trade_only_daystart_balance_estimate_usd":float(balance-since),
            "current_broker_balance_usd":float(balance),
            "missing_deposit_withdrawal_deals_possible":True,
            "verified_daystart_cash_balance":False,
            "verified_native_intraday_peak_equity":False,
            "reason":"DERIV_NATIVE_EXPORT_SKIPS_CASHFLOW_DEAL_TYPES"}

def native_fp(suffix,cid,login,report,day_start):
    base=PRIV/("abutron-client-mt5-"+cid)
    h=load(base/"worker-health.json",60)
    n=h.get("nonce")
    if h.get("status")!="CONNECTED" or h.get("id")!=cid or h.get("broker")!="FP Markets":
        raise ValueError("FP_WORKER_IDENTITY_INVALID")
    lines=native_file(base/"terminal/MQL5/Files"/
          ("ABUTRON_FP_ACCOUNT_HISTORY_V101_"+n+".txt"),180)
    if (lines[:6]!=["ABUTRON_FP_ACCOUNT_HISTORY_V1",n,lines[2],
                    "FPMarketsSC-Demo",login,"DEMO"]
        or lines[8]!="USD" or lines[19]!="BROKER_NATIVE_NO_ORDER_FUNCTIONS"
        or lines[-1]!="END\t0\t0\t"+lines[16]):
        raise ValueError("FP_NATIVE_DEAL_FOOTER_OR_IDENTITY_INVALID")
    records=[]
    for l in lines[20:-1]:
        cols=l.split("\t")
        if len(cols)!=15 or cols[0]!="D":
            raise ValueError("FP_NATIVE_DEAL_RECORD_INVALID")
        when=int(cols[4])
        flow=sum((money(cols[i]) for i in (11,12,13,14)),Decimal("0"))
        records.append((when,flow,int(cols[5])))
    current=money(lines[9])
    if (len(records)!=report["native_deals_in_window"] or
        abs(current-money(report["current_broker_balance_usd"]))>Decimal(".01") or
        abs(sum((r[1] for r in records),Decimal("0"))-current)>Decimal(".01") or
        not report["cashflow_to_current_balance_certified"]):
        raise ValueError("FP_COMPLETE_WINDOW_CASHFLOW_BALANCE_MISMATCH")
    day_items=[r for r in records if r[0]>=day_start]
    since=sum((r[1] for r in day_items),Decimal("0"))
    start_cash=current-since
    if start_cash<0:raise ValueError("NEGATIVE_RECONSTRUCTED_DAYSTART_CASH")
    return {"broker":"FP Markets","account_suffix":suffix,
            "selected_window_deals":len(records),
            "native_broker_deals_since_utc_daystart":len(day_items),
            "utc_daystart_reconstructed_cash_balance_usd":float(start_cash),
            "current_broker_balance_usd":float(current),
            "cashflow_balance_ties_to_native_window":True,
            "utc_daystart_cash_balance_reconstructed_from_complete_selected_window":True,
            "selected_window_includes_initial_broker_funding":any(r[2]>=2 for r in records),
            "verified_native_intraday_peak_equity":False,
            "source_note":"Native MT5 selected-window closed deals and funding; UTC day boundary, not inferred broker-server trading day"}

def inspect():
    now=time.time()
    day=dt.datetime.fromtimestamp(now,dt.timezone.utc).date()
    midnight=int(dt.datetime.combine(day,dt.time(0),dt.timezone.utc).timestamp())
    risk=load(RISK,145)
    fin=load(FIN,205)
    if (risk.get("native_flat_accounts_verified")!=6 or
        risk.get("native_current_open_exposure_reconciled") is not True or
        fin.get("five_demo_native_trade_windows_reconciled") is not True or
        fin.get("fp_two_demo_balance_cashflows_reconciled") is not True):
        raise ValueError("PARENT_NATIVE_BROKER_PROOFS_UNVERIFIED")
    catalog={(x["broker"],x["account_suffix"]):x for x in fin["accounts"]}
    if len(catalog)!=6:raise ValueError("CRM_ROSTER_CHANGED")
    accounts=[]
    for suffix,login in DERIV_ACCTS:
        accounts.append(native_deriv(suffix,login,catalog["Deriv",suffix],midnight))
    for suffix,cid,login in FP_ACCTS:
        accounts.append(native_fp(suffix,cid,login,catalog["FP Markets",suffix],midnight))
    accounts.append({"account_suffix":"0178","broker":"Deriv","environment":"LIVE",
                     "state":"NO_LIVE_FINANCIAL_DEAL_HISTORY",
                     "utc_daystart_cash_balance_reconstructed":False,
                     "native_intraday_equity_peak_certified":False,
                     "execution_authorized":False})
    return {"schema":"abutron.six_account.native_utc_daystart_cash.reconstruction.ro.v1",
            "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "daystart_definition":"00:00 UTC",
            "daystart_utc":dt.datetime.fromtimestamp(midnight,dt.timezone.utc).isoformat(),
            "accounts":accounts,
            "fp_native_daystart_cash_reconstructed":2,
            "deriv_trade_only_daystart_balance_estimated":3,
            "live_cash_history_reconciled":False,
            "native_true_daystart_equity_certified":False,
            "native_true_intraday_highwater_certified":False,
            "complete_account_lifetime_history_certified":False,
            "current_broker_order_ack_certified":False,
            "read_only":True,
            "orders_submitted":0,
            "execution_enabled":False}

def main():
    x=inspect()
    tmp=OUT.parent/(".daystart-cash-"+str(os.getpid())+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(x,f,indent=2,sort_keys=True)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,OUT)
    finally:tmp.unlink(missing_ok=True)
    print(json.dumps({"FP_native_daystart_cash_broker_reconstructed":
                      x["fp_native_daystart_cash_reconstructed"],
                      "Deriv_trade_only_estimates":
                      x["deriv_trade_only_daystart_balance_estimated"],
                      "true_intraday_equity_peak_certified":False,"orders":0}))
if __name__=="__main__":sys.exit(main())
