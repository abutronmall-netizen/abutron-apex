/* ABUTRON APEX live AI stack status: read-only telemetry only. */
"use strict";
(() => {
  const byId=id=>document.getElementById(id);
  const set=(id,v)=>{const e=byId(id); if(e)e.textContent=String(v??"UNVERIFIED");};
  const flag=v=>v===true?"ACTIVE":"NOT ACTIVE";
  const ago=v=>Number.isFinite(v)?(v<60?v+"s":Math.round(v/60)+"m"):"unverified";
  async function refreshAgentStack(){
    try{
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),4500);
      let response;
      try {
        response=await fetch("/apex/api/agent-stack",{credentials:"same-origin",cache:"no-store",signal:controller.signal});
      } finally {clearTimeout(timer);}
      if(!response.ok)throw Error("HTTP "+response.status);
      const d=await response.json();
      if(d.schema!=="abutron.apex.agent_stack.readonly.v1")throw Error("schema");
      const p=d.production||{}, u=d.upgrade||{}, b=d.broker_review||{}, r=d.last_review||{};
      const prodOk=p.ollama_service_active===true&&p.installed===true&&p.selective_reviewer_timer_active===true;
      set("agentStackPrimary",p.model||"UNVERIFIED");
      set("agentStackPrimaryMeta",prodOk?"Selective TradingAgents · scheduled":"Model or reviewer unavailable");
      set("agentStackNext",u.candidate_model||"UNVERIFIED");
      set("agentStackNextMeta",u.model_installed&&u.three_agent_canary_integrity_verified?"Staged · research only":"Not verified");
      set("agentStackMulti",u.production_connected?"CONNECTED":"NOT CONNECTED");
      set("agentStackMultiMeta","Technical · Regime · Risk (canary only)");
      set("agentStackReview",r.fresh?(r.status||"UNVERIFIED"):"STALE / UNVERIFIED");
      set("agentStackReviewMeta",r.fresh?"Updated "+ago(r.age_seconds)+" ago · "+(r.candidate_count??0)+" candidates":"No fresh TradingAgents review proof");
      set("agentStackHealth",prodOk?"RUNNING":"CHECK REQUIRED");
      set("agentsLiveMode",p.tradingagents_mode||"UNVERIFIED");
      set("agentsProductionModel",p.model||"UNVERIFIED");
      set("agentsOllama",flag(p.ollama_service_active));
      set("agentsDeriv",b.deriv||"UNVERIFIED");
      set("agentsFp",b.fp_markets||"UNVERIFIED");
      set("agentsUnified",flag(b.unified_monitor_active));
      set("agentsNextModel",u.candidate_model||"UNVERIFIED");
      set("agentsCanary",u.state||"UNVERIFIED");
      set("agentsEvidence",u.broker_candle_3_agent_proof||"NOT VERIFIED");
      set("agentsRoles",Array.isArray(u.roles)?u.roles.join(" / "):"UNVERIFIED");
      set("agentsChecked",new Date(d.checked_at_utc).toLocaleString("en-GB",{timeZone:"UTC"})+" UTC");
      set("agentsSafety",d.warning||"Research-only canary; no order authority");
    }catch(err){
      for(const id of ["agentStackPrimary","agentStackNext","agentStackMulti","agentStackReview","agentStackHealth","agentsLiveMode","agentsProductionModel","agentsOllama","agentsDeriv","agentsFp","agentsUnified","agentsNextModel","agentsCanary","agentsEvidence","agentsRoles","agentsChecked"]){
        set(id,"UNVERIFIED");
      }
      set("agentStackPrimaryMeta","Telemetry unavailable");
      set("agentStackNextMeta","Telemetry unavailable");
      set("agentStackMultiMeta","No proof of production connection");
      set("agentStackReviewMeta","No fresh review proof");
      set("agentsSafety","AI status could not be verified; do not assume a model upgrade is live.");
    }
  }
  async function refreshQuantFirst(){
    try {
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),4500);
      let response;
      try {
        response=await fetch("/apex/api/quant-first",{credentials:"same-origin",cache:"no-store",signal:controller.signal});
      } finally {clearTimeout(timer);}
      if(!response.ok)throw Error("HTTP "+response.status);
      const d=await response.json();
      if(d.schema!=="abutron.apex.quant_first.dashboard.readonly.v1"
        ||d.execution_authorized!==false||d.orders_enabled!==false)throw Error("untrusted status");
      const q=d.deriv||{},fp=d.fp_markets||{},v=d.validation||{};
      set("quantMode","SHADOW / NO ORDERS");
      set("quantDeriv",q.status==="RESEARCH_ACTIVE"?
        String(q.symbols)+" verified symbols · "+String(q.research_candidates)+" research biases":
        "STALE / UNVERIFIED");
      set("quantFp",fp.status==="PARTIAL_ACCOUNT_SCOPED_RESEARCH"?
        String(fp.accounts)+" DEMO accounts · "+
          (Array.isArray(fp.coverage)?fp.coverage.map(x=>x.verified+"/13").join(" · "):"unverified")+" symbols":
        "STALE / UNVERIFIED");
      set("quantFlow",d.verified_institutional_order_flow===true?"VERIFIED":"NOT CONNECTED · price/quote proxies only");
      set("quantValidation",v.net_profitability_verified===true?"RESEARCH REVIEW REQUIRED":"NOT CERTIFIED · no net edge");
      set("quantVeto",d.smc_ict_mandatory===false?"NOT IN QUANT PIPELINE":"UNVERIFIED");
      set("quantChecked",new Date(d.checked_at_utc).toLocaleString("en-GB",{timeZone:"UTC"})+" UTC");
      set("quantResearchCaveat","Quant research and gross-only replay are not validated execution signals. "+
        "FP feed remains partial and broker order-flow depth is not connected. Existing MT5/risk controls are unchanged.");
    }catch(err){
      for(const id of ["quantMode","quantDeriv","quantFp","quantFlow","quantValidation","quantVeto","quantChecked"]){
        set(id,"UNVERIFIED");
      }
      set("quantResearchCaveat","Quant telemetry unavailable; no new quant trade authorization can be inferred.");
    }
  }
  refreshAgentStack();
  setInterval(refreshAgentStack,20000);
  refreshQuantFirst();
  setInterval(refreshQuantFirst,60000);
})();
