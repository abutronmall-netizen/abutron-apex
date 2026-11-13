/* ABUTRON FP Markets native account history: authenticated read-only client view. */
(() => {
 "use strict";
 const portal=document.getElementById("portalSection");
 const views={dashboard:document.getElementById("apex-view-dashboard"),
  accounts:document.getElementById("apex-view-accounts"),
  trades:document.getElementById("apex-view-trades")};
 if(!portal||!views.trades)return;
 const el=(tag,cls,value)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(value!==undefined)node.textContent=String(value);return node;};
 const usd=x=>typeof x==="number"&&Number.isFinite(x)?"$"+x.toFixed(2):"UNVERIFIED";
 const tm=s=>{const x=new Date(s);return Number.isFinite(x.getTime())?
   x.toLocaleString("en-ZA",{timeZone:"Africa/Johannesburg",dateStyle:"short",timeStyle:"short"})+" SAST":"—"};
 function panel(where,label){
  const box=el("section","apex-fp-panel apex-fp-history");
  box.append(el("h2","",label),el("p","apex-fp-subtle","Awaiting authenticated FP broker history"));
  where?.append(box);return box;
 }
 const trades=panel(views.trades,"FP Markets · Broker positions and trades");
 const accounts=views.accounts?panel(views.accounts,"FP Markets · Native account balance and equity"):null;
 const dashboard=views.dashboard?panel(views.dashboard,"FP Markets · Broker P&L snapshot"):null;
 const table=(where,headers)=>{
  const wrap=el("div","apex-fp-overflow"),tab=el("table","apex-fp-table"),thead=el("thead"),tr=el("tr");
  for(const h of headers)tr.append(el("th","",h));
  thead.append(tr);const body=el("tbody");tab.append(thead,body);wrap.append(tab);where.append(wrap);return body;
 };
 const summary=el("div","apex-fp-stats");trades.append(summary);
 const search=el("input","apex-fp-history-search");
 search.type="search";search.placeholder="Search FP deal by symbol, ticket or side";
 search.setAttribute("aria-label","Search FP Markets deal history");trades.append(search);
 trades.append(el("h3","","Open MT5 positions"));
 const positions=table(trades,["Ticket","Opened SAST","Symbol","Side","Volume","Entry","Current","SL","TP","Floating USD","Swap USD"]);
 trades.append(el("h3","","Pending MT5 orders"));
 const pending=table(trades,["Ticket","Created SAST","Symbol","Type","State","Lots","Order price","SL","TP"]);
 trades.append(el("h3","","MT5 trade deals · last 90 days"));
 const deals=table(trades,["Deal","Time SAST","Symbol","Side","Entry","Volume","Price","Profit USD","Commission","Swap","Fee","Deal cashflow USD"]);
 let current=null;
 function row(body,fields){const tr=el("tr");for(const f of fields)tr.append(el("td","",f??"—"));body.append(tr);}
 function notes(where,value){const p=where?.querySelector(".apex-fp-subtle");if(p)p.textContent=value;}
 function fill(body,items,shape,empty){body.replaceChildren();if(!items.length)row(body,[empty]);else items.forEach(x=>row(body,shape(x)));}
 function boxes(where,pairs){if(!where)return;where.querySelectorAll(".apex-fp-stat").forEach(x=>x.remove());
  for(const [k,v] of pairs){const block=el("div","apex-fp-stat");block.append(el("span","",k),el("strong","",v));where.append(block);}
 }
 function dealsRender(){
  const data=current?.trade_deals||[],q=search.value.trim().toLowerCase();
  const filtered=q?data.filter(x=>(x.symbol+" "+x.ticket+" "+x.side).toLowerCase().includes(q)):data;
  fill(deals,filtered,x=>[x.ticket,tm(x.time_utc),x.symbol,x.side,x.entry,x.volume,
   x.price,usd(x.profit_usd),usd(x.commission_usd),usd(x.swap_usd),usd(x.fee_usd),usd(x.net_cashflow_usd)],
   current?"Broker confirms no matching trade deals in this 90-day window":"No verified broker deal records");
 }
 function unavailable(reason){current=null;search.hidden=true;summary.replaceChildren();
  notes(trades,reason);notes(accounts,reason);notes(dashboard,reason);
  fill(positions,[],()=>[],"Broker-native positions unavailable");
  fill(pending,[],()=>[],"Broker-native pending orders unavailable");
  dealsRender();
  boxes(accounts,[["Open positions","UNVERIFIED"],["Balance","UNVERIFIED"]]);
  boxes(dashboard,[["Broker floating P&L","UNVERIFIED"]]);
 }
 function render(d){
  if(d?.available!==true||d?.history_verified_from_mt5!==true){
   unavailable(d?.reason==="NO_CONNECTED_FP_DEMO_ACCOUNT"?
    "No connected FP Markets DEMO account for this user.":
    "FP Markets native position/deal export not verified. No assumed zero trades, fills or USD profit.");
   return;
  }
  current=d;search.hidden=false;
  const totals=[["Broker DEMO",d.account_masked],["Balance",usd(d.balance_usd)],
   ["Equity",usd(d.equity_usd)],["Floating P&L",usd(d.account_floating_profit_usd)],
   ["Open positions",d.open_positions_count],["Pending orders",d.pending_orders_count],
   ["Trade deals · 90d",d.trade_deals_count],["Closing deal cashflow",usd(d.closing_deal_cashflow_usd)]];
  summary.replaceChildren();boxes(summary,totals);boxes(accounts,totals.slice(0,6));boxes(dashboard,totals.slice(0,4));
  const why="Broker-native FP Markets MT5 "+d.account_masked+" · "+tm(d.broker_export_at_utc)+
   " · "+d.history_trade_deals_shown+" of "+d.trade_deals_count+" trade deals displayed (last 90 days). "+
   "Cashflows are broker deal amounts, not estimated strategy returns.";
  notes(trades,why);notes(accounts,why);notes(dashboard,why);
  fill(positions,d.positions||[],p=>[p.ticket,tm(p.opened_at_utc),p.symbol,p.side,p.volume,p.open_price,
    p.current_price,p.stop_loss??"—",p.take_profit??"—",usd(p.floating_profit_usd),usd(p.swap_usd)],
    "MT5 confirms zero current open positions");
  fill(pending,d.pending_orders||[],p=>[p.ticket,tm(p.created_at_utc),p.symbol,p.order_type_code,
    p.state_code,p.remaining_volume,p.order_price,p.stop_loss??"—",p.take_profit??"—"],
    "MT5 confirms zero current pending orders");
  dealsRender();
  const old=views.trades.querySelector(".apex-placeholder");if(old)old.hidden=true;
  const oldFp=document.querySelector("#abutron-fp-trades .apex-fp-subtle");
  if(oldFp)oldFp.textContent="Native account positions and deals are verified in the section below.";
 }
 let fetching=false;
 async function refresh(){
  if(portal.hidden||document.hidden||fetching)return;fetching=true;
  try{
   const r=await fetch("/account/api/client/fp-native-history",{credentials:"same-origin",cache:"no-store"});
   if(r.status===401){unavailable("Sign in to view your own FP broker history.");return;}
   const d=await r.json();
   render(r.ok?d:{available:false,reason:"FP_HISTORY_UNAVAILABLE"});
  }catch(_){unavailable("FP broker history temporarily unavailable. No cached trades are displayed.");}
  finally{fetching=false;}
 }
 search.addEventListener("input",dealsRender);
 new MutationObserver(()=>{if(!portal.hidden)void refresh();else unavailable("Sign in to view your account.")}).observe(portal,{attributes:true,attributeFilter:["hidden"]});
 if(!portal.hidden)void refresh();
 setInterval(()=>void refresh(),60000);
})();
