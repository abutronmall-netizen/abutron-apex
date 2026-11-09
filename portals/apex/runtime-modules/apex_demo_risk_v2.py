"""APEX independent DEMO risk approval v2: percentage-based, always LIVE-locked.

Independent read-only governor. No MT5 order_send, no external platform.
Full account broker flags, 13-symbol broker specifications, actual gross
negative cashflows, current floating loss and stale-data gates.
"""
from datetime import datetime,timezone
from pathlib import Path
import json,os,math,tempfile

ACCOUNT=Path("/var/lib/apex/mt5-market/deriv_demo_account.json")
SCANNER=Path("/var/lib/apex/scanner/latest.json")
ESTIMATES=Path("/var/lib/apex/mt5-market/contract_risk_latest.json")
POLICY=Path("/etc/apex/trading-policy.json")
OUT=Path("/var/lib/apex/risk/latest.json")
FATAL=Path("/var/lib/apex/demo-execution/KILL_SWITCH")
EXPECTED_SYMBOLS=(
    "Volatility 10 Index.0","Volatility 25 Index.0","Volatility 50 Index.0",
    "Volatility 75 Index.0","Volatility 100 Index.0",
    "Crash 150 Index.0","Crash 300 Index.0","Crash 600 Index.0",
    "Crash 1000 Index.0","Boom 150 Index.0","Boom 300 Index.0",
    "Boom 600 Index.0","Boom 1000 Index.0"
)

def load(path):
    try:
        x=json.loads(path.read_text(encoding="utf8"))
        return x if isinstance(x,dict) else None
    except (OSError,UnicodeError,ValueError):
        return None

def fresh(doc,field,now,limit):
    try:
        t=datetime.fromisoformat(str(doc[field]).replace("Z","+00:00"))
        return t.tzinfo is not None and -30<=(now-t).total_seconds()<=limit
    except (TypeError,KeyError,ValueError,OverflowError):
        return False

def good_pct(x):
    return type(x) in (float,int) and math.isfinite(x) and 0<float(x)<=100

def finite(x):
    return type(x) in (float,int) and math.isfinite(x)

