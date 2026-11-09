/* MFA-only broker-native FP account history: independently scoped summaries. */
(() => {
"use strict";
const tab=document.getElementById("tab-brokers");
if(!tab)return;
const el=(tag,txt)=>{const x=document.createElement(tag);if(txt!==undefined)x.textContent=String(txt);return x;};
const panel=el("section");panel.className="panel apex-fp-admin";
const h=el("h2","FP Markets · verified native positions and deal history");
const note=el("p","Superadmin email-MFA required. Unverified accounts are never shown as zero.");
const stats=el("div");stats.className="apex-fp-stats";
panel.append(h,note,stats);tab.append(panel);
const usd=v=>typeof v==="number"&&Number.isFinite(v)?"$"+v.toFixed(2):"UNVERIFIED";
const put=(name,value)=>{const c=el("div");c.className="apex-fp-stat";
c.append(el("span",name),el("strong",value));stats.append(c);};
async function refresh(){
 if(document.hidden||tab.hidden)return;
 try{
  const response=await fetch("/account/api/client/admin/fp-native-history",
    {credentials:"same-origin",cache:"no-store"});
  if(response.status===401||response.status===403){
    note.textContent="Superadmin email verification required.";stats.replaceChildren();return;
  }
  if(!response.ok)throw Error("Broker history endpoint unavailable");
  const d=await response.json();
  stats.replaceChildren();
  if(!Array.isArray(d.accounts)||d.accounts.length<1){
    note.textContent="No independently verified FP Markets broker history.";return;
  }
  note.textContent=d.account_count+" connected FP DEMO accounts · "+
     (d.all_accounts_history_verified?"native history verified per account":"some account histories unavailable")+
     " · 90-day broker deals, not modeled strategy returns.";
  for(const a of d.accounts){
    const label="FP "+a.account_masked+" · ";
    if(a.available!==true){
      put(label+"History","UNVERIFIED");continue;
    }
    put(label+"Balance",usd(a.balance_usd));
    put(label+"Equity",usd(a.equity_usd));
    put(label+"Open positions",a.open_positions_count);
    put(label+"Pending orders",a.pending_orders_count);
    put(label+"Trade deals / 90d",a.trade_deals_count);
    put(label+"Closing cashflow",usd(a.closing_deal_cashflow_usd));
  }
 }catch(_){note.textContent="FP native history temporarily unavailable.";stats.replaceChildren();}
}
new MutationObserver(()=>{if(!tab.hidden)void refresh()})
 .observe(tab,{attributes:true,attributeFilter:["hidden"]});
setInterval(()=>{if(!tab.hidden)void refresh()},60000);
if(!tab.hidden)void refresh();
})();