/* ABUTRON production evidence, read only; no order or account writes. */
"use strict";
(() => {
  const apex=location.pathname.startsWith("/apex/");
  const admin=!apex && !!document.getElementById("adminPanel");
  const host=apex ? document.querySelector(".workspace main") :
     document.getElementById(admin?"tab-overview":"portalSection");
  if(!host)return;
  const card=document.createElement("section");
  card.className="abutron-runtime-health";
  card.setAttribute("aria-label","Verified broker and signal health");
  const head=document.createElement("div");head.className="arh-head";
  const h=document.createElement("h2");h.textContent="Execution & signal health";
  const timestamp=document.createElement("span");timestamp.className="arh-clock";timestamp.textContent="VERIFYING";
  head.append(h,timestamp);
  const grid=document.createElement("div");grid.className="arh-grid";
  const fields={};
  for(const [key,label] of [["deriv","Deriv DEMO"],["fp","FP Markets DEMO"],
       ["signals","Qualified signals"],["risk","Risk & reconciliation"]]){
    const item=document.createElement("article");item.className="arh-item";
    const title=document.createElement("span");title.className="arh-label";title.textContent=label;
    const value=document.createElement("strong");value.className="arh-value";value.textContent="Checking";
    const detail=document.createElement("small");detail.className="arh-detail";detail.textContent="Verified evidence pending";
    fields[key]={value,detail};item.append(title,value,detail);grid.append(item);
  }
  const note=document.createElement("p");note.className="arh-note";
  note.textContent="Read-only monitoring. Market research is not an order acknowledgement. All DEMO entry and portfolio controls remain with the native broker engine.";
  card.append(head,grid,note);
  if(apex){
    const marker=host.querySelector("#safetyNotice");if(marker)marker.after(card);else host.prepend(card);
  }else if(admin){
    const marker=host.querySelector(".page-heading");if(marker)marker.after(card);else host.prepend(card);
  }else{
    const marker=host.querySelector(".account-top");if(marker)marker.after(card);else host.prepend(card);
  }
  const show=(key,value,detail)=>{fields[key].value.textContent=String(value);
    fields[key].detail.textContent=String(detail);};
  const count=(n)=>Number.isInteger(n)?n:"—";
  const reasons=(v)=>Object.entries(v||{}).filter(x=>typeof x[1]==="number" && x[1]>0)
      .sort((a,b)=>b[1]-a[1]).slice(0,2).map(([k,n])=>k.replace(/^SCANNER_HOLD_/,"").replaceAll("_"," ").toLowerCase()+": "+n).join(" · ")||"No qualified signal identified";
  const age=(stamp)=>{
    const v=Date.parse(stamp||"");
    return Number.isFinite(v)?new Date(v).toLocaleString("en-ZA",{timeZone:"Africa/Johannesburg",hour12:false})+" SAST":"Timestamp unavailable";
  };
  function unavailable(message){
    timestamp.textContent=message;
    for(const k of Object.keys(fields))show(k,"UNVERIFIED","Fresh authenticated production evidence unavailable");
  }
  const endpoint=apex?"/apex/api/runtime-health":admin?
     "/account/api/client/admin/runtime-health":"/account/api/client/runtime-health";
  async function refresh(){
    if(document.hidden)return;
    if(!apex && (host.hidden || (admin && document.getElementById("adminPanel").hidden)))return;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5500);
    try{
      const res=await fetch(endpoint,{credentials:"same-origin",cache:"no-store",signal:controller.signal});
      if(res.status===401||res.status===403){unavailable("SIGN IN / MFA REQUIRED");return;}
      if(!res.ok)throw Error("API_UNAVAILABLE");
      const d=await res.json();
      if(d.schema!=="abutron.apex.runtime_health.readonly.v1"||d.available!==true||
          d.execution_authority!==false)throw Error("EVIDENCE_STALE_OR_INVALID");
      timestamp.textContent="Verified "+age(d.checked_at_utc);
      if(d.scope==="AUTHENTICATED_CLIENT_ACCOUNTS_ONLY"){
        const dv=d.accounts?.Deriv||{},fp=d.accounts?.["FP Markets"]||{};
        show("deriv",count(dv.connected)+" connected",
             count(dv.account_controls_on)+" account switches ON · DEMO");
        show("fp",count(fp.connected)+" connected",
             count(fp.account_controls_on)+" account switches ON · DEMO");
        show("signals","M5 "+count(d.platform_signal_research?.deriv_m5_directional_symbols)+" · RESEARCH",
             d.platform_signal_research?.deriv_scanner_status==="NO_DERIV_ACCOUNT"?
               "Connect a Deriv account to see market signal diagnostics":
               reasons(d.platform_signal_research?.deriv_hold_reasons));
        show("risk",String(d.portfolio_ceiling_pct)+"% portfolio ceiling",
             "Account-specific MT5 stops and execution evidence remain authoritative");
      }else{
        const dv=d.deriv||{},fp=d.fpmarkets||{};
        show("deriv",count(dv.connected)+" connected / "+count(dv.account_controls_on)+" ON",
             count(dv.native_bridges_ready)+" native bridges · "+count(dv.account_feed_verified)+" verified account feeds");
        show("fp",count(fp.account_controls_on)+" switches ON · "+count(fp.broker_verified_positions)+" positions",
             count(fp.symbols_verified)+"/"+count(fp.symbols_total)+" symbols · "+
             (fp.unavailable_symbols?.length?"Unavailable "+fp.unavailable_symbols.join(", ")+" · ":"")+
             count(fp.broker_verified_acks)+" broker acknowledgements · "+fp.status);
        show("signals","Deriv M5 "+count(dv.m5_directional_symbols)+" · Qualified "+count(dv.qualified_candidates)+" / FP "+count(fp.qualified_candidates),
             reasons(dv.signal_reasons)+"; FP: "+reasons(fp.signal_reasons));
        const riskOK=fp.broker_risk_reconciled===true && fp.native_account_control_on===true;
        show("risk",riskOK?"FP ADAPTIVE VERIFIED":"FP CHECK / HOLD",
            "FP "+(fp.risk_model||"UNVERIFIED")+
            " · 0.10%/trade · "+count(d.portfolio_ceiling_pct)+"% cap · "+
            (riskOK?"Reconciled and account ON":"Risk/account activation evidence not fully aligned"));
      }
    }catch(_){unavailable("HEALTH DATA UNAVAILABLE");}
    finally{clearTimeout(timer);}
  }
  void refresh();
  setInterval(()=>{void refresh()},30000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)void refresh();});
  if(!apex){
    const visibilityTarget=admin?document.getElementById("adminPanel"):host;
    if(visibilityTarget)new MutationObserver(()=>{if(!visibilityTarget.hidden)void refresh();})
      .observe(visibilityTarget,{attributes:true,attributeFilter:["hidden"]});
  }
})();
