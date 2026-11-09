/* ABUTRON MFA-only FP Markets account-scoped, broker-native read-only status. */
(() => {
 "use strict";
 const broker=document.getElementById("tab-brokers");
 if(!broker)return;
 const el=(tag,cls,value)=>{const n=document.createElement(tag);
   if(cls)n.className=cls;if(value!==undefined)n.textContent=String(value);return n;};
 const section=el("section","panel apex-fp-admin");
 section.id="fp-markets-admin-market";
 const head=el("div","panel-heading");
 head.append(el("h2","","FP Markets · independent DEMO accounts"),
   el("small","","Owner-isolated, broker-native research only"));
 section.append(head);
 const stats=el("div","apex-fp-stats");section.append(stats);
 const note=el("p","apex-fp-subtle","Email-verified superadmin session required.");
 section.append(note);
 const wrap=el("div","apex-fp-overflow"),table=el("table","apex-fp-table");
 const thead=el("thead"),tr=el("tr");
 ["Account","Symbol","MT5 broker symbol","APEX","Qwen","M5 body","Higher TF","Final","Entry reason"].forEach(t=>tr.append(el("th","",t)));
 thead.append(tr);
 const body=el("tbody");table.append(thead,body);wrap.append(table);section.append(wrap);
 broker.append(section);
 const fmt=when=>{const v=new Date(when);return Number.isFinite(v.getTime())?
   v.toLocaleString("en-ZA",{timeZone:"Africa/Johannesburg"}):"—";};
 function reset(reason){stats.replaceChildren();body.replaceChildren();note.textContent=reason;}
 function stat(k,v){const card=el("div","apex-fp-stat");
  card.append(el("span","",k),el("strong","",v));stats.append(card);}
 function render(d){
  if(d?.available!==true||!Array.isArray(d.accounts)||d.accounts.length<1){
   reset("No currently verified FP Markets DEMO account-scoped research.");return;
  }
  stats.replaceChildren();body.replaceChildren();
  stat("Connected DEMO accounts",d.account_count);
  stat("Verified quotes",d.fresh_quotes+"/"+d.required_quotes);
  stat("Completed timeframe series",d.timeframe_series+"/"+d.required_timeframe_series);
  for(const a of d.accounts){
   stat("FP "+a.account_masked,a.fresh_quotes+"/13 · auto "+(a.trading_controls?.effective_enabled?"ON":"OFF"));
   for(const x of a.symbols||[]){
    const row=el("tr");
    [a.account_masked,x.symbol,x.broker_symbol,x.proposal,x.ai_status,
     x.m5_candle_body,x.higher_timeframe_direction,x.final_decision,
     x.scanner_reason].forEach(y=>row.append(el("td","",y??"—")));
    body.append(row);
   }
  }
  note.textContent=d.account_count+" separately verified FP DEMO accounts. "+
    d.accounts.map(a=>a.account_masked+" "+a.fresh_quotes+"/13, "+a.source_quality+
      ", checked "+fmt(a.generated_at_utc)).join(" · ")+
    ". Missing instruments remain unavailable. No order authority from this research.";
 }
 async function refresh(){
  if(document.hidden||broker.hidden)return;
  try{
   const res=await fetch("/account/api/client/admin/fp-market",
     {credentials:"same-origin",cache:"no-store"});
   if(res.status===401||res.status===403){reset("Superadmin email verification required.");return;}
   if(!res.ok)throw Error("FP private research source unavailable");
   render(await res.json());
  }catch(_){reset("FP Markets broker research unavailable or stale; no substitute prices shown.");}
 }
 new MutationObserver(()=>{if(!broker.hidden)void refresh()})
   .observe(broker,{attributes:true,attributeFilter:["hidden"]});
 setInterval(()=>{if(!broker.hidden)void refresh()},60000);
 if(!broker.hidden)void refresh();
})();
