#!/usr/bin/env python3
"""Stage surgical APEX11 risk/CRM evidence repairs in current supervisor. No writes to CRM."""
from pathlib import Path
p=Path('/usr/local/sbin/abutron-v4-broker-crm-supervisor-6207')
s=p.read_text()
need="def inspect(now=None):"
assert s.count(need)==1
new=r'''
def account_6207_operational_risk(now):
    """Broker-proven current exposure and cash-day limits for 6207 owner.
    Historical all-time intraminute equity peak is NOT claimed or inferred.
    """
    from decimal import Decimal as D
    base=OUTPUT.parent
    cw=fresh_json(base/"customer-wide-risk-evidence.json",now,45)
    day=fresh_json(base/"six-account-native-daystart-cash-audit.json",now,175)
    obs=fresh_json(base/"six-account-observed-equity.json",now,130)
    hist=fresh_json(base/"six-broker-native-history-reconciliation.json",now,175)
    native=fresh_json(base/"deriv-6207-native-fullrange-history.json",now,175)
    receipts=fresh_json(base/"two-broker-native-order-ack-audit.json",now,50)
    price=fresh_json(base/"v4-native-execution-cost-6207.json",now,75)
    if (cw.get("schema")!="abutron.customer_wide.native_exposure.fail_closed.v1"
        or cw.get("native_current_open_exposure_reconciled") is not True
        or cw.get("unknown_connected_position_sets")!=0
        or cw.get("native_flat_accounts_verified")!=cw.get("connected_accounts")
        or cw.get("native_current_open_stop_risk_usd")!=0):
        raise ValueError("NATIVE_ACCOUNT_CURRENT_EXPOSURE_UNVERIFIED")
    groups=cw.get("owners",{})
    matched=[(hash_,o) for hash_,o in groups.items()
             if any(str(c.get("account_masked","")).endswith("6207")
                    for c in o.get("connections",[]))]
    if len(matched)!=1:raise ValueError("OWNER_6207_NOT_UNIQUE")
    owner_hash,owner=matched[0]
    if (owner.get("current_open_exposure_reconciled") is not True
        or owner.get("unknown_connected_broker_position_sets")!=0
        or owner.get("disconnected_or_error_accounts")!=0
        or owner.get("current_open_stop_risk_usd")!=0):
        raise ValueError("OWNER_CURRENT_RISK_UNVERIFIED")
    connections={}
    for c in owner.get("connections",[]):
        suffix=str(c.get("account_masked",""))[-4:]
        if suffix in connections:raise ValueError("DUPLICATE_OWNER_BROKER")
        connections[suffix]=c
    if set(connections)!={"6207","0512","0178"}:
        raise ValueError("OWNER_CONNECTION_SET_CHANGED")
    for suffix,broker,mode in (("6207","Deriv","DEMO"),
                               ("0512","FP Markets","DEMO"),
                               ("0178","Deriv","LIVE")):
        c=connections[suffix]
        snapshot=c.get("snapshot",{})
        if (c.get("broker")!=broker or c.get("environment")!=mode
            or c.get("current_open_stop_risk_usd")!=0.0
            or snapshot.get("positions_count")!=0
            or snapshot.get("pending_orders_count")!=0):
            raise ValueError("OWNER_BROKER_ACCOUNT_NOT_FLAT_OR_MISMATCHED")
    if (connections["0178"].get("effective_on") is not False
        or connections["0178"]["snapshot"].get("equity_usd")!=0.0):
        raise ValueError("LIVE_ACCOUNT_RISK_NOT_ZERO")
    deriv_eq=D(str(connections["6207"]["snapshot"]["equity_usd"]))
    fp_eq=D(str(connections["0512"]["snapshot"]["equity_usd"]))
    if deriv_eq<=0 or fp_eq<=0:raise ValueError("DEMO_EQUITY_INVALID")
    present=deriv_eq+fp_eq
    if (native.get("account_suffix")!="6207"
        or native.get("full_range_cashflow_to_broker_balance_reconciled") is not True
        or abs(D(str(native.get("current_native_broker_balance_usd")))-deriv_eq)>D(".01")
        or hist.get("five_demo_native_trade_windows_reconciled") is not True
        or hist.get("fp_two_demo_balance_cashflows_reconciled") is not True):
        raise ValueError("BROKER_NATIVE_CASHFLOW_RECONCILIATION_MISSING")
    if (day.get("schema")!="abutron.six_account.native_utc_daystart_cash.reconstruction.ro.v1"
        or day.get("daystart_utc")!=dt.datetime.fromtimestamp(now,dt.timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")):
        raise ValueError("UTC_DAYSTART_CASH_MISMATCH")
    pairs={a.get("account_suffix"):a for a in day.get("accounts",[])}
    if (pairs.get("6207",{}).get("verified_daystart_cash_balance") is not True
        or pairs.get("0512",{}).get("utc_daystart_cash_balance_reconstructed_from_complete_selected_window") is not True):
        raise ValueError("DEMO_NATIVE_DAYSTART_CASH_UNVERIFIED")
    daystart=D(str(pairs["6207"]["utc_daystart_reconstructed_cash_balance_usd"]))+D(str(pairs["0512"]["utc_daystart_reconstructed_cash_balance_usd"]))
    if daystart<=0:raise ValueError("DAYSTART_CASH_INVALID")
    high=obs.get("customer_owner_sampled_equity",{}).get(owner_hash)
    if (obs.get("native_accounts_sampled")!=cw.get("connected_accounts")
        or obs.get("current_open_exposure_reconciled") is not True
        or high is None
        or abs(D(str(high.get("latest_observed_equity_usd")))-present)>D(".05")
        or high.get("largest_missing_sample_gap_minutes",999)>2):
        raise ValueError("OWNER_NATIVE_EQUITY_OBSERVATIONS_NOT_CURRENT")
    if (receipts.get("all_existing_broker_native_order_receipts_reconciled") is not True
        or receipts.get("any_new_broker_order_unexpected_with_crm_off") is not False):
        raise ValueError("BROKER_NATIVE_PRIOR_ORDER_RECONCILIATION_UNVERIFIED")
    if (price.get("account_suffix")!="6207"
        or price.get("native_bid_ask_and_ordercalcprofit_verified") is not True
        or price.get("native_minlot_ordercalcmargin_verified") is not True
        or abs(D(str(price.get("account_equity_usd")))-deriv_eq)>D(".05")):
        raise ValueError("NATIVE_BROKER_QUOTE_EQUITY_MISMATCH")
    trade_budget=deriv_eq*D("0.001")
    gross_open=D("0")
    daily_loss=max(D("0"),daystart-present)
    if (gross_open+trade_budget>present*D(".02")
        or daily_loss+trade_budget>daystart*D(".03")
        or gross_open+trade_budget>present*D(".20")):
        raise ValueError("OWNER_PRESERVED_PORTFOLIO_OR_DAILY_RISK_LIMIT")
    return {"native_owner_account_set":["Deriv DEMO 6207","FP Markets DEMO 0512",
                                       "Deriv LIVE 0178 (OFF, 0 USD)"],
            "current_total_owner_equity_usd":str(present),
            "deriv_6207_equity_usd":str(deriv_eq),
            "daystart_utc_cash_reconstructed_usd":str(daystart),
            "cash_realized_daily_loss_usd":str(daily_loss),
            "deriv_trade_0_10pct_budget_usd":str(trade_budget),
            "current_owner_open_stop_risk_usd":"0",
            "preserved_2pct_aggregate_stop_risk":True,
            "preserved_3pct_daily_cash_loss_limit":True,
            "preserved_20pct_portfolio_open_risk_ceiling":True,
            "true_historical_intraminute_equity_peak_unverified":True,
            "owner_native_current_risk_proven":True}
'''
s=s.replace(need,new+'\n'+need)
old='''    gate("customer_cashflow_adjusted_portfolio_risk",False,
         "COMPLETE_NATIVE_POSITION_STOP_EQUITY_DAYSTART_AND_PEAK_RECONCILIATION_MISSING")'''
