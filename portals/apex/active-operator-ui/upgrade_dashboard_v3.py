"""Add broker native protected-order precheck and durable intent view."""
from pathlib import Path
from datetime import datetime, timezone
root=Path("/opt/apex/runtime/apex_ui/static")
html,js=(root/x for x in ("index.html","app.js"))
h=html.read_text()
j=js.read_text()
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for p in (html,js):(root/(p.name+".backup-"+stamp)).write_text(p.read_text())


def replace_once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new,1)


h=replace_once(h,
  '<button class="navitem" data-view="account"><span>▣</span> Account & Trades</button>',
  '<button class="navitem" data-view="account"><span>▣</span> Account & Trades</button>\n'
  '    <button class="navitem" data-view="execution"><span>▤</span> Execution Checks</button>')

extra='''<section id="execution" class="view">
  <div class="kpis">
    <article class="metric"><span>Broker directions tested</span><strong id="execEvaluated">—</strong><small>13 instruments × BUY and SELL</small></article>
    <article class="metric"><span>MT5 checks accepted</span><strong id="execAccepted">—</strong><small>Official order_check, not actual fills</small></article>
    <article class="metric"><span>Automatic APEX orders</span><strong id="execOrders">0</strong><small>Still disabled pending certification</small></article>
    <article class="metric"><span>Broker trading lock</span><strong id="execLock">LOCKED</strong><small>Fail-closed root-owned policy</small></article>
  </div>
  <div class="notice"><span class="notice-icon">◈</span><div><b>Prechecks do not place trades</b><span>MT5 validates proposed minimum-lot order requests with attached SL and TP. No broker orders or protected fill lifecycles have been certified.</span></div></div>
  <article class="panel"><div class="panel-head"><div><p class="panel-kicker">OFFICIAL DERIV USD DEMO · REFERENCE LOSS $3</p><h2>Broker-native stop/target prechecks</h2></div><span class="chip" id="execFreshness">CHECKING</span></div>
    <div class="table-scroll"><table><thead><tr><th>Instrument</th><th>Side</th><th>Minimum lot</th><th>Stop-loss</th><th>Take-profit</th><th>Buffered loss · USD</th><th>Broker check</th></tr></thead><tbody id="execPrechecks"></tbody></table></div>
    <p class="table-foot">Risk estimates use short-horizon ATR stops and a 30% modeling buffer, not guaranteed loss limits. A broker-accepted request is not execution certification.</p></article>
  <article class="panel"><div class="panel-head"><div><p class="panel-kicker">DURABLE SQLITE EXECUTION INTENT JOURNAL</p><h2>Duplicate prevention and recovery state</h2></div><span class="chip">NO ORDER SUBMISSION</span></div>
    <div class="risk-numbers"><div><span>Unique signal intents</span><strong id="execIntents">—</strong></div><div><span>Unreconciled orders</span><strong id="execUncertain">—</strong></div><div><span>Execution state</span><strong id="execMode">LOCKED</strong></div></div>
    <p class="muted">Signal identities survive service restarts. Unexpected/uncertain states prevent attempts from being repeated automatically.</p></article>
</section>

'''
h=replace_once(h,'<section id="markets" class="view">',extra+'<section id="markets" class="view">')
j=replace_once(j,
 'const views=["overview","markets","signals","scanner","account","systems"];',
 'const views=["overview","markets","signals","scanner","account","execution","systems"];')
j=replace_once(j,
 'const title={overview:"Operations Overview",markets:"Market Watch",signals:"AI Decisions",scanner:"Strategy Scanner",account:"Account & Trades",systems:"System & Risk"};',
 'const title={overview:"Operations Overview",markets:"Market Watch",signals:"AI Decisions",scanner:"Strategy Scanner",account:"Account & Trades",execution:"Execution Checks",systems:"System & Risk"};')
j=replace_once(j,
 'account:"Broker-confirmed USD DEMO balances, positions and historical deals.",systems:',
 'account:"Broker-confirmed USD DEMO balances, positions and historical deals.",execution:"Broker-verified protected-order prechecks and durable intent tracking.",systems:')
j=replace_once(j,
 '["risk_governor","Independent risk governor"],',
 '["risk_governor","Independent risk governor"],["order_precheck","MT5 order prechecks"],["execution_preview","Execution attempt ledger"],')
j=replace_once(j,
 '    renderScanner(d);',
 '    renderScanner(d);\n    renderExecution(d);')
function="""
function renderExecution(d){
  const p=d.broker_prechecks||{},e=d.execution_preview||{},g=d.risk_governor||{};
  text("execEvaluated",p.available?p.evaluated:"—");
  text("execAccepted",p.available?p.accepted:"—");
  text("execOrders","0");
  text("execLock",g.kill_switch||"LOCKED");
  text("execIntents",e.available?e.total_intents:"—");
  text("execUncertain",e.available?e.unreconciled_orders:"—");
  text("execMode",e.status||"LOCKED");
  text("execFreshness",!p.available?"UNAVAILABLE":p.stale?"STALE":age(p.age_seconds));
  const rows=p.results||[];
  $("execPrechecks").innerHTML=rows.map((x)=>{
    const accepted=x.order_check_accepted===true;
    return '<tr><td class="symboltext">'+esc(x.symbol)+'</td><td>'+esc(x.side)+'</td><td>'+esc(number(x.minimum_lot))+'</td><td>'+esc(number(x.sl))+'</td><td>'+esc(number(x.tp))+'</td><td>$'+esc(number(x.buffered_stop_estimate_usd))+'</td><td><span class="'+(accepted?"val-up":"val-down")+'">'+esc(accepted?"CHECK ACCEPTED":"BLOCKED")+'</span></td></tr>';
  }).join("")||'<tr><td colspan="7">No verified broker precheck records yet.</td></tr>';
}
"""
j=replace_once(j,'async function refreshOverview(){',function+'\nasync function refreshOverview(){')
for key in ("execEvaluated","execAccepted","execOrders","execLock","execPrechecks","execIntents"):
    assert h.count('id="'+key+'"')==1,key
html.write_text(h)
js.write_text(j)
print("PASS execution readiness dashboard view added")
