"""Make APEX dashboard reflect no-cap multi-symbol v3 truthfully."""
from pathlib import Path
import shutil
root=Path("/opt/apex/runtime/apex_ui")
paths=[root/"app.py",root/"telemetry.py",root/"static/index.html",root/"static/app.js"]
d={p:p.read_text() for p in paths}
def one(p,old,new):
    assert d[p].count(old)==1,(str(p),old[:90],d[p].count(old))
    d[p]=d[p].replace(old,new,1)
app,tele,html,js=paths
d[app]=d[app].replace("apex-demo-auto-v2.timer","apex-demo-auto-v3.timer")
assert d[app].count("apex-demo-auto-v3.timer")==3
one(tele,
'''           and policy.get("max_demo_loss_usd")==140.0)''',
'''           and policy.get("max_demo_loss_usd") is None
           and policy.get("max_concurrent_positions")==13
           and policy.get("max_positions_per_symbol")==1
           and doc.get("controller_version")=="multi_v3")''')
one(tele,
'''            "risk_cap_usd":140 if armed else None,
            "broker_confirmed_orders":doc.get("broker_confirmed_orders"),''',
'''            "risk_cap_usd":None,
            "account_loss_cap_usd":None,
            "controller_version":doc.get("controller_version"),
            "max_concurrent_positions":13 if armed else None,
            "max_positions_per_symbol":1 if armed else None,
            "open_apex_positions":doc.get("open_apex_positions"),
            "open_symbols":doc.get("open_symbols",[]),
            "newly_opened":doc.get("newly_opened",[]),
            "skipped":doc.get("skipped",[]),
            "broker_confirmed_orders":doc.get("broker_confirmed_orders"),''')
d[html]=d[html].replace("$140 DEMO status","DEMO execution status")
d[html]=d[html].replace("separately verified $140 DEMO controller","separately verified v3 DEMO controller")
d[html]=d[html].replace("independently checked $140 USD account-loss admission budget",
                        "independent per-symbol SL/TP and broker margin controls (no account-wide USD loss cap)")
d[html]=d[html].replace("Automatic M5 DEMO orders · $140 account cap",
                        "Automatic M5 DEMO orders · up to 13 simultaneous symbols")
d[html]=d[html].replace("Daily remaining budget · USD","Open APEX positions / 13")
d[html]=d[html].replace("<th>Budget admission</th>","<th>Contract / strategy</th>")
d[html]=d[html].replace("$100 stops require a ~$130 buffered risk allowance and are checked against the remaining $140 account-loss admission budget;",
                        "Each symbol has its own broker-side SL and TP. There is no account-wide USD loss cap;")
d[html]=d[html].replace("The USD cap uses broker cashflows and modelled stop exposure, not a guaranteed maximum fill loss.",
                        "Each order uses its own configured USD SL/TP and broker margin checks. No account-wide loss cap is enforced; losses may exceed stated stops after slippage and costs.")
d[html]=d[html].replace("Verified status from APEX DEMO v2","Verified status from APEX DEMO multi v3")
d[html]=d[html].replace("Separate from controlled DEMO v2","Separate from controlled DEMO multi v3")
one(js,
'''    const budget=Number(auto.remaining_budget_usd);
    const estimated=Number(p.stop_usd)*1.3;
    const eligible=Number.isFinite(budget)&&estimated<=budget;''',
'''    const eligible=auto.usd_profile_active===true;''')
one(js,
'''    const caption=!validLot?"BLOCKED · INVALID BROKER LOT":
      !Number.isFinite(budget)?"WAIT · BUDGET UNKNOWN":
      eligible?"WITHIN $140 BUDGET":"BLOCKED BY $140 CAP";''',
'''    const caption=!validLot?"BLOCKED · INVALID BROKER LOT":
      !eligible?"UNVERIFIED PROFILE":"LOT VALID · SIGNAL/MT5 GATED";''')
one(js,
'''(eligible?"val-up":"val-down")''',
'''(validLot&&eligible?"val-up":"val-down")''')
one(js,
'''    ?"Controlled APEX Deriv DEMO execution enabled with a $140 loss-admission budget. Valid M5 signals only; LIVE remains disabled."''',
'''    ? "APEX Deriv DEMO multi-symbol controller enabled: up to 13 simultaneous positions, one per symbol, individual broker-side USD SL/TP. No account-wide loss cap; LIVE disabled."''')
one(js,
'''  text("demoBudgetRemaining",auto.remaining_budget_usd!=null?"$"+number(auto.remaining_budget_usd):"—");''',
'''  text("demoBudgetRemaining",(auto.open_apex_positions??"—")+"/13");''')
one(js,
'''  text("execGateNote",active?"60-second scheduled DEMO checks":"Check timer / latest cycle");''',
'''  text("execGateNote",active?"Recurring DEMO checks · one entry per symbol":"Check v3 timer / last cycle");''')
one(js,
'''  const mode=!active?"LOCKED":auto.status==="OPEN_PROTECTED"?"POSITION OPEN":
    auto.status==="POSITION_OPEN"?"POSITION OPEN":waiting?"SCANNING":
    auto.status==="BLOCKED"?"SAFETY BLOCK":"READY";''',
'''  const mode=!active?"LOCKED":auto.status==="OPEN_PROTECTED"?"POSITION OPEN":
    auto.status==="POSITION_OPEN"?"POSITION OPEN":auto.status==="FULL"?"13/13 OPEN":
    auto.status==="SCANNING"||waiting?"SCANNING":
    auto.status==="BLOCKED"?"SAFETY BLOCK":"READY";''')
one(js,
'''    else if(Number(a.open_positions)>0){mode="WAIT · OPEN POSITION";kind="signal hold";}
    else {mode="ENTRY CHECK";kind="signal hold";}''',
'''    else {mode="PER-SYMBOL ENTRY CHECK";kind="signal hold";}''')
# Retain the old legacy governor panel explicitly labelled as historical.
for p in paths:
    if p.suffix==".py":compile(d[p],str(p),"exec")
    bak=p.with_name(p.name+".backup-before-multi-v3-ui-20261031")
    shutil.copy2(p,bak)
    tmp=p.with_name("."+p.name+".multi-v3.tmp")
    tmp.write_text(d[p])
    tmp.chmod(p.stat().st_mode&0o777)
for p in paths:
    p.with_name("."+p.name+".multi-v3.tmp").replace(p)
    print("UPDATED",p)
