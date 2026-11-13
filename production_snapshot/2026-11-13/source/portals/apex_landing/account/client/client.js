(()=>{"use strict";const $=id=>document.getElementById(id);const loading=$("loading"),login=$("loginSection"),portal=$("portalSection"),msg=$("message");const api="/account/api/client/";const text=(s)=>String(s??"");const show=(el)=>el.hidden=false;const hide=(el)=>el.hidden=true;function notify(message,error=false){msg.textContent=message;msg.classList.toggle("error",error);show(msg)}function errorText(e){return e instanceof Error?e.message:"Request failed"}async function call(path,opt={}){const r=await fetch(api+path,{credentials:"same-origin",cache:"no-store",...opt});const j=await r.json().catch(()=>({error:"Invalid response from ABUTRON"}));if(!r.ok)throw Object.assign(new Error(j.error||"Request failed"),{status:r.status});return j}function post(path,payload){return call(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}function approvedState(x){signedInApproved=x.status==="approved";ownerOperator=x.role==="SUPERADMIN";const lic=x.crm_license||{};$("crmLicense").textContent=lic.plan?lic.plan+" · "+(lic.status||"Unknown"):"Not assigned";$("crmLicenseNote").textContent=String(lic.assigned_broker_accounts||0)+" / "+String(lic.seats||0)+" broker account seats · CRM only, no payment gateway";const sub=x.crm_subscription||{};$("crmSubscription").textContent=sub.plan?sub.plan+" · "+(sub.status||"Unknown"):"Not assigned";$("crmSubscriptionNote").textContent=sub.plan?(sub.renewal_on?"Next renewal date "+sub.renewal_on:"No renewal scheduled")+" · Manual billing record, no payment processed":"Managed by ABUTRON Admin · No checkout";$("adminNavLink").hidden=x.role!=="SUPERADMIN";$("clientName").textContent=String(x.name||"Client").split(" ")[0]||"Client";if(ownerOperator){$("crmLicense").textContent="Operator · Superadmin";$("licenseRequestForm").hidden=true;$("trialHeading").textContent="ABUTRON Superadmin · Operator Account";$("trialStatusText").textContent="Owner accounts are independent from customer trials and paid subscriptions.";$("crmLicenseNote").textContent="Owner account · customer trial excluded";if(!sub.plan){$("crmSubscription").textContent="Operator account";$("crmSubscriptionNote").textContent="Owner account · no customer subscription assigned"}}$("clientEmail").textContent=x.email;$("accountStatus").textContent=x.status==="approved"?"Active":"Verify email";$("approvalNote").textContent=x.status==="approved"?"Email verified. You may enroll a broker account below.":"Email not verified. Open the ABUTRON verification email before adding a broker account.";
 $("brokerLinkVerificationNotice").hidden=signedInApproved;
 $("requestBtn").disabled=!signedInApproved;}async function renderRequests(){
 const [data,linked]=await Promise.all([call("requests"),call("connections")]);
 const list=$("requestsList");list.replaceChildren();
 const connections=(linked.connections||[]).filter(r=>r.connection_status!=="DISCONNECTED");
 for(const r of connections){
  const el=document.createElement("article");el.className="request-item";
  const head=document.createElement("div");head.className="request-head";
  const title=document.createElement("b");title.textContent=r.broker+" · MT5 · "+r.environment;
  const chip=document.createElement("span");chip.className="chip";
  chip.textContent=r.connection_status==="CONNECTED" && r.broker_verified?"Broker verified":r.connection_status==="CONNECTING"?"Enrolled · verification pending":r.connection_status;
  head.append(title,chip);el.append(head);
  const line=document.createElement("p");
  line.textContent="Account "+r.account_reference_masked+" · Server "+r.broker_server;
  const state=document.createElement("p");
  state.textContent=r.broker_verified?"Broker status verified. Trading permissions are separate.":"No broker authentication yet · Trading OFF";
  el.append(line,state);list.append(el)
 }
 for(const r of data.requests||[]){
  const el=document.createElement("article");el.className="request-item";
  const head=document.createElement("div");head.className="request-head";
  const title=document.createElement("b");title.textContent=r.broker+" · "+r.platform;
  const chip=document.createElement("span");chip.className="chip";
  chip.textContent=r.status==="oauth_pending"?"OAuth required":"Verification pending";
  head.append(title,chip);
  const details=document.createElement("p");details.textContent=r.environment+" · Account "+r.account_reference+" · Server "+r.broker_server;
  const foot=document.createElement("p");foot.textContent="Not connected · No trading permissions";
  const button=document.createElement("button");button.className="remove";button.type="button";button.textContent="Remove request";
  button.addEventListener("click",async()=>{button.disabled=true;try{
   await call("requests/"+encodeURIComponent(r.id),{method:"DELETE",headers:{"Content-Type":"application/json"}});
   await Promise.all([renderRequests(),renderTradingControls()]);window.dispatchEvent(new Event("apex:mt5-accounts-updated"));notify("Account verification request removed.")
  }catch(e){notify(errorText(e),true);button.disabled=false}});
  el.append(head,details,foot,button);list.append(el)
 }
 if(!connections.length && !(data.requests||[]).length){
  const e=document.createElement("div");e.className="empty";
  e.textContent=signedInApproved?"No broker accounts enrolled yet. Begin account linking to submit one.":"Verify your ABUTRON email before enrolling any broker accounts.";
  list.append(e)
 }
}
let tradingRefreshTimer=null;
function scheduleTradingRefresh(recheck){
 if(tradingRefreshTimer!==null){clearTimeout(tradingRefreshTimer);tradingRefreshTimer=null}
 if(recheck && login.hidden){
  tradingRefreshTimer=setTimeout(()=>{
   renderTradingControls().catch(e=>{notify(errorText(e),true);scheduleTradingRefresh(true)})
  },10000);
 }
}
async function renderTradingControls(){
 const list=$("tradingControlsList"),data=await call("trading-controls");
 list.replaceChildren();
 let demoOn=0,liveOn=0,livePending=0,connected=0,needsRecheck=false;
 if(!data.controls.length){
  const empty=document.createElement("div");empty.className="empty";
  empty.textContent="No MT5 accounts added yet. Add an account above to create its independent trading control.";
  list.append(empty);
 }
 for(const entry of data.controls){
  const effective=entry.trading_enabled===true,requested=entry.requested_enabled===true;
  const pending=requested&&!effective,stopping=!requested&&effective,active=requested&&effective;
  if(pending||stopping)needsRecheck=true;
  if(entry.connection_status==="CONNECTED")connected++;
  if(active && entry.environment==="DEMO")demoOn++;
  if(active && entry.environment==="LIVE")liveOn++;if(pending && entry.environment==="LIVE")livePending++;
  const card=document.createElement("article");card.className="trade-control-row";
  const info=document.createElement("div");info.className="trade-control-details";
  const title=document.createElement("strong");
  title.textContent=entry.broker+" · "+entry.platform+" · "+entry.environment;
  const meta=document.createElement("div");meta.className="trade-control-meta";
  const ref=String(entry.account_reference||"");
  meta.textContent="Account ••••"+ref.slice(-4)+" · "+entry.connection_status.replaceAll("_"," ");
  const note=document.createElement("small");
  note.textContent=stopping?"Stop requested. New orders are blocked; waiting for native OFF acknowledgment.":entry.note||"Account-specific trading authorization.";
  info.append(title,meta,note);
  const right=document.createElement("div");right.className="trade-control-actions";
  const state=document.createElement("b");state.className=active?"trade-state on":pending?"trade-state pending":stopping?"trade-state stopping":"trade-state off";
  state.textContent=active?"CRM ON · BROKER CHECK":pending?"PENDING":stopping?"STOPPING":"OFF";
  const button=document.createElement("button");button.type="button";button.className="trade-switch";
  button.setAttribute("role","switch");button.setAttribute("aria-checked",String(requested));
  button.setAttribute("aria-label","Automatic trading for "+entry.broker+" "+entry.environment+" account ending "+ref.slice(-4));
  button.title=stopping?"Stopping: awaiting native OFF acknowledgment":pending?"Cancel pending "+entry.environment+" activation":entry.control_available?"Change automatic trading for this account":"MT5 connection and execution gateway required";
  button.disabled=stopping||!(entry.control_available||active||pending);
  button.addEventListener("click",async()=>{
    const enabling=!requested;
    button.disabled=true;
    try{
      const response=await post("trading-controls/"+encodeURIComponent(entry.id),{enabled:enabling});
      await renderTradingControls();
      const account=entry.broker+" "+entry.environment+" ••••"+ref.slice(-4);
      notify(enabling?(response.trading_enabled===true?account+": automatic trading ON.":response.message||account+": activation requested; awaiting native acknowledgment."):response.trading_enabled===true?account+": STOP requested. New entries blocked; awaiting native OFF acknowledgment.":account+": automatic trading OFF.");
    }catch(err){notify(errorText(err),true);await renderTradingControls()}
  });
  right.append(state,button);
  if(entry.connection_status==="CONNECTING" || entry.connection_status==="DISCONNECTED" || entry.connection_status==="ERROR"){
    const unlink=document.createElement("button");unlink.className="remove";unlink.type="button";
    unlink.textContent=entry.connection_status==="DISCONNECTED"?"Already unlinked":"Remove link";
    unlink.disabled=entry.connection_status==="DISCONNECTED";
    unlink.addEventListener("click",async()=>{unlink.disabled=true;try{
      await call("connections/"+encodeURIComponent(entry.id),{method:"DELETE"});
      await renderTradingControls();notify("MT5 account enrollment removed; trading remains OFF.");
    }catch(e){notify(errorText(e),true);unlink.disabled=false}});
    info.append(unlink);
  }
  card.append(info,right);list.append(card);
 }
 $("verifiedCount").textContent=connected+" connected";
 $("demoTradeStatus").textContent=demoOn?"ON · "+demoOn+" account(s)":"OFF";
 $("liveTradeStatus").textContent=liveOn?"ON · "+liveOn+" account(s)":livePending?"PENDING · "+livePending+" account(s), real orders OFF":"OFF";
 scheduleTradingRefresh(needsRecheck);
}
async function initialize(){try{const me=await call("me");hide(login);show(portal);approvedState(me);const sections=await Promise.allSettled([renderRequests(),renderTradingControls(),renderLicense()]);if(sections.some(x=>x.status==="rejected"))notify("Some account sections are temporarily unavailable. Your sign-in is still active.",true)}catch(e){hide(portal);show(login);notify("Could not load your account. Try signing in again.",true)}finally{hide(loading)}}$("loginForm").addEventListener("submit",async e=>{e.preventDefault();hide(msg);const f=e.currentTarget;const btn=f.querySelector('button[type="submit"]');btn.disabled=true;try{await post("login",{email:f.elements.email.value,password:f.elements.password.value});f.elements.password.value="";await initialize();notify("Signed in. Broker linking requires actual broker authorization.")}catch(err){notify(errorText(err),true)}finally{btn.disabled=false}});$("logoutBtn").addEventListener("click",async()=>{try{await post("logout",{});scheduleTradingRefresh(false);hide(msg);hide(portal);show(login);notify("You have signed out.")}catch(e){notify(errorText(e),true)}});async function renderLicense(){
 const d=await call("license/summary"),t=d.trial||{},paid=d.crm_license||{},req=d.requests||[];
 const pricePlans=d.pricing||[],select=$("licenseRequestForm").elements.namedItem("plan");
 for(const option of select.options){
  const p=pricePlans.find(x=>x.plan===option.value);
  if(p){option.value=p.plan;option.textContent=p.plan+" — R "+(p.amount_minor/100).toLocaleString("en-ZA")+"/month";}
 }
 const chosen=pricePlans.find(x=>x.plan===select.value);
 $("licensePlanQuote").textContent=chosen?"ABUTRON SOFTWARE LICENSE: R "+(chosen.amount_minor/100).toLocaleString("en-ZA")+"/month · "+chosen.included_broker_accounts+" broker-account seat(s). NO TRADING EQUITY INCLUDED.":"Prices temporarily unavailable.";
 if(chosen)$("licenseRequestForm").elements.namedItem("seats").value=chosen.included_broker_accounts;
 const expires=t.expires_at?new Date(t.expires_at).toLocaleString():"—";
 const active=t.status==="active",expired=t.status==="expired",isOwner=t.status==="owner_exempt"||ownerOperator;
 $("licenseRequestForm").hidden=isOwner;
 if(isOwner){
   $("trialHeading").textContent="ABUTRON Superadmin · Operator Account";
   $("trialStatusText").textContent="Owner-operated MT5 is independent of customer trials and paid customer subscriptions. No 24-hour trial countdown applies to this account.";
   $("buyLicenseNotice").textContent="Owner operations are managed separately. Customer trials and paid license requests apply to customer identities only.";
   $("crmLicense").textContent="Operator · Superadmin";
   $("crmLicenseNote").textContent="Owner account · customer trial excluded";
   $("licensePurchaseStatus").textContent="";
   return;
 }
 const minutes=Math.max(0,Math.ceil((t.seconds_remaining||0)/60));
 const hours=Math.floor(minutes/60),mins=minutes%60;
 $("trialHeading").textContent=active?"Trial active · "+hours+"h "+mins+"m remaining":expired?"Trial finished · Paid license required":paid.plan?"ABUTRON license status":"1-day free trial";
 $("trialStatusText").textContent=active
   ?"Your one-time 24-hour trial started after your first verified DEMO broker connection and ends "+expires+". Broker trading activation is separate."
   :expired?"Your free trial expired "+expires+". New trades require a paid ABUTRON license. Existing protective stops are not disabled by trial expiry."
   :paid.plan?"License: "+paid.plan+" — "+paid.status+". Trading requires independently verified broker permissions."
   :"Your 24-hour trial will begin only after your first DEMO broker account is successfully authenticated and marked CONNECTED. Email verification, account enrollment and pending OAuth do not start the countdown.";
 if(active||expired){$("crmLicense").textContent=active?"1-day trial · Active":"Trial expired";$("crmLicenseNote").textContent=active?hours+"h "+mins+"m remaining · DEMO only":"Buy a license to continue"}
 if(paid.plan && paid.plan!=="1-Day Trial"){
  $("crmLicense").textContent=paid.plan+" · "+paid.status;
  $("crmLicenseNote").textContent=String(paid.assigned_broker_accounts||0)+" / "+String(paid.seats||0)+" paid broker-account seats";
 }
 const open=req.find(x=>x.status==="requested"||x.status==="contacted");
 $("requestPaidLicense").disabled=!!open||!meApproved();
 $("licensePurchaseStatus").textContent=open?"Request pending: "+open.requested_plan+" / "+open.requested_seats+" included broker-account seat(s). Trading equity is NOT included; fund your broker account directly for LIVE trading.":req.length?"Latest request: "+req[0].requested_plan+" · "+req[0].status:"No paid license purchase request yet.";
}
let signedInApproved=false,ownerOperator=false;
function meApproved(){return signedInApproved}
$("licenseRequestForm").elements.namedItem("plan").addEventListener("change",async()=>{
 try{const data=await call("license/summary"),p=(data.pricing||[]).find(x=>x.plan===$("licenseRequestForm").elements.namedItem("plan").value);
 $("licensePlanQuote").textContent=p?"ABUTRON SOFTWARE LICENSE: R "+(p.amount_minor/100).toLocaleString("en-ZA")+"/month · "+p.included_broker_accounts+" broker-account seat(s). NO TRADING EQUITY INCLUDED.":"Prices temporarily unavailable.";
 if(p)$("licenseRequestForm").elements.namedItem("seats").value=p.included_broker_accounts}
 catch(err){notify(errorText(err),true)}
});
$("licenseRequestForm").addEventListener("submit",async e=>{
 e.preventDefault();const btn=$("requestPaidLicense"),data=new FormData(e.currentTarget);btn.disabled=true;
 try{const response=await post("license/request",{plan:data.get("plan"),seats:Number(data.get("seats")),note:data.get("note")||"",acknowledge_broker_deposit:data.get("acknowledge_broker_deposit")==="on"});
   notify(response.message);await renderLicense()}catch(err){notify(errorText(err),true)}finally{await renderLicense().catch(()=>{btn.disabled=false})}
});
$("broker").addEventListener("change",()=>{const p=$("platform");const isDeriv=$("broker").value==="Deriv";for(const option of p.options)if(option.value==="cTrader")option.disabled=isDeriv;if(isDeriv)p.value="MT5"});$("brokerForm").addEventListener("submit",async e=>{e.preventDefault();hide(msg);
 if(!signedInApproved){notify("Verify your ABUTRON email first. Open the verification email, then refresh the portal.",true);return;}
 const f=e.currentTarget,btn=$("requestBtn");btn.disabled=true;const v=new FormData(f);const payload={broker:v.get("broker"),platform:v.get("platform"),environment:v.get("environment"),account_reference:v.get("account_reference")?.trim(),broker_server:v.get("broker_server")?.trim(),understand_not_connected:$("requestAck").checked};try{const out=await post(payload.platform==="MT5"?"connections/mt5/start":"requests",payload.platform==="MT5"?((({platform,...rest})=>rest)(payload)):payload);f.reset();notify(out.message+(payload.platform==="MT5"?" ABUTRON will send an account-update notification. This email does not authenticate MT5. Enrollment is CONNECTING; trading remains OFF.":" No LIVE or DEMO trading is activated."));await Promise.all([renderRequests(),renderTradingControls()]);window.dispatchEvent(new Event("apex:mt5-accounts-updated"))}catch(err){notify(errorText(err),true)}finally{btn.disabled=false}});initialize()})();