/* APEX FP native-loss and entry-quality transparency. No trade controls. */
(() => {
 "use strict";
 const root=document.getElementById("overview");if(!root)return;
 const el=(tag,cls,txt)=>{const x=document.createElement(tag);
   if(cls)x.className=cls;if(txt!==undefined)x.textContent=String(txt);return x;};
 const wrap=el("article","panel fp-panel");wrap.id="fp-quality-diagnostics";
 const head=el("div","panel-head fp-panel-head");
 const heading=el("div");
 heading.append(el("p","panel-kicker","BROKER-VERIFIED · QUANT/ENTRY DIAGNOSTICS"),
   el("h2","","FP Markets · losses, native exposure and signal holds"));
 head.append(heading,el("span","fp-tag","READ ONLY"));wrap.append(head);
 const subtitle=el("p","fp-muted","Waiting for fresh broker-native evidence.");
 wrap.append(subtitle);
 const metrics=el("div","fp-metrics");wrap.append(metrics);
 const tableWrap=el("div","fp-scroll"),table=el("table","fp-table");
 const th=el("thead"),hdr=el("tr");
 ["FP account","Broker positions","Trading deals / 90d","Positive / negative exit deals",
  "Account deal cashflow USD","Top negative symbols"].forEach(s=>hdr.append(el("th","",s)));
 th.append(hdr);const body=el("tbody");table.append(th,body);tableWrap.append(table);wrap.append(tableWrap);
 const signal=el("p","fp-muted","Scanner evidence pending");wrap.append(signal);
 root.append(wrap);
 const money=n=>typeof n==="number"&&Number.isFinite(n)?"$"+n.toFixed(2):"UNVERIFIED";
 const card=(title,value)=>{const c=el("div","fp-metric");c.append(el("span","",title),el("strong","",value));metrics.append(c);};
 const draw=(arr)=>{const r=el("tr");arr.forEach(v=>r.append(el("td","",v)));body.append(r);};
 const unavailable=()=>{metrics.replaceChildren();body.replaceChildren();subtitle.textContent="Fresh, independently verified broker history unavailable; no inferred returns or trade counts.";signal.textContent="No setup approval is implied by stale telemetry.";};
 async function refresh(){
   if(document.hidden)return;
   try{
     const res=await fetch("/apex/api/fp-quality-diagnostics",
       {credentials:"same-origin",cache:"no-store"});
     if(!res.ok)throw Error("Unavailable");
     const d=await res.json();
     if(d.schema!=="abutron.fpmarkets.quality_diagnostics.readonly.v1"||
        d.orders_enabled!==false||d.execution_authorized!==false)throw Error("Untrusted");
     metrics.replaceChildren();body.replaceChildren();
     for(const a of d.account_histories||[]){
       if(a.history_verified!==true){draw(["UNVERIFIED","—","—","—","—","—"]);continue;}
       const poor=(a.most_negative_symbol_cashflows||[]).slice(0,3)
           .map(s=>s.symbol+" "+money(s.deal_cashflow_usd)).join(" · ");
       draw([a.account_masked,a.open_positions,a.trading_deals,
             a.positive_closing_deals+" / "+a.negative_closing_deals,
             money(a.broker_reported_all_deal_cashflow_usd),poor||"None verified"]);
     }
     const s=d.scanner||{},ai=d.ai||{},q=d.quant||{};
     card("FP scan proposals",s.available?s.qualified_proposals+"/13":"UNVERIFIED");
     card("Hold decisions",s.available?s.on_hold+"/13":"UNVERIFIED");
     card("AI completed reviews",ai.available?ai.completed_reviews:"UNVERIFIED");
     card("Quant execution","SHADOW ONLY");
     card("True broker order-book flow",q.real_order_book_verified?"VERIFIED":"NOT CONNECTED");
     subtitle.textContent="Native 90-day deal cashflow includes entry costs and may include currently open positions. It is NOT attributable strategy net P&L or validated future edge.";
     const holds=(s.hold_reasons||[]).slice(0,5).map(x=>x.reason+": "+x.count).join(" · ");
     signal.textContent=(s.available?"Current scanner holds: "+(holds||"None"):"Scanner evidence unavailable")+
       " · AI decisions and quote/candle proxies are not broker-acknowledged orders.";
   }catch(_){unavailable();}
 }
 void refresh();
 setInterval(refresh,60000);
 document.addEventListener("visibilitychange",()=>{if(!document.hidden)void refresh();});
})();
