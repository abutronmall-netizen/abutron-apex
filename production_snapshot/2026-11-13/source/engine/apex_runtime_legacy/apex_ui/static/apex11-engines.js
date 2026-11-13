/* Read-only live APEX 1.1 broker-journal status; no order writes. */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const put=(id,value)=>{const e=$(id);if(e)e.textContent=String(value);};
  const SCHEMA="abutron.apex11.operator_dashboard.readonly.v1";
  const names=["Regime","Trend","Mean Reversion","Breakout","Portfolio","Risk"];
  const utc=stamp=>{
    if(stamp===null||stamp===undefined)return "UNVERIFIED";
    const d=new Date(typeof stamp==="number"?stamp*1000:stamp);
    return Number.isFinite(d.getTime())?
      d.toLocaleString("en-GB",{timeZone:"UTC",dateStyle:"short",timeStyle:"medium"})+" UTC":"UNVERIFIED";
  };
  function cells(row,values){
    for(const value of values){const td=document.createElement("td");td.textContent=String(value??"—");row.appendChild(td);}
  }
  function showRows(id,accounts){
    const target=$(id);if(!target)return;
    target.replaceChildren();
    for(const a of accounts){
      const accountLabel=(a.broker||"Deriv")+" "+(a.environment||"DEMO")+" ••••"+a.account_suffix;
      const fresh=a.status==="CURRENT_RESEARCH";
      if(!Array.isArray(a.symbols)||a.symbols.length===0){
        const tr=document.createElement("tr");cells(tr,[accountLabel,"No verified decisions","—","—",a.status]);target.appendChild(tr);continue;
      }
      for(const s of a.symbols){
        const tr=document.createElement("tr");
        cells(tr,[accountLabel,s.symbol,s.direction,utc(s.closed_ts),fresh?"CURRENT · "+a.age_seconds+"s":a.status]);
        if(!fresh)tr.className="apex11-stale";target.appendChild(tr);
      }
    }
  }
  function render(d){
    if(d.schema!==SCHEMA)throw Error("Unexpected data source");
    const accounts=Array.isArray(d.accounts)?d.accounts:[];
    const comps=Array.isArray(d.research_components)?d.research_components:[];
    const observed=comps.filter(x=>x.recent_output_observed).length;
    const n=d.fresh_account_publishers??0;
    const total=d.total_account_publishers??0;
    const status=n===total && total>0?"CURRENT · RESEARCH":n>0?"PARTIAL · RESEARCH":"NO CURRENT JOURNALS";
    const orders=d.orders_submitted_by_publishers===0?"0":"NOT VERIFIED";
    put("apex11SummaryState",status);
    put("apex11StatusChip",status);
    put("apex11SignalsState",status);
    put("apex11AccountCount",n+" / "+total+" DEMO");
    put("apex11EngineCount",observed+" / 6");
    put("apex11OrderCount",orders);
    put("apex11OverviewNote","APEX 1.1 account-bound DEMO research: Deriv "+(d.deriv_research_publishers??0)+"/3, FP Markets "+(d.fp_research_publishers??0)+"/3. Research publishers do not place broker orders; LIVE 0178 remains outside DEMO research.");
    put("apex11Checked","Operator telemetry checked "+utc(d.checked_at_utc)+" · Individual accounts have independent timestamps.");
    const grid=$("apex11Components");
    if(grid){
      grid.replaceChildren();
      for(const name of names){
        const item=document.createElement("article");item.className="apex11-component";
        const title=document.createElement("strong");title.textContent=name+" Agent";
        const mode=document.createElement("span");
        const found=comps.find(c=>c.name===name)?.recent_output_observed===true;
        mode.className="apex11-component-state"+(found?" observed":"");
        mode.textContent=found?"OUTPUT OBSERVED":"NO RECENT OUTPUT VERIFIED";
        const detail=document.createElement("small");
        detail.textContent=found?"Found in current account-bound M5 research journal":"No current evidence of contribution; not a failure diagnosis";
        item.append(title,mode,detail);grid.appendChild(item);
      }
    }
    const allRows=accounts.concat(Array.isArray(d.non_research_accounts)?d.non_research_accounts:[]);
    showRows("apex11Signals",allRows);
    showRows("apex11SignalsExtra",allRows);
  }
  function unavailable(){
    for(const id of ["apex11SummaryState","apex11StatusChip","apex11SignalsState"])put(id,"UNVERIFIED");
    for(const id of ["apex11AccountCount","apex11EngineCount","apex11OrderCount"])put(id,"—");
    put("apex11OverviewNote","APEX 1.1 operator journal telemetry unavailable; no execution status can be inferred.");
    put("apex11Checked","Last checked: telemetry unavailable");
    const g=$("apex11Components");if(g)g.textContent="No verified engine output available.";
    for(const id of ["apex11Signals","apex11SignalsExtra"]){
      const t=$(id);if(t){t.replaceChildren();const r=document.createElement("tr");cells(r,["Engine output unavailable","—","—","—","UNVERIFIED"]);t.appendChild(r);}
    }
  }
  async function refresh(){
    if(document.hidden)return;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),6000);
    try{
      const r=await fetch("/apex/api/apex11-engines",{credentials:"same-origin",cache:"no-store",signal:controller.signal});
      if(!r.ok)throw Error("HTTP "+r.status);
      render(await r.json());
    }catch(_){unavailable();}
    finally{clearTimeout(timer);}
  }
  refresh();
  setInterval(refresh,30000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
})();
