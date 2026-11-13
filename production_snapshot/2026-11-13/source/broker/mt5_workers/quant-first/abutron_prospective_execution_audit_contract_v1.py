#!/usr/bin/env python3
"""Independent execution-evidence contract; never reads credentials or submits orders.

This DOES NOT install hooks into the active MT5 EA. It fails closed by default.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import tempfile
from pathlib import Path

OUT=Path("/var/lib/abutron-quant-first/prospective-execution-audit-readiness-v1.json")
REQ_FIELDS=(
 "signal_key","broker","environment","account_suffix","symbol","side",
 "client_request_created_at_utc","mt5_order_send_called_at_utc",
 "raw_mql5_request_price","execution_mode","send_quote_bid","send_quote_ask",
 "send_quote_time_msc","mt5_request_id","broker_retcode","broker_order_ticket",
 "broker_deal_ticket","broker_ack_recorded_at_utc","broker_fill_price",
 "broker_fill_time_msc","broker_position_id","broker_sl_price",
 "broker_tp_price","broker_protection_verified_at_utc",
 "broker_protection_source")
VALID_STATES=("OPEN_PROTECTED","CLOSED_PROTECTED")

def when(value):
    d=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("MISSING_TIMEZONE")
    return d.astimezone(dt.timezone.utc)

def validate_event(e):
    missing=[k for k in REQ_FIELDS if k not in e or e[k] is None]
    if missing: return ["MISSING_FIELDS:"+",".join(missing)]
    errors=[]
    if e["broker"]!="Deriv" or e["environment"]!="DEMO" or e["account_suffix"]!="6207":
        errors.append("OTHER_ACCOUNT_OR_LIVE_DENIED")
    if e["side"] not in ("BUY","SELL"): errors.append("INVALID_SIDE")
    if not e.get("signal_key") or len(str(e["signal_key"]))!=64:
        errors.append("INVALID_SIGNAL_KEY")
    try:
        created=when(e["client_request_created_at_utc"])
        sent=when(e["mt5_order_send_called_at_utc"])
        ack=when(e["broker_ack_recorded_at_utc"])
        protected=when(e["broker_protection_verified_at_utc"])
        if not created<=sent<=ack<=protected:errors.append("CAUSAL_TIMESTAMP_ORDER_BROKEN")
        bid=float(e["send_quote_bid"]);ask=float(e["send_quote_ask"])
        requested=float(e["raw_mql5_request_price"])
        filled=float(e["broker_fill_price"])
        sl=float(e["broker_sl_price"]);tp=float(e["broker_tp_price"])
        if not all(math.isfinite(v) for v in (bid,ask,requested,filled,sl,tp)):
            errors.append("NONFINITE_PRICE")
        if min(bid,ask,filled,sl,tp)<=0 or requested<0 or ask<bid:
            errors.append("INVALID_BROKER_PRICE")
        if requested==0 and e["execution_mode"]!="MARKET_NO_PRICE":
            errors.append("ZERO_REQUEST_PRICE_NOT_EXPLAINED")
        if requested>0 and e["execution_mode"]=="MARKET_NO_PRICE":
            errors.append("EXECUTION_PRICE_MODE_CONFLICT")
        if e["side"]=="BUY" and not sl<filled<tp:
            errors.append("BROKER_STOP_GEOMETRY_INVALID")
        if e["side"]=="SELL" and not tp<filled<sl:
            errors.append("BROKER_STOP_GEOMETRY_INVALID")
        for key in ("mt5_request_id","broker_order_ticket","broker_deal_ticket","broker_position_id"):
            if int(e[key])<=0:errors.append("INVALID_ID:"+key)
        if int(e["send_quote_time_msc"])<=0 or int(e["broker_fill_time_msc"])<=0:
            errors.append("INVALID_BROKER_MILLISECOND_TIME")
        if e["broker_protection_source"]!="BROKER_POSITION_REQUERY":
            errors.append("NO_INDEPENDENT_BROKER_POSITION_PROTECTION")
        if e.get("broker_position_status") not in VALID_STATES:
            errors.append("POSITION_PROTECTION_STATUS_NOT_PROVEN")
        if e.get("broker_retcode") not in ("TRADE_RETCODE_DONE",10009):
            errors.append("BROKER_ORDER_ACCEPTANCE_NOT_PROVEN")
    except (ValueError,TypeError,OverflowError) as err:
        errors.append("INVALID_FIELD_TYPE_OR_TIME:"+type(err).__name__)
    return errors

def main():
    now=dt.datetime.now(dt.timezone.utc)
    report={
      "schema":"abutron.apex.execution_evidence.contract.v1",
      "checked_at_utc":now.isoformat(),
      "mode":"RESEARCH_READONLY_AUDIT_CONTRACT_NO_ORDER_AUTHORITY",
      "target_demo_account_suffix":"6207",
      "mandatory_fields":REQ_FIELDS,
      "request_price_note":"Record exact raw MqlTradeRequest.price; 0 only for MARKET_NO_PRICE. Also record original bid/ask and native tick timestamp at OrderSend.",
      "timestamp_note":"Client request creation + native OrderSend call + broker acknowledgement + broker deal time + independent protected position requery are distinct clocks/events.",
      "active_ea_audit_hook_verified":False,
      "native_order_runtime_hook_verified":False,
      "actual_broker_request_slippage_distribution_verified":False,
      "complete_protected_new_model_events":0,
      "one_order_test_eligible":False,
      "order_submission_allowed":False,
      "blockers":[
       "ACTIVE_DERIV_MT5_EA_MUST_WRITE_ORIGINAL_REQUEST_PRICE_AND_SEND_TIMESTAMP",
       "MT5_REQUEST_RESULT_MUST_BE_LINKED_TO_BROKER_ORDER_AND_DEAL",
       "BROKER_POSITION_MUST_CONFIRM_ACTUAL_SL_TP",
       "NO_APPROVED_PROSPECTIVE_MODEL"
      ],
      "orders_submitted":0,"positions_changed":0
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.is_symlink():raise ValueError("OUTPUT_IS_SYMLINK")
    fd,tmp=tempfile.mkstemp(prefix=".exec-audit-contract-",dir=OUT.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(report,f,indent=2,allow_nan=False);f.write("\n");f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640);os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("EXECUTION_AUDIT_CONTRACT_STAGED","ACTIVE_EA_HOOK_NOT_YET_WIRED","NO_ORDERS")
if __name__=="__main__":main()
