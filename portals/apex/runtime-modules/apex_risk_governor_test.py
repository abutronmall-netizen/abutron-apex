"""APEX risk regression suite after replacement of fixed dollar limits.

No fixed default amount is set; percentage policies are simulation-only until
commission-complete accounting and real broker execution certified.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from apex_risk_governor import evaluate
import copy
import json

read=lambda path:json.loads(Path(path).read_text())
a=read("/var/lib/apex/mt5-market/deriv_demo_account.json")
s=read("/var/lib/apex/scanner/latest.json")
r=read("/var/lib/apex/mt5-market/contract_risk_latest.json")
p=read("/etc/apex/trading-policy.json")
now=datetime.now(timezone.utc)

def check(account=a,scanner=s,risk=r,policy=p):
    x=evaluate(account,scanner,risk,policy,now)
    assert x["kill_switch"]=="LOCKED"
    assert x["orders_enabled"] is False and x["live_enabled"] is False
    assert x["overall_status"]=="BLOCKED"
    assert all(o["trade_ready"] is False and o["execution_authorized"] is False for o in x["proposals"])
    return x

x=check()
assert x["risk_parameters_configured"] is False
assert x["risk_budget_reference_usd"] is None and x["max_single_order_reference_usd"] is None
assert x["estimated_account_headroom_usd"] is None
assert "RISK_PARAMETERS_NOT_CONFIGURED" in x["system_blockers"]
print("PASS no hidden dollar defaults and execution remains locked")

new=copy.deepcopy(p);new["risk_per_trade_pct"]=0.5;new["max_daily_loss_pct"]=2.0
x=check(policy=new)
e=a["account"]["equity_usd"]
assert x["risk_parameters_configured"] is True
assert x["max_single_order_reference_usd"]==round(e*.005,2)
assert x["risk_budget_reference_usd"]==round(e*.02,2)
print("PASS simulated equity-based risk settings")

for badv in (-1,0,101,None,"1"):
    bad=copy.deepcopy(new);bad["risk_per_trade_pct"]=badv
    assert "RISK_PARAMETERS_NOT_CONFIGURED" in check(policy=bad)["system_blockers"]
print("PASS reject malformed percentage settings")

bad=copy.deepcopy(new);bad["live_trading"]=True
assert "ROOT_POLICY_LOCKED_OR_INVALID" in check(policy=bad)["system_blockers"]
print("PASS LIVE remains locked")

bad=copy.deepcopy(new);bad["automated_demo_execution"]=True
assert "ROOT_POLICY_LOCKED_OR_INVALID" in check(policy=bad)["system_blockers"]
print("PASS unauthorized DEMO activation rejected")

bad=copy.deepcopy(a);bad["account"]["mode"]="REAL"
assert "NOT_USD_DEMO" in check(account=bad)["system_blockers"]
print("PASS LIVE broker rejected")

bad=copy.deepcopy(a)
bad["positions"]=[{"ticket":1,"sl":0}]
bad["account"]["open_positions"]=1
assert "UNPROTECTED_OPEN_POSITION" in check(account=bad)["system_blockers"]
print("PASS unprotected position blocks")

bad=copy.deepcopy(a)
bad["generated_at_utc"]=(now-timedelta(minutes=60)).isoformat()
assert "STALE_BROKER_ACCOUNT" in check(account=bad)["system_blockers"]
print("PASS stale broker telemetry blocked")

bad=copy.deepcopy(s)
bad["generated_at_utc"]=(now-timedelta(minutes=60)).isoformat()
assert "SCANNER_STALE" in check(scanner=bad)["system_blockers"]
print("PASS stale scanner signal blocked")

bad=copy.deepcopy(a)
bad["account"]["realized_today_usd"]=-500.
assert "ACCOUNT_LOSS_REFERENCE_EXHAUSTED" in check(account=bad,policy=new)["system_blockers"]
print("PASS simulated account drawdown exhausts configured loss reference")

bad=copy.deepcopy(a);bad["history_complete"]=False
assert "INCOMPLETE_BROKER_DEAL_HISTORY" in check(account=bad)["system_blockers"]
print("PASS incomplete broker-history reconciliation blocked")

assert "COST_COMPLETE_ACCOUNTING_UNCERTIFIED" in check()["system_blockers"]
print("PASS commission accounting not falsely certified")
print("RESULT: 12/12 categories passed; no broker order submission")
