"""Apply APEX operator dashboard v2 enhancements (idempotent, backup first)."""
from pathlib import Path
from datetime import datetime,timezone

root=Path("/opt/apex/runtime/apex_ui/static")
html=root/"index.html"
js=root/"app.js"
css=root/"style.css"
h=html.read_text()
j=js.read_text()
c=css.read_text()
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for path in (html,js,css):
    (root/(path.name+".backup-"+stamp)).write_text(path.read_text())

def change_once(data,old,new):
    if data.count(old)!=1:
        raise RuntimeError("Unexpected source layout: "+old[:70]+" count "+str(data.count(old)))
    return data.replace(old,new,1)

h=change_once(h,
  '<button class="navitem" data-view="signals"><span>⌁</span> AI Decisions</button>',
  '<button class="navitem" data-view="signals"><span>⌁</span> AI Decisions</button>\n'
  '    <button class="navitem" data-view="scanner"><span>◈</span> Strategy Scanner</button>\n'
  '    <button class="navitem" data-view="account"><span>▣</span> Account & Trades</button>')
h=change_once(h,
    '<section id="overview" class="view active">',
    '<section id="overview" class="view active">')

new_stats='''<div class="account-strip">
    <article class="metric"><span>Broker balance · USD</span><strong id="homeBalance">—</strong><small>Authenticated Deriv DEMO</small></article>
    <article class="metric"><span>Broker equity · USD</span><strong id="homeEquity">—</strong><small>Including open P&amp;L</small></article>
    <article class="metric"><span>Open broker positions</span><strong id="homePositions">—</strong><small>Confirmed by MetaTrader 5</small></article>
    <article class="metric"><span>Risk kill switch</span><strong id="homeRiskLock">—</strong><small>Broker orders require separate certification</small></article>
  </div>
'''
h=change_once(h,'  <div class="main-grid">',new_stats+'\n  <div class="main-grid">')
account='''<section id="account" class="view">
  <div class="kpis">
    <article class="metric"><span>Balance · USD</span><strong id="accountBalance">—</strong><small>Broker-confirmed DEMO</small></article>
    <article class="metric"><span>Equity · USD</span><strong id="accountEquity">—</strong><small>Current account snapshot</small></article>
    <article class="metric"><span>Free margin · USD</span><strong id="accountFreeMargin">—</strong><small>Not available for automatic execution</small></article>
    <article class="metric"><span>Today's realized P&amp;L · USD</span><strong id="accountTodayPnl">—</strong><small>All broker trades, not APEX-only</small></article>
  </div>
  <article class="panel"><div class="panel-head"><div><p class="panel-kicker">OFFICIAL DERIV MT5 ACCOUNT</p><h2>Open positions</h2></div><span class="chip" id="accountFreshness">CHECKING</span></div>
  <div class="table-scroll"><table><thead><tr><th>Ticket</th><th>Symbol</th><th>Side</th><th>Volume</th><th>Open</th><th>Current</th><th>Stop</th><th>Target</th><th>Floating USD</th></tr></thead><tbody id="accountPositions"></tbody></table></div>
  <p class="table-foot">Broker positions are reported from the connected MT5 DEMO terminal. No order-entry controls are enabled.</p></article>
  <article class="panel"><div class="panel-head"><div><p class="panel-kicker">OFFICIAL BROKER HISTORY</p><h2>Recent execution deals</h2></div><span class="chip">HISTORICAL / ALL SOURCES</span></div>
  <div class="table-scroll"><table><thead><tr><th>UTC time</th><th>Symbol</th><th>Side</th><th>Event</th><th>Volume</th><th>Price</th><th>Gross P&amp;L</th><th>Net cashflow</th></tr></thead><tbody id="accountDeals"></tbody></table></div>
  <p class="table-foot">Historical broker trades were not necessarily created by APEX. The dashboard does not attribute them to this new agent system.</p></article>
</section>

<section id="scanner" class="view">
  <div class="kpis">
    <article class="metric"><span>Instruments scanned</span><strong id="scanSymbols">—</strong><small>Volatility, Crash &amp; Boom</small></article>
    <article class="metric"><span>Research proposals</span><strong id="scanCandidates">—</strong><small>Not actionable without certification</small></article>
    <article class="metric"><span>Scanner freshness</span><strong id="scanFreshness">—</strong><small id="scanAge">Checking scanner output</small></article>
    <article class="metric"><span>Independent risk decision</span><strong id="scanRisk">LOCKED</strong><small>DEMO execution not authorized</small></article>
  </div>
  <article class="panel"><div class="panel-head"><div><p class="panel-kicker">DETERMINISTIC MULTI-TIMEFRAME RESEARCH</p><h2>All 13 Deriv strategy proposals</h2></div><span class="chip">ORIGINAL BROKER CANDLES</span></div>
  <div class="table-scroll"><table><thead><tr><th>Instrument</th><th>Family</th><th>M15</th><th>H1</th><th>H4</th><th>RSI M5</th><th>Proposal</th><th>Independent risk</th><th>Evidence / Reason</th></tr></thead><tbody id="scannerBody"></tbody></table></div>
  <p class="table-foot">Experimental EMA/RSI logic using completed Deriv candles. Crash/Boom research is held pending dedicated spike-model testing. A proposal is not a validated profitable strategy or order approval.</p></article>
  <article class="panel"><div class="panel-head"><div><p class="panel-kicker">ACCOUNT-WIDE DEMO RISK</p><h2>Independent Risk Governor</h2></div><span class="chip">FAIL CLOSED</span></div>
  <div class="risk-numbers"><div><span>Estimated headroom · USD</span><strong id="governorHeadroom">—</strong></div><div><span>Per-order limit reference · USD</span><strong id="governorSingle">—</strong></div><div><span>Kill switch</span><strong id="governorKill">LOCKED</strong></div></div>
  <p class="muted" id="governorNotes">The risk governor independently validates broker snapshots, active positions, aggregate exposure, loss history and minimum-lot USD estimates.</p>
  <p class="warning-copy">The USD values are *references and estimates*, not guaranteed loss caps. No LIVE or DEMO broker orders are enabled.</p></article>
</section>

'''
h=change_once(h,'<section id="markets" class="view">',account+'<section id="markets" class="view">')