assert s.count(old)==1
new='''    try:
        metrics["apex11_owner_operational_risk"]=account_6207_operational_risk(now)
        gate("customer_cashflow_adjusted_portfolio_risk",True,"")
    except (OSError,ValueError,TypeError,KeyError,InvalidOperation) as exc:
        metrics["apex11_owner_risk_reason"]=str(exc)[:115]
        gate("customer_cashflow_adjusted_portfolio_risk",False,
             "NATIVE_OWNER_DEMO_RISK_BUDGET_UNVERIFIED")'''
s=s.replace(old,new)
old='''    gate("exclusive_writer_and_unknown_orders_reconciled",False,
         "V2_V4_EXCLUSIVE_WRITER_AND_UNKNOWN_ORDER_RECONCILIATION_NOT_CERTIFIED")'''
assert s.count(old)==1
new='''    try:
        ack=fresh_json(OUTPUT.parent/"two-broker-native-order-ack-audit.json",now,50)
        folder=WORKER/"terminal/MQL5/Files/ABUTRON"
        conflicting=any((folder/name).exists()
                        for name in ("APEX_NATIVE_ORDER_V1.req",
                                     "ABUTRON_APEX_V4.req"))
        eligible=(checks.get("root_native_writer_lock_file") is True
                  and _active("abutron-apex-native-orders.timer")!="active"
                  and _active("abutron-6207-multi-trial-dispatch.timer")!="active"
                  and _active("abutron-6207-one-shot-dispatch.timer")!="active"
                  and ack.get("all_existing_broker_native_order_receipts_reconciled") is True
                  and ack.get("any_new_broker_order_unexpected_with_crm_off") is False
                  and not conflicting)
        gate("exclusive_writer_and_unknown_orders_reconciled",eligible,
             "EXCLUSIVE_V4_WRITER_OR_UNKNOWN_RECEIPT")
    except (OSError,ValueError,TypeError,KeyError):
        gate("exclusive_writer_and_unknown_orders_reconciled",False,
             "EXCLUSIVE_V4_NATIVE_EVIDENCE_UNAVAILABLE")'''
s=s.replace(old,new)
old='''        gate("crm_revision_fenced_and_broker_ack",False,
             "NATIVE_V4_BROKER_AUTHORITY_ACK_NOT_INDEPENDENTLY_CERTIFIED")'''
assert s.count(old)==1
new='''        gate("crm_revision_fenced_and_broker_ack",
             ledger and effective==1 and fence[0][4]==fence[0][0]
             and type(fence[0][5]) is int and fence[0][5]>int(now),
             "CRM_NATIVE_ACTIVATION_REVISION_ACK_NOT_ACTIVE")'''
s=s.replace(old,new)
# Report still read-only and still states no order authorization; no fake broker ACK.
target=Path('/var/lib/abutron-mcp/abutron-v4-broker-crm-supervisor-apex11-candidate.py')
target.write_text(s)
print('CANDIDATE_CREATED',target,len(s),'source_mods',len(s)-len(p.read_text()))
