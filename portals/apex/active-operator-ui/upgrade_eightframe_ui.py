"""Upgrade APEX UI to distinguish single-candle bias from EMA/RSI trend."""
from pathlib import Path
from datetime import datetime,timezone

root=Path("/opt/apex/runtime/apex_ui/static")
hpath=root/"index.html"
jpath=root/"app.js"
cpath=root/"style.css"
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for p in (hpath,jpath,cpath):(root/(p.name+".backup-candle-compare-"+stamp)).write_text(p.read_text())
h=hpath.read_text();j=jpath.read_text();c=cpath.read_text()

def edit(src,old,new):
    n=src.count(old)
    if n!=1:raise RuntimeError("Unexpected source "+old[:100]+" count="+str(n))
    return src.replace(old,new,1)

h=edit(h,
'<button class="navitem" data-view="scanner"><span>◈</span> Strategy Scanner</button>',
'<button class="navitem" data-view="scanner"><span>◈</span> Strategy Scanner</button>\n'
'    <button class="navitem" data-view="compare"><span>◷</span> Candle Comparison <small>8 TF</small></button>')
h=edit(h,
'<th>Family</th><th>M1</th><th>M5</th><th>M5 Signal</th><th>M15</th>',
'<th>Family</th><th>M1 EMA</th><th>M5 candle</th><th>M5 EMA trend</th><th>M5 EMA/RSI direction</th><th>M15 EMA</th>')
h=edit(h,'<th>H1</th><th>H4</th><th>D1</th><th>RSI M5</th><th>MTF Proposal</th>',
'<th>H1 EMA</th><th>H4 EMA</th><th>D1 EMA</th><th>RSI M5</th><th>Strategy Gate</th>')
h=edit(h,
'<p class="table-foot">M5 is the primary research direction. M5 Signal is not a trade authorization. MTF Proposal applies higher-timeframe, RSI and instrument-family filters. Experimental EMA/RSI logic using completed Deriv candles.',
'<p class="table-foot">**M5 candle** = direction of one completed candle (last-completed-candle method). **M5 EMA trend** = multi-candle EMA/RSI direction. **Strategy Gate** = additional entry rules. These are three different calculations, not interchangeable BUY/SELL signals. Experimental EMA/RSI logic using completed Deriv candles.')
h=edit(h,
'<h2>All 13 Deriv strategy proposals</h2></div><span class="chip">ORIGINAL BROKER CANDLES</span>',
'<h2>All 13 Deriv strategy proposals</h2></div><button class="textbutton" data-jump="compare">Compare closed candles ›</button>')

compare='''<section id="compare" class="view">
  <article class="panel" style="margin-bottom:18px">
    <div class="panel-head"><div><p class="panel-kicker">DERIV DEMO MT5 · 8 VERIFIED TIMEFRAMES</p><h2>Closed candle direction versus multi-candle trend</h2></div><select id="comparisonSymbol" aria-label="Select instrument for candle comparison"></select></div>
    <p class="muted" style="margin-top:-4px">APEX independently calculates single-candle close-versus-open direction using only the connected Deriv USD DEMO MT5 feed. No external trading platform is required.</p>
    <div class="account-strip comparison-strip">
      <article class="metric"><span>Last completed M5 candle</span><strong id="comparisonM5Bias">—</strong><small id="comparisonM5Time">Waiting for candles</small></article>
      <article class="metric"><span>M5 multi-candle EMA/RSI trend</span><strong id="comparisonM5Trend">—</strong><small>Calculated from 9/21 EMA and RSI</small></article>
      <article class="metric"><span>Candle source / status</span><strong id="comparisonSource">—</strong><small id="comparisonFreshness">Checking independent MT5 source</small></article>
    </div>
    <div class="notice"><span class="notice-icon">◈</span><div><b>Why BUY and SELL can both be visible</b><span>A BUY candle means its close was above its open. A DOWN trend means the longer EMA/RSI history remains bearish. One bullish candle does not reverse a multi-candle trend.</span></div></div>
    <div class="table-scroll"><table><thead><tr><th>Timeframe</th><th>Last closed candle</th><th>EMA/RSI trend</th><th>Open</th><th>Close</th><th>Closed at (UTC)</th><th>Time since close</th></tr></thead><tbody id="comparisonRows"><tr><td colspan="7">Loading verified broker candles…</td></tr></tbody></table></div>
    <p class="table-foot">All timestamps are actual candle closing times, not opening times. M3/M30 EMA/RSI trend is marked unavailable because the supplemental feed currently provides only completed-candle observations, not enough bars for an EMA21 history. No execution signal is implied.</p>
  </article>
</section>

'''
h=edit(h,'<section id="account" class="view">',compare+'<section id="account" class="view">')

