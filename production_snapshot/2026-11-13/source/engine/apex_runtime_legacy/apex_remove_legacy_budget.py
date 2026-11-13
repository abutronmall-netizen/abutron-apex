"""Remove temporary fixed dollar reference rules across active APEX runtime.

Risk parameters are intentionally unset until explicit configuration.
No DEMO/LIVE execution can be enabled by this change.
"""
from pathlib import Path
from datetime import datetime,timezone
import json

paths=[
'/etc/apex/trading-policy.json',
'/opt/apex/runtime/apex_risk_governor.py',
'/opt/apex/runtime/apex_mt5_order_precheck.py',
'/opt/apex/runtime/apex_deriv_contract_probe.py',
'/opt/apex/runtime/apex_broker_agent.py',
'/opt/apex/runtime/apex_ui/app.py',
'/opt/apex/runtime/apex_ui/telemetry.py',
'/opt/apex/runtime/apex_ui/static/index.html',
'/opt/apex/runtime/apex_ui/static/app.js',
]
stamp='.backup-risk-settings-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
originals={p:Path(p).read_text() for p in paths}
for p,s in originals.items():
    b=Path(p+stamp)
    b.write_text(s)
    b.chmod(0o600)
def replace(src,old,new,label):
    if src.count(old)!=1:raise RuntimeError(f'{label}: unexpected count {src.count(old)} for {old[:110]!r}')
    return src.replace(old,new,1)

p='/etc/apex/trading-policy.json'
policy=json.loads(originals[p])
policy.pop('max_cumulative_loss_reference_usd',None)
policy.pop('max_single_order_reference_usd',None)
policy['risk_per_trade_pct']=None
policy['max_daily_loss_pct']=None
policy['description']='User-configurable equity-based risk settings required; no default dollar budget. DEMO and LIVE orders locked.'
assert policy['automated_demo_execution'] is False and policy['live_trading'] is False
originals[p]=json.dumps(policy,indent=2)+'\n'

p='/opt/apex/runtime/apex_risk_governor.py';s=originals[p]
s=replace(s,'BUDGET=10.00\nMAX_SINGLE=3.00\n','',p)
s=replace(s,'''    try:
        realized=float(a["realized_today_usd"])
        floating=float(a["floating_profit_usd"])
        equity=float(a["equity_usd"])
        balance=float(a["balance_usd"])
        if not all(math.isfinite(x) for x in (realized,floating,equity,balance)) or equity<0 or balance<0:
            raise ValueError
        used=max(0.,-realized)+max(0.,-floating)
        remaining=round(max(0.,BUDGET-used),2)
        if remaining<=MAX_SINGLE:
            reasons.append("ACCOUNT_LOSS_BUDGET_INSUFFICIENT")
    except (KeyError,TypeError,ValueError):
        used=None
        remaining=0.
        reasons.append("UNKNOWN_ACCOUNT_DRAWDOWN")
''','''    def valid_pct(value):
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
        floating=float(a["floating_profit_usd"])
        equity=float(a["equity_usd"])
        balance=float(a["balance_usd"])
        if not all(math.isfinite(x) for x in (realized,floating,equity,balance)) or equity<0 or balance<0:
            raise ValueError
        used=max(0.,-realized)+max(0.,-floating)
        if configured:
            single_cap=round(equity*float(policy["risk_per_trade_pct"])/100,2)
            daily_cap=round(equity*float(policy["max_daily_loss_pct"])/100,2)
            remaining=round(max(0.,daily_cap-used),2)
            if remaining<=0:reasons.append("ACCOUNT_LOSS_REFERENCE_EXHAUSTED")
    except (KeyError,TypeError,ValueError):
        used=None
        reasons.append("UNKNOWN_ACCOUNT_DRAWDOWN")
''',p)
s=replace(s,'''            elif est_loss > min(MAX_SINGLE,remaining):
                issues.append("SINGLE_ORDER_OR_ACCOUNT_RISK_LIMIT")
''','''            elif single_cap is None or remaining is None:
                issues.append("RISK_PARAMETERS_NOT_CONFIGURED")
            elif est_loss > min(single_cap,remaining):
                issues.append("SINGLE_ORDER_OR_ACCOUNT_RISK_REFERENCE")
''',p)
s=replace(s,'''        "kill_switch":"LOCKED","risk_budget_reference_usd":BUDGET,
        "max_single_order_reference_usd":MAX_SINGLE,''','''        "kill_switch":"LOCKED","risk_budget_reference_usd":daily_cap,
        "max_single_order_reference_usd":single_cap,
        "risk_per_trade_pct":policy.get("risk_per_trade_pct") if configured else None,
        "max_daily_loss_pct":policy.get("max_daily_loss_pct") if configured else None,
        "risk_parameters_configured":configured,''',p)
originals[p]=s

p='/opt/apex/runtime/apex_mt5_order_precheck.py';s=originals[p]
s=replace(s,'USD_SINGLE_REFERENCE=3.0\nUSD_TOTAL_REFERENCE=10.0\n','',p)
s=replace(s,'''                    if buffered>USD_SINGLE_REFERENCE:
                        raise ValueError("Minimum-lot estimated loss exceeds per-order DEMO reference")
''','''                    # Report risk in USD; account-specific limits are set in
                    # the independent risk governor, not in broker order_check.
''',p)
s=replace(s,'''                "single_loss_reference_usd":USD_SINGLE_REFERENCE,
                "aggregate_loss_reference_usd":USD_TOTAL_REFERENCE,
''','''                "single_loss_reference_usd":None,
                "aggregate_loss_reference_usd":None,
''',p)
originals[p]=s