j=change_once(j,'const views=["overview","markets","signals","systems"];',
             'const views=["overview","markets","signals","scanner","account","systems"];')
j=change_once(j,'const title={overview:"Operations Overview",markets:"Market Watch",signals:"AI Decisions",systems:"System & Risk"};',
             'const title={overview:"Operations Overview",markets:"Market Watch",signals:"AI Decisions",scanner:"Strategy Scanner",account:"Account & Trades",systems:"System & Risk"};')
j=change_once(j,'const subtitle={overview:"Broker prices, automatic AI decisions and real infrastructure status.",markets:"13 Deriv synthetic instruments · Six completed-candle timeframes.",signals:"Saved decisions from the original TradingAgents workflow.",systems:"Live infrastructure checks and estimated broker contract exposure."};',
             'const subtitle={overview:"Broker prices, automatic AI decisions and real infrastructure status.",markets:"13 Deriv synthetic instruments · Six completed-candle timeframes.",signals:"Saved decisions from the original TradingAgents workflow.",scanner:"13-symbol multi-timeframe scanner and independent risk approval checks.",account:"Broker-confirmed USD DEMO balances, positions and historical deals.",systems:"Live infrastructure checks and estimated broker contract exposure."};')
j=change_once(j,'["local_model","Local Qwen inference"],',
             '["local_model","Local Qwen inference"],["fast_scanner","13-symbol fast scanner"],["broker_account","Deriv account reconciliation"],["usd_risk","MT5 USD-risk calculator"],["risk_governor","Independent risk governor"],')
j=change_once(j,'    renderRisk(d);','    renderRisk(d);\n    renderAccount(d);\n    renderScanner(d);')

