/* Authenticated client FP Markets scanner presentation. No trade mutations. */
(() => {
 "use strict";
 const portal=document.getElementById("portalSection");
 const accountApi="/account/api/client/fp-market";
 if(!portal)return;
 const $=id=>document.getElementById(id);
 const mk=(tag,className,t)=>{const x=document.createElement(tag);if(className)x.className=className;if(t!==undefined)x.textContent=String(t);return x;};
 const number=(n,max=4)=>typeof n==="number"&&Number.isFinite(n)?n.toLocaleString("en-US",{maximumFractionDigits:max}):"—";
 const fmt=t=>{const d=new Date(t);return Number.isFinite(d.getTime())?d.toLocaleString("en-GB",{timeZone:"Africa/Johannesburg",dateStyle:"short",timeStyle:"short"})+" SAST":"—";};
 const spaces=["dashboard","trading","accounts","trades"];
 const sections={};
 for(const name of spaces){
  const v=$("apex-view-"+name);if(!v)continue;
  const s=mk("section","apex-fp-panel");s.id="abutron-fp-"+name;
  const header=mk("div","apex-fp-heading");
  header.append(mk("h2","",name==="trades"?"FP Markets · Broker Trade History":
    name==="trading"?"FP Markets · Strategy Scanner":
    name==="accounts"?"FP Markets · Native Symbol Coverage":"FP Markets · Live Market Intelligence"));
  header.append(mk("span","apex-fp-status","DEMO · READ-ONLY"));
  s.append(header);
  v.append(s);sections[name]=s;
 }
 if(!sections.dashboard)return;
 const table=(columns,parent)=>{
  const wrap=mk("div","apex-fp-overflow"),tab=mk("table","apex-fp-table"),th=mk("thead"),tr=mk("tr");
  for(const h of columns)tr.append(mk("th","",h));
  th.append(tr);
  const body=mk("tbody");tab.append(th,body);wrap.append(tab);parent.append(wrap);
  return body;
 };
 const msg={};const bodies={};
 const summary=mk("div","apex-fp-stats");sections.dashboard.append(summary);
 msg.dashboard=mk("p","apex-fp-subtle","FP Markets feed checks will appear after sign-in.");sections.dashboard.append(msg.dashboard);
 const dashBody=table(["Symbol","Bid","Ask","M5","APEX","AI","M5 Body","Final","Entry Reason"],sections.dashboard);
 msg.trading=mk("p","apex-fp-subtle","M5 entry screening requires M15/H1/H4 alignment, a quality-confirmed closed candle and independent TradingAgents agreement. Research does not send orders.");
 sections.trading.append(msg.trading);
 bodies.trading=table(["Symbol","M5","Higher TF","RSI14","Proposal","AI","M5 Candle","Final","Entry Reason"],sections.trading);
 const ctrls=mk("div","apex-fp-controls");
 const symbol=mk("select"),frame=mk("select");
 symbol.setAttribute("aria-label","FP Markets broker symbol");
 frame.setAttribute("aria-label","FP Markets completed-candle timeframe");
 ["M1","M5","M15","H1","H4","D1"].forEach(tf=>{const o=mk("option","",tf);o.value=tf;frame.append(o)});
 const label=mk("label","","Symbol");const label2=mk("label","","Timeframe");
 ctrls.append(label,symbol,label2,frame);sections.trading.append(ctrls);
 const chart=mk("canvas","apex-fp-chart");chart.setAttribute("role","img");chart.setAttribute("aria-label","FP Markets broker-native completed candles");
 sections.trading.append(chart);
 msg.chart=mk("p","apex-fp-subtle","Completed native broker candles, not an executable trading signal.");
 sections.trading.append(msg.chart);
 msg.accounts=mk("p","apex-fp-subtle","Connect your own FP Markets DEMO account to view account-scoped data.");
 sections.accounts.append(msg.accounts);
 bodies.accounts=table(["Canonical symbol","Broker MT5 symbol","Quote age","Last closed M5","Research decision"],sections.accounts);
 msg.trades=mk("p","apex-fp-subtle","Real FP Markets broker trade history is not connected to this view. No open positions, fills or P&L are inferred from signals.");
 sections.trades.append(msg.trades);
 const state={data:null,chosen:"EURUSD",tf:"M5",busy:false};
 function cells(body,values){
  const row=mk("tr");
  values.forEach(v=>{const td=mk("td","",v??"—");row.append(td)});
  body.append(row);
 }
 function countRows(body,cols,values){
  body.replaceChildren();
  for(const row of values)cells(body,cols(row));
  if(!values.length)cells(body,["No verified FP Markets symbols available"]);
 }
 function draw(){
  const d=state.data;
  if(!d?.available)return;
  const bars=d.candles?.[state.chosen]?.[state.tf]||[];
  if(!Array.isArray(bars)||bars.length<50){msg.chart.textContent="Authenticated broker candles unavailable";return;}
  const width=Math.max(280,Math.floor(chart.clientWidth||680)),height=250;
  const scale=Math.min(window.devicePixelRatio||1,2);
  chart.width=Math.round(width*scale);chart.height=height*scale;
  const ctx=chart.getContext("2d");if(!ctx)return;
  ctx.scale(scale,scale);ctx.fillStyle="#0c1c2e";ctx.fillRect(0,0,width,height);
  const low=Math.min(...bars.map(x=>x[3])),high=Math.max(...bars.map(x=>x[2]));
  const span=Math.max(high-low,.000001);
  const map=v=>220-(v-low)/span*190;
  ctx.strokeStyle="#29455b";ctx.lineWidth=1;
  for(let i=0;i<4;i++){let y=15+i*60;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
  const unit=(width-24)/bars.length;
  for(let i=0;i<bars.length;i++){
   const b=bars[i],x=12+unit*(i+.5);ctx.fillStyle=ctx.strokeStyle=b[4]>=b[1]?"#32d7a4":"#ff8079";
   ctx.beginPath();ctx.moveTo(x,map(b[2]));ctx.lineTo(x,map(b[3]));ctx.stroke();
   const top=map(Math.max(b[1],b[4])),bot=map(Math.min(b[1],b[4]));
   ctx.fillRect(x-Math.max(1,unit*.25),top,Math.max(2,unit*.5),Math.max(1,bot-top));
  }
  ctx.fillStyle="#d7e5ef";ctx.font="12px system-ui";ctx.fillText(number(high,5),8,12);ctx.fillText(number(low,5),8,244);
  msg.chart.textContent=state.chosen+" · "+state.tf+" · "+bars.length+" broker-native completed candles · "+fmt(d.generated_at_utc)+". Research only.";
 }
 function error(message){
  state.data=null;summary.replaceChildren();
  summary.append(mk("p","apex-fp-subtle",message));
  msg.dashboard.textContent=message;
  msg.trading.textContent="FP Markets source unavailable · no trading signal inferred.";
  msg.accounts.textContent=message;
  for(const b of [dashBody,bodies.trading,bodies.accounts])countRows(b,()=>[],[]);
  const c=chart.getContext("2d");c?.clearRect(0,0,chart.width,chart.height);
 }
 function render(d){
  if(d?.available!==true){
   const unavailable=d?.reason==="NO_CONNECTED_FP_DEMO_ACCOUNT"?
     "No connected FP Markets DEMO account under this client login.":
     "FP Markets broker-native data temporarily unavailable or stale.";
   error(unavailable);return;
  }
  state.data=d;
  summary.replaceChildren();
  const items=[["Native quotes",d.fresh_quotes+"/13"],["Completed TF",d.timeframe_series+"/78"],
    ["Scanner setups",d.scanner_proposals],["Qwen matches",d.ai_agreements],
    ["TradingAgents approvals",d.tradingagents_ai_agreements],["FP auto trading",d.trading_controls?.effective_enabled?"ON":"OFF"]];
  for(const [t,v] of items){
   const box=mk("div","apex-fp-stat");
   box.append(mk("span","",t),mk("strong","",v));summary.append(box);
  }
  msg.dashboard.textContent="FP Markets DEMO "+d.account_masked+" · "+d.broker_server+
    " · native feed "+fmt(d.native_feed_at_utc)+" · native order execution requires separate broker risk approval.";
  const rows=d.symbols;
  countRows(dashBody,r=>[r.symbol,number(r.bid,6),number(r.ask,6),number(r.m5_last_close,6),
    r.proposal,r.ai_status,r.m5_candle_body,r.final_decision,r.scanner_reason],rows);
  countRows(bodies.trading,r=>[r.symbol,r.m5_direction,r.higher_timeframe_direction,
    number(r.rsi14,2),r.proposal,r.ai_status,r.m5_candle_body,r.final_decision,
    r.scanner_reason],rows);
  msg.trading.textContent="Broker-native FP Markets DEMO "+d.account_masked+
   " · Last scanner "+fmt(d.scanner_at_utc)+" · Qwen "+fmt(d.ai_review_at_utc)+
   ". No trade order, position or profit is implied by a preliminary signal.";
  countRows(bodies.accounts,r=>[r.symbol,r.broker_symbol,
     number(r.quote_age_seconds,0)+" s",fmt(r.m5_close_utc),r.final_decision],rows);
  msg.accounts.textContent="All 13 broker symbols · M1, M5, M15, H1, H4, D1 · connected account "+d.account_masked+
    ". Historical quote data is separate from broker trade history.";
  msg.trades.textContent=d.trade_history_notice;
  if(!rows.some(x=>x.symbol===state.chosen))state.chosen=rows[0].symbol;
  symbol.replaceChildren();
  for(const row of rows){const opt=mk("option","",row.symbol+" · "+row.broker_symbol);opt.value=row.symbol;symbol.append(opt)}
  symbol.value=state.chosen;frame.value=state.tf;
  draw();
 }
 async function refresh(){
  if(portal.hidden||state.busy||document.hidden)return;
  state.busy=true;
  try{
   const r=await fetch(accountApi,{cache:"no-store",credentials:"same-origin"});
   if(r.status===401){error("Sign in to view your connected FP Markets account.");return;}
   const doc=await r.json();
   render(r.ok?doc:{available:false,reason:"FP_UI_NOT_AVAILABLE"});
  }catch(_){error("FP Markets view cannot reach authenticated broker data.");}
  finally{state.busy=false;}
 }
 symbol.addEventListener("change",()=>{state.chosen=symbol.value;draw()});
 frame.addEventListener("change",()=>{state.tf=frame.value;draw()});
 window.addEventListener("resize",()=>{if(state.data?.available)draw()});
 new MutationObserver(()=>{if(!portal.hidden)void refresh();else error("Sign in to view your FP Markets account.")}).observe(portal,{attributes:true,attributeFilter:["hidden"]});
 if(!portal.hidden)void refresh();
 setInterval(()=>void refresh(),60000);
})();
