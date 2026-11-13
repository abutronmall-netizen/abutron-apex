/* Authenticated ABUTRON APEX 1.1 platform research status; no broker writes. */
"use strict";
(() => {
  const nodes=field=>document.querySelectorAll('[data-ai-field="'+field+'"]');
  const put=(field,value)=>nodes(field).forEach(el=>{el.textContent=String(value??"UNVERIFIED");});
  async function refresh(){
    if(!document.querySelector("[data-abutron-ai-card]"))return;
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),5000);
    try{
      const response=await fetch("/account/api/client/ai-engine",
        {credentials:"same-origin",cache:"no-store",signal:controller.signal});
      if(response.status===401||response.status===403){
        for(const f of ["active-model","candidate-model","tradingagents-mode","multiagent-mode","ai-checkpoint"])put(f,"SIGN IN REQUIRED");
        put("ai-note","Sign in to see platform engine status.");return;
      }
      if(!response.ok)throw Error("API "+response.status);
      const d=await response.json();
      if(d.schema!=="abutron.apex.client_apex11_engine.readonly.v1")throw Error("Source mismatch");
      put("active-model",d.engine);
      put("candidate-model",d.fresh_publishers+" / "+d.total_publishers+(d.fresh_publishers===d.total_publishers?" · CURRENT":" · PARTIAL/STALE"));
      put("tradingagents-mode",d.observed_components+" / "+d.total_components+" · OBSERVED");
      put("multiagent-mode",d.orders_submitted_by_publishers===0?"0 · NO SUBMITTED ORDERS":"UNVERIFIED");
      put("ai-checkpoint",d.checked_at_utc||"UNVERIFIED");
      put("ai-note","APEX 1.1 platform research covers Deriv and FP Markets DEMO journals. It is not proof of execution on your MT5 account; LIVE remains outside DEMO research.");
    }catch(_){
      for(const f of ["active-model","candidate-model","tradingagents-mode","multiagent-mode","ai-checkpoint"])put(f,"UNVERIFIED");
      put("ai-note","Current APEX 1.1 engine telemetry is unavailable; no execution status is implied.");
    }finally{clearTimeout(timer);}
  }
  refresh();
  setInterval(refresh,30000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
  const panel=document.getElementById("portalSection");
  if(panel)new MutationObserver(()=>{if(!panel.hidden)refresh();}).observe(panel,{attributes:true,attributeFilter:["hidden"]});
})();
