from pathlib import Path
import os
p=Path("/usr/local/sbin/abutron-customer-wide-risk-readonly")
s=p.read_text()
marker='DERIV_NATIVE_RECONCILIATION=Path("/var/lib/abutron-deriv-multi-native-reconciliation/latest.json")'
assert s.count(marker)==1
insert='''FP_DUAL_RECONCILIATION=Path("/var/lib/abutron-fp-execution/dual-account-reconciliation/latest.json")

def independently_verify_fp_native_receipts(cid,login,positions,pending,equity,now):
    """A second reader verifies broker-native FP 90d history and ACK ledger.

    Historical broker receipt ACK does not authorize a new execution ACK.
    """
    blob,st=readfile(FP_DUAL_RECONCILIATION,300000)
    if not -3<=now-st.st_mtime<=145:
        raise ValueError("FP_DUAL_ACCOUNT_RECEIPT_REPORT_STALE")
    d=json.loads(blob)
    if (d.get("schema")!="abutron.fpmarkets.dual_demo_native_reconciliation.readonly.v1"
        or d.get("state")!="RECONCILED_READONLY"
        or d.get("broker_order_authorized") is not False
        or d.get("orders_submitted_by_job")!=0
        or d.get("client_switches_modified") is not False
        or not -3<=utc_age(d.get("at_utc",""),now)<=145):
        raise ValueError("FP_DUAL_BROKER_RECEIPT_CONTRACT_INVALID")
    accounts=d.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("FP_DUAL_ACCOUNT_COUNT_INVALID")
    matches=[x for x in accounts if x.get("connection_suffix")==cid[-6:]
             and x.get("account_suffix")==str(login)[-4:]]
    if len(matches)!=1:
        raise ValueError("FP_INDEPENDENT_ACCOUNT_LINK_NOT_UNIQUE")
    account=matches[0]
    if (account.get("state")!="RECONCILED_READONLY"
        or account.get("connected") is not True
        or account.get("effective_on") is not False
        or account.get("unresolved_receipts")!=0
        or type(account.get("historical_broker_ack")) is not int
        or account["historical_broker_ack"]<0
        or account.get("positions")!=positions or account.get("pending")!=pending
        or type(account.get("equity_usd")) not in (int,float)
        or abs(account["equity_usd"]-equity)>0.01):
        raise ValueError("FP_NATIVE_HISTORY_POSITION_EQUITY_OR_RECEIPT_DIVERGENCE")
    return {"historical_broker_ack_count":account["historical_broker_ack"],
            "90day_broker_trade_deals":account["historical_trade_deals"],
            "unresolved_historical_receipts":0,
            "current_execution_ack_granted":False}

def verified_current_flat_exposure(rec):
    """Only account-bound fresh native proof with zero positions and zero pending."""
    snap=rec.get("snapshot",{})
    if type(snap)!=dict or rec.get("connection_status")!="CONNECTED":
        return False
    if snap.get("positions_count")!=0 or snap.get("pending_orders_count")!=0:
        return False
    if rec.get("broker")=="Deriv" and rec.get("environment")=="DEMO":
        return (rec.get("broker_position_reconciliation_status")=="ZERO_EXPOSURE_DUAL_NATIVE_VERIFIED"
                and snap.get("all_current_position_counts_verified") is True
                and snap.get("all_current_positions_sl_tp_usd_risk_verified") is True
                and snap.get("open_position_usd_stop_risk")==0.0)
    if rec.get("broker")=="FP Markets" and rec.get("environment")=="DEMO":
        return (rec.get("broker_position_reconciliation_status")=="POSITIONS_COUNT_VERIFIED_READONLY"
                and snap.get("native_receipt_reconciliation_verified") is True
                and snap.get("all_position_usd_stop_risk_proved") is True)
    if rec.get("broker")=="Deriv" and rec.get("environment")=="LIVE":
        return (rec.get("broker_position_reconciliation_status")=="SIGNED_LIVE_NO_ORDER_POSITION_COUNTS_VERIFIED"
                and snap.get("positions_count_verified_from_live_broker") is True
                and snap.get("account_execution_authorized") is False
                and snap.get("broker_trade_allowed") is False)
    return False

'''
s=s.replace(marker,insert+marker)
old='''    return {"broker":"FP Markets","account":"••••"+login[-4:],
            "positions_count":len(p),"pending_orders_count":len(o),'''
new='''    receipt=independently_verify_fp_native_receipts(
        cid,login,len(p),len(o),snap["equity_usd"],now)
    return {"broker":"FP Markets","account":"••••"+login[-4:],
            "positions_count":len(p),"pending_orders_count":len(o),'''
assert s.count(old)==1
s=s.replace(old,new)
old='''            "all_position_usd_stop_risk_proved":False,
            "market_quote_fresh_for_trading":False}'''
