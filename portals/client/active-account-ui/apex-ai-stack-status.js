/* Authenticated, read-only ABUTRON client / CRM AI engine status. */
"use strict";
(() => {
  const all=(field)=>document.querySelectorAll('[data-ai-field="'+field+'"]');
  const put=(field,value)=>all(field).forEach(el=>{el.textContent=String(value??"UNVERIFIED");});
  async function update(){
    if(!document.querySelector("[data-abutron-ai-card]")) return;
    try{
      const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),4500);
      let response;
      try{
        response=await fetch("/account/api/client/ai-engine",{credentials:"same-origin",cache:"no-store",signal:controller.signal});
      }finally{clearTimeout(timer);}
      if(response.status===401||response.status===403){
        put("active-model","SIGN IN REQUIRED");
        put("candidate-model","SIGN IN REQUIRED");
        put("tradingagents-mode","SIGN IN REQUIRED");
        put("multiagent-mode","SIGN IN REQUIRED");
        return;
      }
      if(!response.ok)throw Error("API "+response.status);
      const d=await response.json();
      if(d.schema!=="abutron.apex.client_ai_engine.readonly.v1")throw Error("schema");
      put("active-model",d.production_model);
      put("candidate-model",d.candidate_model);
      put("tradingagents-mode",d.selective_reviewer_scheduled?"SELECTIVE / SCHEDULED":"UNVERIFIED");
      put("multiagent-mode",d.three_agent_production_connected?"ACTIVE":"STAGED ONLY · NOT LIVE");
      put("ai-checkpoint",d.checkpoint_utc||"UNVERIFIED");
      put("ai-note","TradingAgents research does not independently authorize orders. Existing account-level trading and broker risk controls remain authoritative.");
    }catch(e){
      for(const field of ["active-model","candidate-model","tradingagents-mode","multiagent-mode","ai-checkpoint"])put(field,"UNVERIFIED");
      put("ai-note","AI engine telemetry is unavailable. No model activation is implied.");
    }
  }
  update();
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)update();});
  setInterval(update,30000);
})();