j=edit(j,
'const ui = { overview: null, symbol: "", frame: "M5", chart: [], busy: false, view: "overview", symbolInitialized: false };',
'const ui = { overview: null, symbol: "", compareSymbol:"", frame: "M5", chart: [], busy: false, view: "overview", symbolInitialized: false };')
j=edit(j,
'const views=["overview","markets","signals","scanner","account","execution","systems"];',
'const views=["overview","markets","signals","scanner","compare","account","execution","systems"];')
j=edit(j,
'scanner:"Strategy Scanner",account:"Account & Trades",',
'scanner:"Strategy Scanner",compare:"Candle Comparison",account:"Account & Trades",')
j=edit(j,
'scanner:"13-symbol multi-timeframe scanner and independent risk approval checks.",account:',
'scanner:"13-symbol multi-timeframe scanner and independent risk approval checks.",compare:"Eight completed broker candle periods, with candle bias separate from EMA/RSI trend.",account:')
old="""return '<tr><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.family)+'</td><td>'+badgeTrend(v.m1_trend)+'</td><td>'+badgeTrend(v.m5_trend)+'</td><td><span class="signal '+pretty(v.m5_signal)+'">'+esc(v.m5_signal||"HOLD")+'</span></td><td>'+badgeTrend(v.m15_trend)+'</td><td>'+badgeTrend(v.h1_trend)+'</td><td>'+badgeTrend(v.h4_trend)+'</td><td>'+badgeTrend(v.d1_trend)+'</td><td>'+esc(number(v.m5_rsi))+'</td><td><span class="signal '+pretty(v.proposal)+'">'+esc(v.proposal)+'</span></td><td><span class="val-down">'+esc(risk.status||"BLOCKED")+'</span></td><td>'+esc(v.reason)+'</td></tr>';"""
new="""return '<tr class="selectable" data-compare-symbol="'+esc(v.symbol)+'"><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.family)+'</td><td>'+badgeTrend(v.m1_trend)+'</td><td><span class="signal '+pretty(v.m5_candle_bias)+'">'+esc(v.m5_candle_bias||"UNAVAILABLE")+'</span></td><td>'+badgeTrend(v.m5_trend)+'</td><td><span class="signal '+pretty(v.m5_signal)+'">'+esc(v.m5_signal||"HOLD")+'</span></td><td>'+badgeTrend(v.m15_trend)+'</td><td>'+badgeTrend(v.h1_trend)+'</td><td>'+badgeTrend(v.h4_trend)+'</td><td>'+badgeTrend(v.d1_trend)+'</td><td>'+esc(number(v.m5_rsi))+'</td><td><span class="signal '+pretty(v.proposal)+'">'+esc(v.proposal)+'</span></td><td><span class="val-down">'+esc(risk.status||"BLOCKED")+'</span></td><td>'+esc(v.reason)+'</td></tr>';"""
j=edit(j,old,new)
j=edit(j,'<tr><td colspan="13">Scanner output unavailable or unverified.</td></tr>',
'<tr><td colspan="14">Scanner output unavailable or unverified.</td></tr>')
j=edit(j,
'  }).join("")||\'<tr><td colspan="14">Scanner output unavailable or unverified.</td></tr>\';',
'''  }).join("")||'<tr><td colspan="14">Scanner output unavailable or unverified.</td></tr>';
  $("scannerBody").querySelectorAll("tr[data-compare-symbol]").forEach((row)=>row.addEventListener("click",()=>{
    ui.compareSymbol=row.dataset.compareSymbol;
    changeUI("compare");
    syncComparisonSelector(ui.overview);
    loadComparison();
  }));''')