new='''            "all_position_usd_stop_risk_proved":len(p)==0 and len(o)==0,
            "historical_broker_receipt_reconciliation":receipt,
            "native_receipt_reconciliation_verified":True,
            "market_quote_fresh_for_trading":False}'''
assert s.count(old)==1
s=s.replace(old,new)
# Verified source and no position mean no per-position USD stop calculation is required.
old='''                    rec["blockers"]=["FP_MARKET_QUOTE_STALE_OR_CLOSED",
                                    "NATIVE_ORDER_CALC_PROFIT_PER_POSITION_MISSING",
                                    "ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]'''
new='''                    rec["blockers"]=["ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]
                    rec["entry_blockers"]=["FP_QUOTE_CLOCK_OR_EXECUTABLE_COST_UNCERTIFIED"]
                    if snap["positions_count"] or snap["pending_orders_count"]:
                        rec["blockers"] += ["NATIVE_ORDER_CALC_PROFIT_PER_POSITION_MISSING"]
                    # Zero currently open positions need no hypothetical USD stop
                    # calculation. Entry quote freshness is a separate guard.'''
assert s.count(old)==1
s=s.replace(old,new)
old='''                    rec["blockers"]=["ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "LIVE_NATIVE_POSITION_USD_STOP_RISK_UNCERTIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]'''
new='''                    rec["blockers"]=["ACCOUNT_EQUITY_DAYSTART_PEAK_UNVERIFIED",
                                    "NATIVE_BROKER_ACK_ORDER_RECONCILIATION_PENDING"]
                    rec["entry_blockers"]=["LIVE_BROKER_TRADE_PERMISSION_OFF",
                                            "LIVE_EQUITY_ZERO"]
                    if snap["positions_count"] or snap["pending_orders_count"]:
                        rec["blockers"].append("LIVE_NATIVE_POSITION_USD_STOP_RISK_UNCERTIFIED")'''
assert s.count(old)==1
s=s.replace(old,new)
old='''        if effective==1: rec.setdefault("blockers",[]).append("UNEXPECTED_EFFECTIVE_ON")
        cust["connections"].append(rec)'''
new='''        if effective==1: rec.setdefault("blockers",[]).append("UNEXPECTED_EFFECTIVE_ON")
        certified_flat=verified_current_flat_exposure(rec)
        rec["current_open_exposure_reconciled"]=certified_flat
        rec["current_open_stop_risk_usd"]=0.0 if certified_flat else None
        cust["connections"].append(rec)'''
assert s.count(old)==1
s=s.replace(old,new)
old='''    blocked=sorted(set(b for cust in owners.values() for rec in cust["connections"]
                       for b in rec.get("blockers",[])))'''
new='''    # This is CURRENT observable open-position risk only; never represent
    # it as complete day-start/peak equity, historic trades or execution ACK.
    for owner in owners.values():
        flags=[a["current_open_exposure_reconciled"] for a in owner["connections"]]
        owner["current_open_exposure_reconciled"]=bool(flags) and all(flags)
        owner["current_open_stop_risk_usd"]=(
            0.0 if owner["current_open_exposure_reconciled"] else None)
    all_flat=(bool(rows) and len(rows)==6 and connected_count==6
              and unknown_connected_exposure==0 and
              all(a["current_open_exposure_reconciled"]
                  for owner in owners.values() for a in owner["connections"]))
    blocked=sorted(set(b for cust in owners.values() for rec in cust["connections"]
                       for b in rec.get("blockers",[])))'''
assert s.count(old)==1
s=s.replace(old,new)
old='''           "open_positions_stop_beyond_last_mark":stop_geometry_bad,
           "unknown_connected_position_sets":unknown_connected_exposure,
           "blockers":blocked,"owners":owners,"risk_caps_policy":CAPS,'''
new='''           "open_positions_stop_beyond_last_mark":stop_geometry_bad,
           "unknown_connected_position_sets":unknown_connected_exposure,
           "native_current_open_exposure_reconciled":all_flat,
           "native_current_open_stop_risk_usd":0.0 if all_flat else None,
           "native_flat_accounts_verified":sum(a["current_open_exposure_reconciled"]
                                                for c in owners.values()
                                                for a in c["connections"]),
           "current_open_exposure_vs_full_drawdown_risk_distinguished":True,
           "blockers":blocked,"owners":owners,"risk_caps_policy":CAPS,'''
assert s.count(old)==1
s=s.replace(old,new)
compile(s,str(p),"exec")
Path("/var/lib/abutron-mcp/abutron-six-current-exposure-risk-readonly-candidate.py").write_text(s)
print("CANDIDATE_SYNTAX_OK size",len(s))
