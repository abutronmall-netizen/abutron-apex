/* APEX operator FP Markets native positions and trade deals · protected read-only. */
(() => {
 "use strict";
 const targets={overview:document.getElementById("overview"),account:document.getElementById("account"),
  systems:document.getElementById("systems")};
 if(!targets.account)return;
 const node=(tag,cls,value)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(value!==undefined)x.textContent=String(value);return x;};
 const money=v=>typeof v==="number"&&Number.isFinite(v)?"$"+v.toFixed(2):"UNVERIFIED";
 const fmt=v=>{const d=new Date(v);return Number.isFinite(d.getTime())?
   d.toLocaleString("en-ZA",{timeZone:"Africa/Johannesburg",dateStyle:"short",timeStyle:"short"})+" SAST":"—"};
 function panel(root,label){
  if(!root)return null;
  const x=node("article","panel fp-panel");
  const h=node("div","panel-head");
  h.append(node("h2","",label),node("span","fp-tag","BROKER-NATIVE · DEMO"));
  x.append(h,node("p","fp-muted","Verifying native FP Markets MT5 account history…"));
  root.append(x);return x;
 }
 const sections={overview:panel(targets.overview,"FP Markets broker balance, equity and P&L"),
  account:panel(targets.account,"FP Markets · Broker-native positions and deal history"),
  systems:panel(targets.systems,"FP Markets native-history exporter evidence")};
 const table=(parent,headers)=>{
  const wrap=node("div","table-scroll fp-scroll");
  const t=node("table","fp-table"),hd=node("thead"),tr=node("tr");
  for(const h of headers)tr.append(node("th","",h));
  hd.append(tr);const body=node("tbody");t.append(hd,body);wrap.append(t);parent.append(wrap);return body;
 };
 const statBox=(where,pairs)=>{
  if(!where)return;
  where.querySelectorAll(".fp-stat").forEach(x=>x.remove());
  const grid=node("div","fp-account");
  for(const [label,value] of pairs){const tile=node("div","fp-stat");tile.append(node("span","",label),node("strong","",value));grid.append(tile)}
  where.append(grid);
 };
 const act=sections.account;
 act.append(node("h3","","Actual MT5 open positions"));
 const positions=table(act,["Ticket","Opened SAST","Symbol","Side","Lots","Entry","Current","Stop","Target","Floating USD","Swap USD"]);
 act.append(node("h3","","Actual MT5 trade deals · 90 days"));
 const deals=table(act,["Deal","SAST","Symbol","Side","IN / OUT","Volume","Price","Profit USD","Commission USD","Swap USD","Fee USD","Net cashflow USD"]);
 const pendingTitle=node("h3","","Pending broker orders");act.append(pendingTitle);
 const orders=table(act,["Ticket","Symbol","Type","State","Remaining lots","Price","Stop","Target"]);
 function line(body,fields){const tr=node("tr");for(const cell of fields)tr.append(node("td","",cell??"—"));body.append(tr);}
 function rows(body,items,extract,empty){body.replaceChildren();if(!items.length)line(body,[empty]);else items.forEach(x=>line(body,extract(x)));}
 function note(section,value){if(section)section.querySelector(".fp-muted").textContent=value;}
 function unavailable(textValue){
  for(const x of Object.values(sections))note(x,textValue);
  statBox(sections.overview,[["FP native positions","UNVERIFIED"],["FP USD P&L","UNVERIFIED"]]);
  statBox(sections.systems,[["Native historical export","NOT VERIFIED"]]);
  rows(positions,[],()=>[],"No verified FP position snapshot");
  rows(orders,[],()=>[],"No verified FP pending-order snapshot");
  rows(deals,[],()=>[],"No verified FP deal history");
 }
 function render(d){
  if(d?.available!==true||d?.history_verified_from_mt5!==true){
   unavailable("The FP Markets MT5 native account history has not produced a verified snapshot. No positions or profits are inferred.");
   return;
  }
  const totals=[["FP account",d.account_masked],["Balance USD",money(d.balance_usd)],
    ["Equity USD",money(d.equity_usd)],["Broker floating P&L",money(d.account_floating_profit_usd)],
    ["Open positions",d.open_positions_count],["Pending orders",d.pending_orders_count],
    ["90d trade deals",d.trade_deals_count],["Closing deal cashflow",money(d.closing_deal_cashflow_usd)]];
  for(const x of [sections.overview,sections.account])statBox(x,totals);
  statBox(sections.systems,[["MQL5 HistorySelect","VERIFIED"],["Snapshot",fmt(d.broker_export_at_utc)],
    ["Broker trade deals",d.trade_deals_count],["FP order execution","OFF"]]);
  const msg="FP Markets DEMO "+d.account_masked+" · "+fmt(d.broker_export_at_utc)+
     " · "+d.history_trade_deals_shown+" newest trade deals of "+d.trade_deals_count+
     " from the last 90 days. Entry/exit are distinct MT5 deals; not backtest trades.";
  for(const x of Object.values(sections))note(x,msg);
  rows(positions,d.positions||[],x=>[x.ticket,fmt(x.opened_at_utc),x.symbol,x.side,
    x.volume,x.open_price,x.current_price,x.stop_loss??"—",x.take_profit??"—",
    money(x.floating_profit_usd),money(x.swap_usd)],"MT5 verified zero open positions");
  rows(orders,d.pending_orders||[],x=>[x.ticket,x.symbol,x.order_type_code,x.state_code,
    x.remaining_volume,x.order_price,x.stop_loss??"—",x.take_profit??"—"],"MT5 verified zero pending orders");
  rows(deals,d.trade_deals||[],x=>[x.ticket,fmt(x.time_utc),x.symbol,x.side,
    x.entry,x.volume,x.price,money(x.profit_usd),money(x.commission_usd),
    money(x.swap_usd),money(x.fee_usd),money(x.net_cashflow_usd)],
    "MT5 verified zero trade deals in this 90-day window");
 }
 let busy=false;
 async function refresh(){
  if(busy||document.hidden)return;busy=true;
  try{
   const r=await fetch("/apex/api/fp-native-history",{cache:"no-store",credentials:"same-origin"});
   const data=await r.json();
   render(r.ok?data:{available:false});
  }catch(_){unavailable("FP Markets native-history source temporarily unavailable.");}
  finally{busy=false;}
 }
 void refresh();
 document.getElementById("refreshNow")?.addEventListener("click",()=>void refresh());
 setInterval(()=>void refresh(),60000);
})();