def evaluate(account,scan,estimates,policy,now=None,kill_present=False):
    now=now or datetime.now(timezone.utc)
    reasons=[]
    if (not isinstance(policy,dict) or policy.get("schema")!="apex.trading.policy.v1"
        or policy.get("environment")!="DERIV_DEMO" or policy.get("live_trading") is not False):
        reasons.append("INVALID_DEMO_ROOT_POLICY")
    enabled=isinstance(policy,dict) and policy.get("automated_demo_execution") is True and policy.get("operator_demo_authorized") is True
    if not enabled:reasons.append("AUTOMATED_DEMO_NOT_AUTHORIZED")
    pct=policy.get("risk_per_trade_pct") if isinstance(policy,dict) else None
    day=policy.get("max_daily_loss_pct") if isinstance(policy,dict) else None
    configured=good_pct(pct) and good_pct(day) and pct<=2 and day<=5 and day>=pct
    if not configured:reasons.append("ACCOUNT_RISK_PERCENTAGES_INVALID")
    if kill_present:reasons.append("PERSISTENT_EMERGENCY_KILL_SWITCH")
    a={}
    if (not isinstance(account,dict) or account.get("schema")!="apex.mt5.account.v1"
        or account.get("source")!="Deriv DEMO MT5" or account.get("execution_enabled") is not False
        or account.get("orders_placed_by_this_exporter")!=0):
        reasons.append("BROKER_IDENTITY_OR_SOURCE_INVALID")
    else:
        a=account.get("account") if isinstance(account.get("account"),dict) else {}
        if (a.get("broker")!="Deriv" or a.get("mode")!="DEMO" or
            a.get("currency")!="USD"):
            reasons.append("ONLY_DERIV_USD_DEMO")
        if not all(a.get(k) is True for k in
            ("allow_trading_terminal","allow_trading_account","allow_expert_terminal")):
            reasons.append("BROKER_TRADING_PERMISSIONS_DISABLED")
        if not fresh(account,"generated_at_utc",now,420):
            reasons.append("BROKER_ACCOUNT_SNAPSHOT_STALE")
        if account.get("history_complete") is not True:
            reasons.append("BROKER_DEAL_HISTORY_INCOMPLETE")
        positions=account.get("positions")
        if not isinstance(positions,list) or len(positions)!=a.get("open_positions"):
            reasons.append("UNRECONCILED_OPEN_POSITIONS")
        elif len(positions)>0:
            reasons.append("EXISTING_BROKER_POSITIONS")
            if any(not isinstance(p,dict) or
                   not finite(p.get("sl")) or p.get("sl")<=0 for p in positions):
                reasons.append("UNPROTECTED_BROKER_POSITION")
    loss_used=None
    per_allowance=None
    daily_allowance=None
    remaining=None
    try:
        equity=float(a["equity_usd"]); balance=float(a["balance_usd"])
        gross=float(a["gross_negative_deal_cashflows_today_usd"])
        floating=float(a["floating_profit_usd"])
        if not all(math.isfinite(v) for v in (equity,balance,gross,floating)) or equity<=0 or balance<0 or gross<0:
            raise ValueError
        loss_used=round(gross+max(0.0,-floating),2)
        if configured:
            per_allowance=round(equity*float(pct)/100,2)
            daily_allowance=round(equity*float(day)/100,2)
            remaining=round(max(0.0,daily_allowance-loss_used),2)
            if remaining<min(per_allowance,daily_allowance)*0.05:
                reasons.append("DAILY_ACCOUNT_LOSS_ALLOWANCE_EXHAUSTED")
    except (KeyError,ValueError,TypeError):
        reasons.append("BROKER_USD_LOSS_RECONCILIATION_UNAVAILABLE")
    if not isinstance(scan,dict) or scan.get("schema")!="apex.scanner.shadow.v1" or scan.get("source")!="Deriv DEMO MT5" or scan.get("orders_enabled") is not False:
        reasons.append("STRATEGY_SCANNER_INVALID")
        items=[]
    else:
        items=scan.get("instruments")
        if not isinstance(items,list) or len(items)!=13 or set(x.get("symbol") for x in items if isinstance(x,dict))!=set(EXPECTED_SYMBOLS):
            reasons.append("SCAN_13_SYMBOL_COVERAGE_INVALID")
            items=[]
        if not fresh(scan,"generated_at_utc",now,240):
            reasons.append("STRATEGY_SCANNER_STALE")
    contracts={}
    if isinstance(account,dict):
        for item in account.get("contracts",[]):
            if isinstance(item,dict):contracts[item.get("symbol")]=item
        if set(contracts)!=set(EXPECTED_SYMBOLS):reasons.append("BROKER_CONTRACT_COVERAGE_INCOMPLETE")
    broker_losses={}
    if (not isinstance(estimates,dict) or estimates.get("status")!="inspection_only"
        or estimates.get("source")!="Deriv USD DEMO MT5"
        or estimates.get("orders_placed")!=0):
        reasons.append("BROKER_STOP_CALCULATOR_INVALID")
    else:
        if not fresh(estimates,"checked_at_utc",now,900):
            reasons.append("BROKER_STOP_ESTIMATES_STALE")
        for item in estimates.get("instruments",[]):
            if isinstance(item,dict):broker_losses[item.get("symbol")]=item
        if set(broker_losses)!=set(EXPECTED_SYMBOLS):
            reasons.append("BROKER_STOP_ESTIMATE_COVERAGE_INCOMPLETE")
    proposals=[]
    for record in items:
        symbol=record.get("symbol")
        side=record.get("proposal")
        problems=list(reasons)
        if side not in ("BUY","SELL") or side !=record.get("m5_signal"):
            problems.append("NO_CONFIRMED_M5_RESEARCH_ENTRY")
        spec=contracts.get(symbol,{})
        if spec.get("ok") is not True or spec.get("trade_mode")!=4:
            problems.append("BROKER_SYMBOL_NOT_TRADABLE")
        else:
            try:
                bid=float(spec["bid"]);ask=float(spec["ask"])
                tick=datetime.fromisoformat(spec["tick_time_utc"])
                if not math.isfinite(bid) or not math.isfinite(ask) or not bid>0 or ask<bid or (now-tick).total_seconds()>300:
                    problems.append("BROKER_QUOTES_INVALID_OR_STALE")
            except (ValueError,TypeError,KeyError):problems.append("BROKER_QUOTES_INVALID_OR_STALE")
        risk=broker_losses.get(symbol,{})
        estimated=None
        if risk.get("verified") is not True:
            problems.append("BROKER_PROFIT_CALCULATOR_NOT_VERIFIED")
        elif side in ("BUY","SELL"):
            estimated=risk.get("buy_sl_est_usd") if side=="BUY" else risk.get("sell_sl_est_usd")
            if not finite(estimated) or estimated<=0:
                problems.append("BROKER_ESTIMATED_STOP_INVALID")
            elif per_allowance is None or remaining is None or float(estimated)*1.3>min(per_allowance,remaining):
                problems.append("MINIMUM_LOT_EXCEEDS_PERCENT_RISK")
        authorized=not problems
        proposals.append({
            "symbol":symbol,"proposal":side,"estimated_min_lot_loss_usd":estimated,
            "status":"APPROVED" if authorized else "BLOCKED",
            "trade_ready":authorized,"execution_authorized":authorized,
            "blockers":list(dict.fromkeys(problems))
        })
    active=not reasons
    return {
        "schema":"apex.risk.governor.v1","generated_at_utc":now.isoformat(),
        "environment":"DERIV_DEMO","live_enabled":False,
        "orders_enabled":active,"kill_switch":"UNLOCKED" if active else "LOCKED",
        "overall_status":"APPROVED" if active else "BLOCKED",
        "risk_budget_reference_usd":daily_allowance,"max_single_order_reference_usd":per_allowance,
        "risk_per_trade_pct":pct if configured else None,
        "max_daily_loss_pct":day if configured else None,
        "risk_parameters_configured":configured,
        "estimated_account_loss_used_usd":loss_used,
        "estimated_account_headroom_usd":remaining,
        "open_positions":a.get("open_positions") if isinstance(a,dict) else None,
        "system_blockers":list(dict.fromkeys(reasons)),
        "proposals":proposals,
        "authorized_candidates":sum(x["execution_authorized"] for x in proposals),
        "mode":"AUTOMATED_DERIV_DEMO_EXPERIMENTAL",
        "profitability_certified":False
    }

def save(result,path=OUT):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".demo-risk.")
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(result,stream,allow_nan=False,separators=(",",":"))
            stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,0o640);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

if __name__=="__main__":
    report=evaluate(load(ACCOUNT),load(SCANNER),load(ESTIMATES),load(POLICY),kill_present=FATAL.exists())
    save(report)
    print(json.dumps({"state":report["overall_status"],"demo_enabled":report["orders_enabled"],
        "approved_candidates":report["authorized_candidates"],"kill":report["kill_switch"],
        "blockers":report["system_blockers"]}),flush=True)