additional="""
function syncComparisonSelector(d){
  const list=d?.market?.instruments||[];
  const select=$("comparisonSymbol");
  const existing=ui.compareSymbol;
  select.replaceChildren(...list.map(x=>{
    const opt=document.createElement("option");
    opt.value=x.name;opt.textContent=x.name;return opt;
  }));
  if(!list.some(x=>x.name===existing)){
    ui.compareSymbol=list.find(x=>x.name==="Volatility 75 Index.0")?.name || list[0]?.name || "";
  }
  select.value=ui.compareSymbol;
}
async function loadComparison(){
  if(!ui.compareSymbol)return;
  const chosen=ui.compareSymbol;
  try{
    const data=await getJson("candle-comparison?symbol="+encodeURIComponent(chosen));
    if(chosen!==ui.compareSymbol)return;
    if(!data.rows||data.rows.length!==8||data.orders_enabled!==false)throw Error("Invalid broker comparison");
    const m5=data.rows.find(x=>x.timeframe==="M5");
    text("comparisonM5Bias",m5?.candle_bias||"—");
    text("comparisonM5Trend",m5?.ema_rsi_trend||"—");
    text("comparisonM5Time",m5?.candle_closed_utc?
      "Closed "+new Date(m5.candle_closed_utc).toISOString().slice(0,19).replace("T"," ")+" UTC":"Unavailable");
    text("comparisonSource","MT5 DEMO");
    text("comparisonFreshness","Last broker snapshots "+age(Math.max(data.main_snapshot_age_seconds,data.extra_snapshot_age_seconds)));
    $("comparisonRows").innerHTML=data.rows.map(x=>
      '<tr><td class="symboltext">'+esc(x.timeframe)+'</td>'+
      '<td><span class="signal '+pretty(x.candle_bias)+'">'+esc(x.candle_bias)+'</span></td>'+
      '<td>'+badgeTrend(x.ema_rsi_trend)+'</td>'+
      '<td>'+esc(number(x.open))+'</td><td>'+esc(number(x.close))+'</td>'+
      '<td>'+esc(new Date(x.candle_closed_utc).toISOString().slice(0,19).replace("T"," "))+'</td>'+
      '<td>'+esc(age(x.closed_age_seconds))+'</td></tr>'
    ).join("");
  }catch(err){
    text("comparisonSource","UNAVAILABLE");
    text("comparisonFreshness","Broker data stale or not verified");
    text("comparisonM5Bias","—");
    text("comparisonM5Trend","—");
    text("comparisonM5Time","No verified M5 candle");
    $("comparisonRows").innerHTML='<tr><td colspan="7">Broker candle comparison unavailable: '+esc(err.message)+'</td></tr>';
  }
}
"""
j=edit(j,'async function refreshOverview(){',additional+'\nasync function refreshOverview(){')
j=edit(j,'    renderScanner(d);\n    renderExecution(d);','    renderScanner(d);\n    renderExecution(d);\n    syncComparisonSelector(d);\n    if(ui.view==="compare")loadComparison();')
j=edit(j,'$("symbolSelect").addEventListener("change",(e)=>{ui.symbol=e.target.value;loadChart();});',
'''$("symbolSelect").addEventListener("change",(e)=>{ui.symbol=e.target.value;loadChart();});
$("comparisonSymbol").addEventListener("change",(e)=>{ui.compareSymbol=e.target.value;loadComparison();});''')
j=edit(j,'setInterval(()=>{if(ui.view==="overview")loadChart();},60000);',
'''setInterval(()=>{if(ui.view==="overview")loadChart();},60000);
setInterval(()=>{if(ui.view==="compare")loadComparison();},60000);''')

c+='\n.comparison-strip{grid-template-columns:repeat(3,minmax(0,1fr))!important}.comparison-strip .metric{background:#112637;border-color:#265b70}.comparison-strip .metric strong{font-size:24px!important}.comparison-strip .metric small{line-height:1.5}@media(max-width:720px){.comparison-strip{grid-template-columns:1fr!important}}\n'
for key in ("comparisonRows","comparisonSymbol","comparisonM5Bias","comparisonM5Trend","comparisonM5Time"):
    assert h.count('id="'+key+'"')==1,key
hpath.write_text(h);jpath.write_text(j);cpath.write_text(c)
print('APEX eight-period comparison interface installed with independent M5 candle/EMA labels')