j_add="""
function renderAccount(d){
  const a=d.broker_account||{};
  const valid=a.available===true;
  const bal=valid?"$"+number(a.balance_usd):"—";
  const equ=valid?"$"+number(a.equity_usd):"—";
  text("homeBalance",bal);text("homeEquity",equ);text("homePositions",valid?a.open_positions:"—");
  text("accountBalance",bal);text("accountEquity",equ);
  text("accountFreeMargin",valid?"$"+number(a.free_margin_usd):"—");
  text("accountTodayPnl",valid?"$"+number(a.realized_today_usd):"—");
  text("accountFreshness",!valid?"UNAVAILABLE":a.stale?"STALE":age(a.age_seconds));
  const positions=a.positions||[];
  $("accountPositions").innerHTML=positions.length?positions.map((p)=>
    '<tr><td>'+esc(p.ticket)+'</td><td class="symboltext">'+esc(p.symbol)+'</td><td>'+esc(p.side)+'</td><td>'+esc(number(p.volume))+'</td><td>'+esc(number(p.price_open))+'</td><td>'+esc(number(p.price_current))+'</td><td>'+esc(number(p.sl))+'</td><td>'+esc(number(p.tp))+'</td><td class="'+(p.profit_usd>=0?"val-up":"val-down")+'">'+esc(number(p.profit_usd))+'</td></tr>').join(""):'<tr><td colspan="9">'+(valid?"No broker positions currently open.":"Broker account data unavailable.")+'</td></tr>';
  const deals=a.recent_deals||[];
  $("accountDeals").innerHTML=deals.length?deals.map((v)=>
   '<tr><td>'+esc(clock(v.time_utc))+'</td><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.side)+'</td><td>'+esc(v.entry)+'</td><td>'+esc(number(v.volume))+'</td><td>'+esc(number(v.price))+'</td><td class="'+(v.profit_usd>=0?"val-up":"val-down")+'">'+esc(number(v.profit_usd))+'</td><td class="'+(v.net_cashflow_usd>=0?"val-up":"val-down")+'">'+esc(number(v.net_cashflow_usd))+'</td></tr>').join(""):'<tr><td colspan="8">No broker deal records available.</td></tr>';
}
function renderScanner(d){
  const s=d.scanner||{},g=d.risk_governor||{};
  text("scanSymbols",s.available?s.symbols+"/13":"—");
  text("scanCandidates",s.available?s.candidates:"—");
  text("scanFreshness",s.stale?"STALE":"CURRENT");
  text("scanAge",age(s.age_seconds));
  text("scanRisk",g.kill_switch||"LOCKED");
  text("homeRiskLock",g.kill_switch||"LOCKED");
  text("governorHeadroom",g.available?"$"+number(g.headroom_estimated_usd):"—");
  text("governorSingle",g.available?"$"+number(g.max_single_reference_usd):"—");
  text("governorKill",g.kill_switch||"LOCKED");
  text("governorNotes","Risk status: "+(g.status||"BLOCKED")+
    " · "+(g.blockers||["NO VERIFIED RISK CONTROLS"]).join(" · ")+
    " · Last validation: "+age(g.age_seconds)+".");
  const bySymbol=new Map((g.proposals||[]).map(x=>[x.symbol,x]));
  const rows=s.instruments||[];
  $("scannerBody").innerHTML=rows.map((v)=>{
   const risk=bySymbol.get(v.symbol)||{};
   return '<tr><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.family)+'</td><td>'+badgeTrend(v.m15_trend)+'</td><td>'+badgeTrend(v.h1_trend)+'</td><td>'+badgeTrend(v.h4_trend)+'</td><td>'+esc(number(v.m5_rsi))+'</td><td><span class="signal '+pretty(v.proposal)+'">'+esc(v.proposal)+'</span></td><td><span class="val-down">'+esc(risk.status||"BLOCKED")+'</span></td><td>'+esc(v.reason)+'</td></tr>';
  }).join("")||'<tr><td colspan="9">Scanner output unavailable or unverified.</td></tr>';
}
"""
j=change_once(j,'async function refreshOverview(){',j_add+'\nasync function refreshOverview(){')
j=j.replace('text("refreshLabel",alive?"LIVE FEED":"FEED STALE");','text("refreshLabel",alive?"BROKER SNAPSHOT":"FEED STALE");')

c+='\n.account-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:20px}.account-strip .metric{background:#0e2433;border-color:#22485b}.account-strip .metric strong{font-size:25px}.risk-numbers{flex-wrap:wrap}.risk-numbers>div{min-width:130px}.risk-numbers strong{font-size:22px!important}@media(max-width:1150px){.account-strip{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.account-strip{grid-template-columns:repeat(2,1fr);gap:10px}}\n'

# Check all newly referenced ID tokens appear exactly once in the HTML.
for name in ("homeBalance","homeEquity","homeRiskLock","accountBalance",
    "accountPositions","accountDeals","scanSymbols","scanCandidates",
    "scannerBody","governorHeadroom","governorKill"):
    assert h.count('id="'+name+'"')==1,name
for path,data in ((html,h),(js,j),(css,c)):
    path.write_text(data)
print("APEX account/scanner/risk screen patch completed")