p='/opt/apex/runtime/apex_deriv_contract_probe.py';s=originals[p]
s=replace(s,'BUDGET_USD = 10.0\n','',p)
s=replace(s,'''                              "min_lot_est_below_10_usd": max(buy_loss, sell_loss) < BUDGET_USD,
''','',p)
s=replace(s,'''                  "source": "Deriv USD DEMO MT5", "budget_reference_usd": BUDGET_USD,
''','''                  "source": "Deriv USD DEMO MT5", "budget_reference_usd": None,
''',p)
originals[p]=s

p='/opt/apex/runtime/apex_broker_agent.py';s=originals[p]
s=replace(s,'RISK_REF_USD = 10.0\n','',p)
s=replace(s,'''                    f'under USD 10 estimate={r.get("min_lot_est_below_10_usd")}. '
''','''                    'No preselected dollar-loss threshold is asserted. '
''',p)
s=replace(s,'''    risk_estimate_below=(r.get('min_lot_est_below_10_usd') is True and risk_state=='ok')
''','''    risk_estimate_valid=(r.get('verified') is True and risk_state=='ok')
''',p)
s=replace(s,'''            'risk_probe_current':risk_state=='ok','single_trade_risk_estimate_below_10_usd':risk_estimate_below,
''','''            'risk_probe_current':risk_state=='ok','broker_loss_estimate_valid':risk_estimate_valid,
''',p)
originals[p]=s

p='/opt/apex/runtime/apex_ui/app.py';s=originals[p]
s=replace(s,'''        return {"available": False, "safe_estimates": 0, "not_within_reference": 0, "age_seconds": None, "instruments": {}}''',
'''        return {"available": False, "verified_contracts": 0, "unverified_contracts": 0, "age_seconds": None, "instruments": {}}''',p)
s=replace(s,'''            "under_reference": obj.get("min_lot_est_below_10_usd") is True,''',
'''            "verified": obj.get("verified") is True,''',p)
s=replace(s,'''        "safe_estimates": sum(1 for x in instruments.values() if x["under_reference"]),
        "not_within_reference": sum(1 for x in instruments.values() if not x["under_reference"]),''',
'''        "verified_contracts": sum(1 for x in instruments.values() if x["verified"]),
        "unverified_contracts": sum(1 for x in instruments.values() if not x["verified"]),''',p)
originals[p]=s

p='/opt/apex/runtime/apex_ui/telemetry.py';s=originals[p]
s=replace(s,'''        "reference_usd":doc.get("risk_budget_reference_usd"),''',
'''        "reference_usd":doc.get("risk_budget_reference_usd"),
        "risk_parameters_configured":doc.get("risk_parameters_configured") is True,
        "risk_per_trade_pct":doc.get("risk_per_trade_pct"),
        "max_daily_loss_pct":doc.get("max_daily_loss_pct"),''',p)
originals[p]=s

p='/opt/apex/runtime/apex_ui/static/index.html';s=originals[p]
s=replace(s,'''<span>Estimated headroom · USD</span>''','''<span>Daily loss headroom · USD</span>''',p)
s=replace(s,'''<span>Per-order limit reference · USD</span>''','''<span>Per-order risk allowance · USD</span>''',p)
s=replace(s,'''The USD values are *references and estimates*, not guaranteed loss caps. No LIVE or DEMO broker orders are enabled.''',
'''Risk percentages are unconfigured until explicitly set. USD estimates are not guaranteed loss caps. No LIVE or DEMO broker orders are enabled.''',p)
s=replace(s,'''OFFICIAL DERIV USD DEMO · REFERENCE LOSS $3''',
'''OFFICIAL DERIV USD DEMO · BROKER ORDER VALIDATION''',p)
s=replace(s,'''USD 10 REFERENCE · DEMO ONLY''',
'''CONTRACT-LOSS ESTIMATES · DEMO''',p)
s=replace(s,'''<span>Below risk reference</span>''',
'''<span>Verified contract estimates</span>''',p)
s=replace(s,'''<span>At / above reference</span>''',
'''<span>Unverified contracts</span>''',p)
s=replace(s,'''<th>$10 reference</th>''',
'''<th>Validation</th>''',p)
originals[p]=s

p='/opt/apex/runtime/apex_ui/static/app.js';s=originals[p]
s=replace(s,'''text("riskBelow",risk.available?risk.safe_estimates:"—");''','''text("riskBelow",risk.available?risk.verified_contracts:"—");''',p)
s=replace(s,'''text("riskAbove",risk.available?risk.not_within_reference:"—");''','''text("riskAbove",risk.available?risk.unverified_contracts:"—");''',p)
s=replace(s,'''(r.under_reference?'<span class="val-up">Below estimate</span>':'<span class="val-down">Over / unavailable</span>')''',
'''(r.verified?'<span class="val-up">ESTIMATED</span>':'<span class="val-down">UNVERIFIED</span>')''',p)
s=replace(s,'''text("governorHeadroom",g.available?"$"+number(g.headroom_estimated_usd):"—");''',
'''text("governorHeadroom",g.available&&g.risk_parameters_configured?"$"+number(g.headroom_estimated_usd):"NOT SET");''',p)
s=replace(s,'''text("governorSingle",g.available?"$"+number(g.max_single_reference_usd):"—");''',
'''text("governorSingle",g.available&&g.risk_parameters_configured?"$"+number(g.max_single_reference_usd):"NOT SET");''',p)
originals[p]=s

for p,s in originals.items():
    target=Path(p)
    target.write_text(s)
    target.chmod(0o640 if p.startswith('/etc/apex/') else 0o644)
print('PASS removed old fixed $10/$3 budget logic; trade execution still LOCKED')
