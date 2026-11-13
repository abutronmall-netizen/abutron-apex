/* ABUTRON MT5 Account Manager v1
 * Broker account management. Real CONNECTED requires an authenticated,
 * isolated persistent client MT5 terminal. No enrollment-only workflow.
 */
(()=>{
"use strict";
const $=id=>document.getElementById(id);
const view=$("apex-view-accounts"), form=$("brokerForm"), oldSplit=view?.querySelector(".split");
if(!view||!form||!oldSplit)return;
const names=[
  {id:"Deriv",short:"DV",title:"DERIV MT5 ACCOUNTS",desc:"Deriv (BVI) Ltd. · Deriv (SVG) LLC · Deriv Demo"},
  {id:"IC Markets",short:"IC",title:"IC MARKETS MT5 ACCOUNTS",desc:"IC Markets SC · Live and Demo"},
  {id:"FP Markets",short:"FP",title:"FP MARKETS MT5 ACCOUNTS",desc:"FP Markets SC · Live and Demo"}
];
const servers={
  "Deriv":[{name:"DerivBVI-Server-02",env:"LIVE",entity:"Deriv (BVI) Ltd."},
           {name:"DerivSVG-Server",env:"LIVE",entity:"Deriv (SVG) LLC"},
           {name:"Deriv-Demo",env:"DEMO",entity:"Deriv Demo"}],
  "IC Markets":[{name:"ICMarketsSC-MT5-3",env:"LIVE",entity:"IC Markets"},
                {name:"ICMarketsSC-Demo",env:"DEMO",entity:"IC Markets"}],
  "FP Markets":[{name:"FPMarketsSC-Demo",env:"DEMO",entity:"FP Markets SC"},
                {name:"FPMarketsSC-Demo Server",env:"DEMO",entity:"FP Markets SC"},
                {name:"FPMarketsSC-Live",env:"LIVE",entity:"FP Markets SC"},
                {name:"FPMarketsLtd-Demo2",env:"DEMO",entity:"FP Markets Ltd."},
                {name:"FPMarketsLtd-Live2",env:"LIVE",entity:"FP Markets Ltd."}]
};
const statusLabels={
  CONNECTED:"Connected",CONNECTING:"Not connected · previous attempt",ERROR:"Connection error",
  DISCONNECTED:"Disconnected",NOT_CONNECTED:"Not connected"
};
const api="/account/api/client/";
const el=(tag,cls,text)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x};
const root=el("section","apex-mt5-manager");
root.id="apexMt5Manager";
const title=el("div","apex-mt5-heading");
title.innerHTML='<div><span class="eyebrow">TRADING ACCOUNTS / META TRADER 5</span><h2>MetaTrader 5 Accounts</h2><p>View each broker account, add an MT5 login, or disconnect a broker session. DEMO and LIVE are separate accounts.</p></div>';
const refreshBtn=el("button","apex-mt5-refresh","Refresh accounts");
refreshBtn.type="button";refreshBtn.addEventListener("click",refresh);
title.append(refreshBtn);
root.append(title);
const summary=el("div","apex-mt5-summary");
summary.setAttribute("aria-live","polite");
root.append(summary);
const cards=el("div","apex-mt5-broker-grid");
const lists={};
const counts={};
for(const broker of names){
  const card=el("section","apex-mt5-broker");
  const head=el("div","apex-mt5-broker-head");
  const emblem=el("span","apex-mt5-emblem",broker.short);
  const labels=el("div","apex-mt5-broker-labels");
  labels.append(el("h3","",broker.title),el("p","",broker.desc));
  const count=el("span","apex-mt5-count","0 connected");
  counts[broker.id]=count;
  head.append(emblem,labels,count);
  const list=el("div","apex-mt5-list");
  lists[broker.id]=list;
  const add=el("button","apex-mt5-add","＋ Connect Trading Account");
  add.type="button";
  add.addEventListener("click",()=>openForm(broker.id));
  card.append(head,list,add);
  cards.append(card);
}
root.append(cards);
const message=el("p","apex-mt5-message");
message.id="mt5ManagerNotice";
message.hidden=true;
message.setAttribute("role","status");
root.append(message);
const setMessage=(text,isError=false)=>{
  message.hidden=!text;message.textContent=text||"";
  message.classList.toggle("error",isError);
};
view.insertBefore(root,oldSplit);
const brokerSelect=$("broker");
const platformSelect=$("platform");
platformSelect.value="MT5";
const platformLabel=platformSelect.closest("label");
if(platformLabel)platformLabel.hidden=true;
const envSelect=form.elements.namedItem("environment");
const loginInput=form.elements.namedItem("account_reference");
const serverOld=form.elements.namedItem("broker_server");
const serverSelect=el("select");
serverSelect.id="mt5Server";
serverSelect.name="broker_server";
serverSelect.required=true;
serverOld.replaceWith(serverSelect);
const nameLabel=loginInput.closest("label");
if(nameLabel){
  nameLabel.childNodes.forEach(n=>{if(n.nodeType===Node.TEXT_NODE&&n.textContent.includes("Broker account number"))n.textContent="Username (MT5 login number)"});
}
loginInput.setAttribute("inputmode","numeric");
loginInput.setAttribute("pattern","[0-9]{4,20}");
loginInput.setAttribute("minlength","4");
loginInput.setAttribute("maxlength","20");
loginInput.setAttribute("placeholder","Your MT5 login number");
const passwordRow=el("label","apex-mt5-password","Password (MT5 broker password)");
const password=el("input");
password.id="mt5Password";
password.type="password";
password.autocomplete="off";
password.placeholder="Enter the MT5 trading password for this broker account";
password.disabled=true;
passwordRow.append(password);
const passwordHelp=el("small","apex-mt5-password-note",
  "Your MT5 password is transmitted to an isolated MT5 terminal, not saved in CRM. Choose the broker-issued DEMO or LIVE server. Linking a LIVE account never enables automatic LIVE trading.");
passwordRow.append(passwordHelp);
const serverLabel=serverSelect.closest("label");
if(serverLabel) serverLabel.insertAdjacentElement("afterend",passwordRow);
const entityRow=el("label","apex-mt5-entity");
entityRow.id="mt5BrokerEntity";
entityRow.append(document.createTextNode("Broker legal entity"));
const entitySelect=el("select");
entitySelect.id="mt5EntitySelect";
entityRow.append(entitySelect);
if(serverLabel)serverLabel.insertAdjacentElement("afterend",entityRow);
const formNotice=el("div","apex-mt5-form-notice");
formNotice.textContent="Connect your MT5 account directly. ABUTRON shows Connected only after your dedicated terminal confirms and maintains a broker session. Automatic trading stays OFF.";
form.prepend(formNotice);
const formWrap=oldSplit.querySelector("section");
const formHead=formWrap?.querySelector("h2");
if(formHead)formHead.textContent="Connect MT5 Trading Account";
const formDesc=formWrap?.querySelector("p");
if(formDesc)formDesc.textContent="Select Deriv, IC Markets or FP Markets. Enter MT5 username, broker password and exact server, then Connect Trading Account. Each connected account has its own terminal; no additional email code.";
const formSwitch=el("div","apex-mt5-form-header");
formSwitch.append(el("span","eyebrow","ADD TRADING ACCOUNT"));
const closeBtn=el("button","apex-mt5-close","Close form ×");
closeBtn.type="button";closeBtn.addEventListener("click",()=>closeForm());
formSwitch.append(closeBtn);
formWrap.prepend(formSwitch);
oldSplit.classList.add("apex-mt5-form-wrap");
oldSplit.hidden=true;
const trustedServer=()=>servers[brokerSelect.value]||servers["Deriv"];
function populateServers(desired){
  const options=trustedServer();
  const entityNames=[...new Set(options.map(x=>x.entity))];
  entitySelect.replaceChildren();
  for(const name of entityNames){const opt=el("option","",name);opt.value=name;entitySelect.append(opt)}
  serverSelect.replaceChildren();
  for(const record of options){
    const option=el("option","",record.name);
    option.value=record.name;
    serverSelect.append(option);
  }
  const matching=options.find(v=>v.name===desired);
  serverSelect.value=(matching||options.find(v=>v.env===envSelect.value)||options[0]).name;
  updateServer();
}
function updateServer(){
  const item=trustedServer().find(v=>v.name===serverSelect.value);
  if(!item)return;
  envSelect.value=item.env;
  entitySelect.value=item.entity;
}
entitySelect.addEventListener("change",()=>{
  const selected=trustedServer().find(x=>x.entity===entitySelect.value);
  if(selected)serverSelect.value=selected.name;
  updateServer();
});
serverSelect.addEventListener("change",updateServer);
brokerSelect.addEventListener("change",()=>populateServers());
envSelect.addEventListener("change",()=>{
 const match=trustedServer().find(v=>v.env===envSelect.value);
 if(match)serverSelect.value=match.name;
 updateServer();
});
function openForm(broker){
  brokerSelect.value=broker;
  brokerSelect.dispatchEvent(new Event("change",{bubbles:true}));
  platformSelect.value="MT5";
  envSelect.value="DEMO";
  populateServers(servers[broker].find(v=>v.env==="DEMO")?.name);
  oldSplit.hidden=false;
  root.classList.add("adding");
  formWrap?.scrollIntoView({behavior:"smooth",block:"start"});
  loginInput.focus({preventScroll:true});
}
function closeForm(){
  oldSplit.hidden=true;
  root.classList.remove("adding");
  password.value="";
  form.reset();
}
function safeRef(value){
 const s=String(value||"");
 return s.includes("•")?s:"••••"+s.slice(-4);
}
function connectionStatus(r){
 if(r.connection_status==="CONNECTED"&&r.broker_verified===true)return "Connected";
 if(r.connection_status==="CONNECTED")return "Awaiting broker verification";
 if(r.last_native_login_proof_at && r.connection_status==="CONNECTING")return "Login verified · session offline";
 return statusLabels[r.connection_status]||"Not authenticated";
}
function row(r,kind){
  const isLinked=kind==="connection";
  const ok=isLinked&&r.connection_status==="CONNECTED"&&r.broker_verified===true;
  const item=el("article","apex-mt5-account"+(ok?" connected":""));
  const top=el("div","apex-mt5-account-top");
  const data=el("div","apex-mt5-account-details");
  const reference=isLinked?r.account_reference_masked:safeRef(r.account_reference);
  const account=el("strong","",reference||"MT5 account");
  const meta=el("span","",String(r.environment)+" · "+String(r.broker_server));
  const status=el("span","apex-mt5-status "+(ok?"connected":"pending"),isLinked?connectionStatus(r):"Pending linking request");
  data.append(account,meta);
  top.append(data,status);
  const foot=el("div","apex-mt5-account-bottom");
  const detail=el("span","",ok?"Broker session verified · Trading permission is separate":
    isLinked&&r.connection_status==="ERROR"?"Broker error · Trading OFF":
    isLinked&&r.last_native_login_proof_at?"Previous login proof only · No persistent connection · Trading OFF":
    "No authenticated MT5 terminal · Trading OFF");
  const btn=el("button","apex-mt5-disconnect","Disconnect Trading Account");
  btn.type="button";
  const isPast=isLinked&&r.connection_status==="DISCONNECTED";
  btn.disabled=isPast;
  if(isPast)btn.textContent="Disconnected";
  btn.addEventListener("click",async()=>{
    if(!window.confirm("Disconnect "+r.broker+" MT5 account "+String(reference)+"? This removes the previous ABUTRON account record. Active broker sessions must be stopped by the isolated execution gateway first."))return;
    btn.disabled=true;
    try{
      const target=isLinked?"connections/":"requests/";
      const response=await fetch(api+target+encodeURIComponent(r.id),{
        method:"DELETE",credentials:"same-origin",cache:"no-store",
        headers:{"Accept":"application/json"}
      });
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(body.error||"Broker account could not be disconnected.");
      setMessage("Trading account disconnected from ABUTRON. Any active broker orders remain subject to the broker execution gateway.");
      await refresh();
      window.dispatchEvent(new Event("apex:mt5-disconnected"));
    }catch(e){
      setMessage(e.message||"Unable to disconnect the account.",true);
    }finally{btn.disabled=false}
  });
  if(isLinked&&(r.connection_status==="CONNECTING"||r.connection_status==="ERROR")){
    const verifyBtn=el("button","apex-mt5-add",
      r.connection_status==="ERROR"?"Retry MT5 Connection":"Connect MT5 Trading Account");
    verifyBtn.type="button";
    verifyBtn.addEventListener("click",()=>window.dispatchEvent(
      new CustomEvent("apex:mt5-auth-existing",{detail:{id:r.id,broker:r.broker,
        environment:r.environment,server:r.broker_server}})));
    foot.append(verifyBtn);
  }
  foot.append(detail,btn);
  item.append(top,foot);
  return item;
}
let refreshing=false;
async function refresh(){
  if(refreshing||view.closest("#portalSection")?.hidden)return;
  refreshing=true;
  refreshBtn.disabled=true;
  try {
    const [a,b]=await Promise.all([
      fetch(api+"connections",{credentials:"same-origin",cache:"no-store"}),
      fetch(api+"requests",{credentials:"same-origin",cache:"no-store"})
    ]);
    if(!a.ok||!b.ok)throw new Error("Could not load your MT5 accounts. Refresh or sign in again.");
    const live=await a.json(),requests=await b.json();
    const accounts=(live.connections||[]).filter(x=>x.platform==="MT5"&&x.connection_status!=="DISCONNECTED");
    const pending=(requests.requests||[]).filter(x=>x.platform==="MT5");
    let verified=0;
    for(const broker of names){
      const active=accounts.filter(x=>x.broker===broker.id);
      const waiting=pending.filter(x=>x.broker===broker.id);
      const count=active.filter(x=>x.connection_status==="CONNECTED"&&x.broker_verified===true).length;
      verified+=count;
      counts[broker.id].textContent=count+" connected";
      const list=lists[broker.id];
      list.replaceChildren();
      for(const record of active)list.append(row(record,"connection"));
      for(const record of waiting)list.append(row(record,"request"));
      if(!active.length&&!waiting.length){
        const empty=el("p","apex-mt5-empty","No connected MT5 accounts. Choose Connect Trading Account.");
        list.append(empty);
      }
    }
    summary.textContent=verified+" verified MT5 connection"+(verified===1?"":"s")+" · "+(accounts.length+pending.length-verified)+" previously saved, not connected";
  }catch(err){
    summary.textContent="Account list unavailable";
    setMessage(err.message||"Failed to load broker accounts",true);
  }finally{refreshing=false;refreshBtn.disabled=false}
}
window.addEventListener("apex:mt5-accounts-updated",refresh);
window.addEventListener("apex:mt5-disconnected",refresh);
const watcher=new MutationObserver(()=>{
  if(!$("portalSection").hidden)refresh();
});
watcher.observe($("portalSection"),{attributes:true,attributeFilter:["hidden"]});
const nav=document.querySelector('.apex-side-link[data-view="accounts"]');
if(nav)nav.addEventListener("click",refresh);
form.addEventListener("submit",()=>{
  if(form.checkValidity()){
    window.setTimeout(()=>{refresh();},1200);
  }
});
if(!$("portalSection").hidden)refresh();
})();
