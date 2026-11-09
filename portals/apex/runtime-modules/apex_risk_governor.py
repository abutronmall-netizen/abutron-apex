"""APEX independent broker/account risk governor. No broker order API.

Fail-closed: even a passing mathematical screen does not authorize trading.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import math
import os
import tempfile

ACCOUNT=Path("/var/lib/apex/mt5-market/deriv_demo_account.json")
SCAN=Path("/var/lib/apex/scanner/latest.json")
RISK=Path("/var/lib/apex/mt5-market/contract_risk_latest.json")
POLICY=Path("/etc/apex/trading-policy.json")
OUT=Path("/var/lib/apex/risk/latest.json")


def age(value,now):
    d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone required")
    return (now-d).total_seconds()


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,UnicodeError):
        return None


def unique_reasons(values):
    return list(dict.fromkeys(values))


def evaluate(account, scanner, estimate, policy,now=None):
    now=now or datetime.now(timezone.utc)
    reasons=[]
    if not isinstance(policy,dict) or policy.get("environment")!="DERIV_DEMO" or policy.get("live_trading") is not False or policy.get("automated_demo_execution") is not False:
        reasons.append("ROOT_POLICY_LOCKED_OR_INVALID")
    if not isinstance(account,dict) or account.get("source")!="Deriv DEMO MT5" or account.get("execution_enabled") is not False or account.get("orders_placed_by_this_exporter")!=0:
        reasons.append("NO_VERIFIED_BROKER_ACCOUNT")
        a={}
    else:
        a=account.get("account",{})
        if a.get("mode")!="DEMO" or a.get("currency")!="USD":
            reasons.append("NOT_USD_DEMO")
        try:
            secs=age(account.get("generated_at_utc"),now)
            if secs< -30 or secs>420:reasons.append("STALE_BROKER_ACCOUNT")
        except (TypeError,ValueError):reasons.append("BROKER_ACCOUNT_TIME_INVALID")
        p=account.get("positions")
        if not isinstance(p,list) or len(p)!=a.get("open_positions"):
            reasons.append("POSITION_RECONCILIATION_MISMATCH")
        elif p:
            # Existing open broker positions are never ignored.
            reasons.append("EXISTING_POSITIONS_UNCERTIFIED")
            for position in p:
                if not isinstance(position,dict) or position.get("sl",0)<=0:
                    reasons.append("UNPROTECTED_OPEN_POSITION")
        if account.get("history_complete") is not True:
            reasons.append("INCOMPLETE_BROKER_DEAL_HISTORY")
    def valid_pct(value):
        return (isinstance(value,(int,float)) and not isinstance(value,bool)
                and math.isfinite(float(value)) and 0 < float(value) <= 100)

    configured=(isinstance(policy,dict)
                and valid_pct(policy.get("risk_per_trade_pct"))
                and valid_pct(policy.get("max_daily_loss_pct")))
    if not configured:
        reasons.append("RISK_PARAMETERS_NOT_CONFIGURED")
    # These percent-based estimates are informational until the complete,
    # commission-aware broker loss ledger has been independently certified.
    reasons.append("COST_COMPLETE_ACCOUNTING_UNCERTIFIED")
    single_cap=None
    daily_cap=None
    remaining=None
    try:
        realized=float(a["realized_today_usd"])
        gross_negative=float(a["gross_negative_deal_cashflows_today_usd"])
        floating=float(a["floating_profit_usd"])
        equity=float(a["equity_usd"])
        balance=float(a["balance_usd"])
        if (not all(math.isfinite(x) for x in (realized,gross_negative,floating,equity,balance))
                or equity<0 or balance<0 or gross_negative<0):
            raise ValueError
        # Conservative: all negative trading deal cashflows (including
        # entry-side costs) PLUS current negative unrealized exposure.
        used=gross_negative+max(0.,-floating)
        if configured:
            single_cap=round(equity*float(policy["risk_per_trade_pct"])/100,2)
            daily_cap=round(equity*float(policy["max_daily_loss_pct"])/100,2)
            remaining=round(max(0.,daily_cap-used),2)
            if remaining<=0:reasons.append("ACCOUNT_LOSS_REFERENCE_EXHAUSTED")
    except (KeyError,TypeError,ValueError):
        used=None
        reasons.append("UNKNOWN_ACCOUNT_DRAWDOWN")
    if not isinstance(scanner,dict) or scanner.get("source")!="Deriv DEMO MT5" or scanner.get("symbol_count")!=13 or scanner.get("orders_enabled") is not False:
        reasons.append("SCANNER_INVALID")
        items=[]
    else:
        items=scanner.get("instruments",[])
        if not isinstance(items,list) or len(items)!=13:reasons.append("SCANNER_COVERAGE_MISMATCH");items=[]
        try:
            secs=age(scanner.get("generated_at_utc"),now)
            if secs< -30 or secs>240:reasons.append("SCANNER_STALE")
        except (TypeError,ValueError):reasons.append("SCANNER_CLOCK_INVALID")
    contracts=account.get("contracts",[]) if isinstance(account,dict) else []
    specs={x.get("symbol"):x for x in contracts if isinstance(x,dict)}
    hypothetical={}
    if not isinstance(estimate,dict) or estimate.get("status")!="inspection_only" or estimate.get("orders_placed")!=0:
        reasons.append("NO_RISK_ESTIMATES")
    else:
        try:
            secs=age(estimate.get("checked_at_utc"),now)
            if secs< -30 or secs>900:reasons.append("STALE_BROKER_RISK_ESTIMATES")
        except (TypeError,ValueError):reasons.append("INVALID_RISK_ESTIMATE_CLOCK")
        hypothetical={x["symbol"]:x for x in estimate.get("instruments",[]) if isinstance(x,dict) and isinstance(x.get("symbol"),str)}
    proposals=[]
    for record in items:
        symbol=record.get("symbol") if isinstance(record,dict) else None
        side=record.get("proposal") if isinstance(record,dict) else None
        issues=list(reasons)
        if side not in ("BUY","SELL"):
            issues.append("NO_ACTIONABLE_STRATEGY_PROPOSAL")
        broker_spec=specs.get(symbol)
        if not broker_spec or broker_spec.get("ok") is not True:
            issues.append("SYMBOL_BROKER_SPEC_UNVERIFIED")
        else:
            if broker_spec.get("trade_mode",0)==0:
                issues.append("BROKER_SYMBOL_DISABLED")
            try:
                bid,ask=float(broker_spec["bid"]),float(broker_spec["ask"])
                if not (bid>0 and ask>=bid) or (now-datetime.fromisoformat(broker_spec["tick_time_utc"])).total_seconds()>300:
                    issues.append("BROKER_QUOTE_INVALID_OR_STALE")
            except (KeyError,TypeError,ValueError):
                issues.append("BROKER_QUOTE_INVALID_OR_STALE")
        risk=hypothetical.get(symbol)
        est_loss=None
        if not risk or risk.get("verified") is not True:
            issues.append("BROKER_USD_STOP_ESTIMATE_MISSING")
        else:
            est_loss=risk.get("buy_sl_est_usd") if side=="BUY" else risk.get("sell_sl_est_usd")
            if not isinstance(est_loss,(int,float)) or not math.isfinite(float(est_loss)) or est_loss<=0:
                issues.append("INVALID_ESTIMATED_USD_LOSS")
            elif single_cap is None or remaining is None:
                issues.append("RISK_PARAMETERS_NOT_CONFIGURED")
            elif est_loss > min(single_cap,remaining):
                issues.append("SINGLE_ORDER_OR_ACCOUNT_RISK_REFERENCE")
        issues.append("DEMO_EXECUTION_UNCERTIFIED")
        proposals.append({
            "symbol":symbol,"proposal":side,"estimated_min_lot_loss_usd":est_loss,
            "status":"BLOCKED","trade_ready":False,"execution_authorized":False,
            "blockers":unique_reasons(issues),
        })
    return {
        "schema":"apex.risk.governor.v1","generated_at_utc":now.isoformat(),
        "environment":"DERIV_DEMO","orders_enabled":False,"live_enabled":False,
        "kill_switch":"LOCKED","risk_budget_reference_usd":daily_cap,
        "max_single_order_reference_usd":single_cap,
        "risk_per_trade_pct":policy.get("risk_per_trade_pct") if configured else None,
        "max_daily_loss_pct":policy.get("max_daily_loss_pct") if configured else None,
        "risk_parameters_configured":configured,
        "estimated_account_loss_used_usd":round(used,2) if used is not None else None,
        "estimated_account_headroom_usd":remaining,
        "open_positions":a.get("open_positions") if isinstance(a,dict) else None,
        "overall_status":"BLOCKED","system_blockers":unique_reasons(reasons+["DEMO_EXECUTION_UNCERTIFIED"]),
        "proposals":proposals,
    }


def atomic_write(result,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".risk.")
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(result,stream,separators=(",",":"),allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    now=datetime.now(timezone.utc)
    result=evaluate(load(ACCOUNT),load(SCAN),load(RISK),load(POLICY),now)
    atomic_write(result,OUT)
    print(json.dumps({"status":result["overall_status"],"symbols":len(result["proposals"]),
        "kill_switch":result["kill_switch"],"headroom_reference_usd":result["estimated_account_headroom_usd"],
        "orders_enabled":result["orders_enabled"],"blockers":result["system_blockers"]}),flush=True)


if __name__=="__main__":
    main()
