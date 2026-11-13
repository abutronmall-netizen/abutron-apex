"""V7 authenticated Deriv Options public Multiplier DEVELOPMENT research.

Strictly public broker indicative quote provenance, NOT customer DEMO tokens,
order gateway, purchasing, or any V7 account mutations.
"""
from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
import json
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import JSONResponse
from app.models import Customer
from app.security import get_current_customer

REPORT=Path("/var/lib/abutron-v7-deriv-options/public_quotes_latest.json")
TARGETS=frozenset(("R_10","R_25","R_50","R_75","R_100",
 "CRASH150N","CRASH300N","CRASH600","CRASH1000",
 "BOOM150N","BOOM300N","BOOM600","BOOM1000"))
SIDES=frozenset(("MULTUP","MULTDOWN"))
router=APIRouter(prefix="/api/v1",tags=["deriv-options-demo-development"])

def decimal_field(value):
    if type(value) is not str:return None
    try:
        d=Decimal(value)
        return d if d.is_finite() and d>=0 else None
    except (InvalidOperation,ValueError):return None

def verify_public_report(path:Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>65000:
        raise ValueError("QUOTE_REPORT_MISSING_OR_UNTRUSTED")
    d=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(d,dict) or d.get("schema")!="ABUTRON_DERIV_OPTIONS_13_PUBLIC_MULTIPLIER_PROPOSAL_PRECHECK_V1":
        raise ValueError("QUOTE_SCHEMA_MISMATCH")
    for field in ("public_quote_not_account_specific",):
        if d.get(field) is not True:raise ValueError("QUOTE_SCOPE_MUTATED")
    for field in ("separate_deriv_options_demo_auth_verified",
                  "demo_balance_and_existing_exposures_reconciled",
                  "commission_all_in_debit_broker_account_attested",
                  "quote_locked_or_trade_price_guaranteed",
                  "strategy_profitable_independently_forward_certified",
                  "demo_order_approval","live_trading_enabled"):
        if d.get(field) is not False:raise ValueError("PRIVILEGED_RISK_STATE_UNVERIFIED")
    if d.get("demo_orders_placed")!=0 or d.get("existing_ctrader_cfds")!="RESEARCH_ONLY":
        raise ValueError("TRADE_SCOPE_CHANGED")
    if (d.get("requested_13_symbols")!=13 or d.get("requested_up_down_proposals")!=26 or
        d.get("position_model_debit_ceiling_usd")!="2.00" or
        d.get("session_model_budget_usd")!="5.00" or
        d.get("emergency_model_ceiling_usd")!="10.00"):
        raise ValueError("RISK_POLICY_VERSION_CHANGED")
    dt=datetime.fromisoformat(d["observed_at_utc"])
    if dt.tzinfo is None:raise ValueError("UNTRUSTED_TIMESTAMP")
    age=(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()
    if not -60<=age<=24*3600:raise ValueError("EXPIRED_INDICATIVE_QUOTES")
    lines=d.get("quotes")
    if not isinstance(lines,list) or len(lines)!=26:raise ValueError("EXPECTED_26_PROBES")
    seen=set();out=[]
    for row in lines:
        if not isinstance(row,dict):raise ValueError("INVALID_PUBLIC_QUOTE_ROW")
        pair=(row.get("symbol"),row.get("direction"))
        if pair in seen or pair[0] not in TARGETS or pair[1] not in SIDES:
            raise ValueError("MISSING_DUPLICATED_OR_FORGED_CONTRACT_PAIR")
        seen.add(pair)
        if row.get("account_specific") is not False or row.get("demo_execution_allowed") is not False:
            raise ValueError("FALSE_BROKER_ACCOUNT_ATTESTATION")
        status=row.get("status")
        if status not in ("PUBLIC_PRICED","PUBLIC_PRICING_REJECTED",
                          "PUBLIC_QUERY_UNAVAILABLE",
                          "NO_BROKER_PRICING_CONTRACT_PROPOSAL",
                          "ASK_OR_COMMISSION_MISSING"):
            raise ValueError("INVALID_QUOTE_STATUS")
        if status=="PUBLIC_PRICED":
            ask=decimal_field(row.get("public_ask_usd"))
            fee=decimal_field(row.get("public_commission_usd"))
            debit=decimal_field(row.get("conservative_planning_debit_usd"))
            if any(x is None for x in (ask,fee,debit)) or ask<=0 or debit!=max(ask,Decimal("1.00"))+fee:
                raise ValueError("PUBLIC_CASH_QUOTE_CALCULATION_MISMATCH")
            if row.get("provider_public_quote_eligible_for_study") is not (debit<=Decimal("2.00")):
                raise ValueError("INCORRECT_DEBIT_THRESHOLD")
            out.append({"symbol":pair[0],"direction":pair[1],"status":status,
                "public_ask_usd":str(ask),"public_commission_usd":str(fee),
                "conservative_debit_usd":str(debit),
                "public_under_2_usd":debit<=Decimal("2.00"),
                "demo_account_priced":False,"order_authorized":False})
        else:
            if row.get("provider_public_quote_eligible_for_study") is True:
                raise ValueError("UNPRICED_CONTRACT_MARKED_ELIGIBLE")
            out.append({"symbol":pair[0],"direction":pair[1],"status":status,
                        "public_ask_usd":None,"public_commission_usd":None,
                        "conservative_debit_usd":None,"public_under_2_usd":False,
                        "demo_account_priced":False,"order_authorized":False})
    if len(seen)!=26:raise ValueError("INCOMPLETE_QUOTES")
    priced=sum(x["status"]=="PUBLIC_PRICED" for x in out)
    eligible=sum(x["public_under_2_usd"] for x in out)
    if priced!=d.get("publicly_priced_proposals") or eligible!=d.get("publicly_priced_conservatively_under_2usd"):
        raise ValueError("SUMMARY_COUNTS_DONT_MATCH_SOURCE")
    return {
     "schema":"ABUTRON_V7_DERIV_OPTIONS_PUBLIC_MULTIPLIERS_DEVELOPMENT_V1",
     "snapshot_utc":d["observed_at_utc"],
     "stage":"PUBLIC_DISCOVERY_NOT_ACCOUNT_DEMO_AUTH",
     "target_underlyings":13,"requested_contract_directions":26,
     "public_contracts_priced":priced,"public_quotes_under_2usd":eligible,
     "planned_max_debit_per_contract_usd":"2.00",
     "planned_max_total_session_debit_usd":"5.00",
     "emergency_ceiling_usd":"10.00",
     "public_quote_not_executable_or_account_specific":True,
     "deriv_options_demo_account_connected":False,
     "broker_exposure_reconciled":False,
     "strategy_profitable_certified":False,
     "orders_authorized":False,
     "orders_placed":0,
     "existing_13_ctrader_cfds":"RESEARCH_ONLY",
     "quotes":out,
    }

@router.get("/research/deriv-options/multipliers")
async def get_options_multiplier_research(_customer:Customer=Depends(get_current_customer)):
    try:payload=verify_public_report(REPORT)
    except Exception as exc:
        raise HTTPException(503,"DERIV_MULTIPLIER_PUBLIC_RESEARCH_UNAVAILABLE") from exc
    return JSONResponse(payload,headers={"Cache-Control":"private, no-store, max-age=0",
                                      "X-Content-Type-Options":"nosniff"})
