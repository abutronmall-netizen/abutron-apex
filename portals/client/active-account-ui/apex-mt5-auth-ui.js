/* ABUTRON MT5 DEMO account manager: direct broker password verification.
   Existing client sign-in is required. No extra email code and no password storage.
   MT5 account remains CONNECTING until a persistent broker worker is verified. */
(()=>{
"use strict";
const form=document.getElementById("brokerForm");
const password=document.getElementById("mt5Password");
if(!form||!password)return;
const broker=form.elements.namedItem("broker");
const environment=form.elements.namedItem("environment");
const server=form.elements.namedItem("broker_server");
const login=form.elements.namedItem("account_reference");
const platform=form.elements.namedItem("platform");
const ack=document.getElementById("requestAck");
const mainButton=document.getElementById("requestBtn");
const formNotice=form.querySelector(".apex-mt5-form-notice");
const note=document.createElement("p");
note.setAttribute("role","status");
note.className="helper";
password.closest("label")?.insertAdjacentElement("afterend",note);
const result=document.createElement("p");
result.setAttribute("role","status");
result.className="apex-mt5-form-notice";
result.hidden=true;
note.insertAdjacentElement("afterend",result);
let available=false,liveReady=false,busy=false,existingId=null;
const endpoint="/account/api/client/";
async function send(path,body){
 const response=await fetch(endpoint+path,{method:"POST",credentials:"same-origin",cache:"no-store",
  headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify(body)});
 const data=await response.json().catch(()=>({error:"Unexpected response from ABUTRON."}));
 if(!response.ok){
   const error=new Error(data.message||data.error||"MT5 verification could not be completed.");
   error.status=response.status;error.details=data;
   throw error;
 }
 return data;
}
function status(text,isError=false){
 result.hidden=false;
 result.textContent=text;
 result.style.borderColor=isError?"#bb6262":"#477b70";
 result.scrollIntoView({block:"nearest",behavior:"smooth"});
}
function resetExisting(){existingId=null;result.hidden=true;mainButton.textContent="Connect Trading Account";}
function refresh(){
 const demo=environment.value==="DEMO"&&platform.value==="MT5";
 const fpLive=broker.value==="FP Markets"&&environment.value==="LIVE"&&platform.value==="MT5";
 const derivLive=broker.value==="Deriv"&&environment.value==="LIVE"&&platform.value==="MT5";
 const modeSupported=platform.value==="MT5";
 const permitted=demo||((fpLive||derivLive)&&liveReady);
 // Never prevent the customer from typing a LIVE MT5 password just because
 // an asynchronous health probe has not finished. A disabled/gated submit
 // still rejects transmission until authenticated gateway readiness.
 password.disabled=!modeSupported;
 password.required=modeSupported&&available;
 if(!modeSupported)password.value="";
 if(formNotice)formNotice.textContent=modeSupported?
   "Secure MT5 password input available. "+(available?(permitted?"Verified connection gateway ready.":"LIVE account entry is visible, but no authenticated broker connector is available for this mode."):"Connection gateway pending or offline; credentials will not be submitted.")+
   " Broker login is separate from automatic trading authorization.":
   "This broker/account mode has no authorized MT5 connection worker.";
 note.textContent=!modeSupported?"Select MetaTrader 5 for broker password entry.":
  !available?"You can enter your broker password locally, but linking cannot submit until the private connection gateway is ready.":
  environment.value==="LIVE"&&!fpLive&&!derivLive?"LIVE MT5 password entry is enabled. This broker's LIVE terminal connection is not yet supported; do not submit your password until its broker connector is available.":
  (fpLive||derivLive)&&!liveReady?"LIVE password entry is available. FP Markets LIVE linking requires a fresh verified gateway response.":
  "Enter your MT5 trading password. A private isolated MT5 terminal will verify the broker session. No email code.";
 mainButton.textContent=existingId?"Connect Existing MT5 Account":"Connect Trading Account";
}
async function probe(){
 try{
  const response=await fetch(endpoint+"mt5/gateway",{credentials:"same-origin",cache:"no-store"});
  const data=await response.json();
  available=response.ok&&data.private_gateway_ready===true&&
   data.customer_password_login_enabled===true&&
   data.persistent_client_sessions_ready===true&&
   data.trading_authorized===false;
  liveReady=available&&data.live_mt5_login_enabled===true;
 }catch{available=false;liveReady=false}
 refresh();
}
form.addEventListener("submit",async ev=>{
 if(platform.value!=="MT5")return;
 ev.preventDefault();ev.stopImmediatePropagation();
 if(!available){
  status("No dedicated MT5 terminal connection service is available. Nothing was enrolled, saved or connected. The terminal runtime must be repaired first.",true);
  return;
 }
 if(environment.value!=="DEMO" && !(environment.value==="LIVE" && (broker.value==="FP Markets"||broker.value==="Deriv") && liveReady)){
  status("This MT5 account mode is not enabled. Nothing was enrolled or connected.",true);
  return;
 }
 if(busy)return;
 if(!ack.checked){status("Confirm the connection acknowledgement first.",true);return}
 const matched=[...server.options].some(x=>x.value===server.value);
 if(!matched||!login.value.trim()||!password.value){
  status("Enter a valid MT5 login, password and exact broker server.",true);return
 }
 const secret=password.value; password.value="";password.required=false;
 busy=true;mainButton.disabled=true;
 try{
  const response=await send("connections/mt5/connect",{
    broker:broker.value,environment:environment.value,
    account_reference:login.value.trim(),broker_server:server.value,
    password:secret,connection_id:existingId});
  if(response.connection_status==="CONNECTED" && response.persistent_broker_session===true){
   status("MT5 broker session connected. Automatic trading is still OFF.");
   window.dispatchEvent(new Event("apex:mt5-accounts-updated"));resetExisting();
  }else if(response.connection_status==="CONNECTING" && response.connection_id){
   const cid=response.connection_id;
   status("Your dedicated MT5 terminal is starting. Waiting for broker authentication. Trading remains OFF.");
   window.dispatchEvent(new Event("apex:mt5-accounts-updated"));
   let finalState="CONNECTING";
   for(let step=0;step<46;step++){
    await new Promise(resolve=>setTimeout(resolve,5000));
    const r=await fetch(endpoint+"connections/"+encodeURIComponent(cid)+"/status",
        {credentials:"same-origin",cache:"no-store"});
    const check=await r.json().catch(()=>({}));
    if(!r.ok){throw new Error(check.error||"MT5 session status unavailable. Refresh Trading Accounts.");}
    finalState=check.connection_status;
    if(finalState==="CONNECTED"&&check.persistent_broker_session===true){
      status("Connected to "+broker.value+" MT5. Your dedicated terminal is authenticated. Automatic trading remains OFF.");
      window.dispatchEvent(new Event("apex:mt5-accounts-updated"));resetExisting();break;
    }
    if(finalState==="NOT_CONNECTED"||finalState==="ERROR"){
      const why={
        WORKER_STARTUP_ERROR:"ABUTRON's MT5 terminal failed to start. This does not confirm a broker password problem.",
        MT5_TERMINAL_EXITED:"The MT5 terminal closed before broker authentication. This is a terminal-side failure, not a confirmed password rejection.",
        BROKER_AUTH_TIMEOUT:"The MT5 terminal could not confirm the broker session within the allowed time.",
        BROKER_SESSION_LOST:"The MT5 broker session was lost after connecting."
      };
      throw new Error((why[check.failure_category]||"MT5 broker authentication is not verified.")+" No automatic trading is enabled.");
    }
   }
   if(finalState==="CONNECTING"){
     status("Broker login not confirmed. Check Trading Accounts for the latest result; automatic trading remains OFF.",true);
   }
  }else{
   throw new Error("Broker session was not verified. No account was connected.");
  }
 }catch(err){status(err.message,true)}
 finally{busy=false;mainButton.disabled=false;password.value="";refresh()}
},true);
window.addEventListener("apex:mt5-auth-existing",async ev=>{
 const data=ev.detail||{};
 if(!/^[a-f0-9]{32}$/.test(data.id||""))return;
 if(data.environment!=="DEMO" && !(["FP Markets","Deriv"].includes(data.broker) && data.environment==="LIVE")){
  status("This broker mode is not supported for direct account linking.",true);return
 }
 // The previously saved account can be opened without the Add-account form.
 // Always populate broker server options before selecting the saved server.
 if(data.broker)broker.value=data.broker;
 broker.dispatchEvent(new Event("change",{bubbles:true}));
 if(data.server)server.value=data.server;
 server.dispatchEvent(new Event("change",{bubbles:true}));
 if(data.environment)environment.value=data.environment;
 login.value="";
 const wrap=form.closest(".split");
 if(wrap)wrap.hidden=false;
 existingId=data.id;
 await probe(); // Initial signed-out probe may have returned 401 before login.
 existingId=data.id;
 refresh();
 if(!available){
  status("MT5 connection service could not be reached. Try Refresh Connection Status.",true);
  return;
 }
 status("Re-enter the MT5 username and password, and verify the selected server exactly matches the broker account portal. Connecting the account does not enable automatic trading.");
 form.scrollIntoView({behavior:"smooth",block:"center"});
 password.focus({preventScroll:true});
});
[broker,environment,server,platform].forEach(el=>el?.addEventListener("change",()=>{password.value="";resetExisting();refresh()}));
const portal=document.getElementById("portalSection");
if(portal){
  new MutationObserver(()=>{
    if(!portal.hidden)probe();
    else{password.value="";available=false;liveReady=false;refresh()}
  }).observe(portal,{attributes:true,attributeFilter:["hidden"]});
}
document.addEventListener("visibilitychange",()=>{if(document.hidden)password.value="";else if(portal&&!portal.hidden)probe()});
window.addEventListener("pagehide",()=>{password.value="";});
window.addEventListener("pageshow",()=>{if(portal&&!portal.hidden)probe()});
probe();
})();
