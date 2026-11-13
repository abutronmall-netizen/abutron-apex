(()=>{"use strict";
const $=id=>document.getElementById(id),API="/account/api/client/admin/",CRM=API+"crm/";
let selected=null,allClients=[],section="overview",initializing=false,planCatalog=[];
const hidden=(id,value)=>$(id).hidden=value;
function notify(message,error=false){const el=$("toast");el.textContent=message;el.className=error?"error":"ok";el.hidden=false;window.clearTimeout(notify.timer);notify.timer=window.setTimeout(()=>{el.hidden=true},5000)}
function errorMsg(e){return e&&e.message?e.message:"Request unsuccessful"}
async function request(path,payload){const o={credentials:"same-origin",cache:"no-store"};if(payload!==undefined){o.method="POST";o.headers={"Content-Type":"application/json"};o.body=JSON.stringify(payload)}
 const r=await fetch(path,o),j=await r.json().catch(()=>({error:"Invalid server response"}));if(!r.ok){const e=new Error(j.error||"Request failed");e.status=r.status;throw e}return j}
const get=x=>request(CRM+x),post=(x,y)=>request(CRM+x,y);
function elem(tag,cls,value){const x=document.createElement(tag);if(cls)x.className=cls;if(value!==undefined)x.textContent=String(value);return x}
function empty(parent,message){parent.replaceChildren(elem("p","empty",message))}
function stateLabel(status){return ({approved:"Active",pending_review:"Unverified",disabled:"Suspended",rejected:"Closed",revoked:"Revoked",verification_pending:"Pending connection",oauth_pending:"OAuth required",CONNECTED:"Connected",DISCONNECTED:"Disconnected",active:"Active",paused:"Paused",expired:"Expired",trial:"Trial",cancelled:"Cancelled",overdue:"Overdue",due_soon:"Due soon",scheduled:"Scheduled",unscheduled:"Unscheduled",open:"Open",in_progress:"In progress",resolved:"Resolved"})[status]||status||"Not assigned"}
function pill(value){const label=stateLabel(value),x=elem("span","state "+(value==="approved"||value==="active"||value==="CONNECTED"||value==="resolved"?"good":value==="disabled"||value==="expired"||value==="cancelled"||value==="revoked"?"bad":"neutral"),label);return x}
function cell(tr,value,tag="td"){const x=elem(tag,"",value);tr.append(x);return x}
function actionButton(label,fn,cls="mini-btn"){const x=elem("button",cls,label);x.type="button";x.addEventListener("click",async()=>{x.disabled=true;try{await fn()}catch(e){notify(errorMsg(e),true)}finally{x.disabled=false}});return x}
function when(s){return s?s.slice(0,10):"—"}
function money(plan){return "R "+(plan.amount_minor/100).toLocaleString("en-ZA",{minimumFractionDigits:0,maximumFractionDigits:0})+"/month"}
function updateCommercialPrice(){
 const f=$("subscriptionForm"),plan=f.elements.namedItem("plan").value,price=planCatalog.find(x=>x.plan===plan);
 if(!price)return;
 formValue(f,"currency",price.currency);formValue(f,"amount",(price.amount_minor/100).toFixed(2));
 formValue(f,"billing_interval",price.billing_interval);
}
function updateLicensePrice(){
 const plan=$("licenseForm").elements.namedItem("plan").value;
 const price=planCatalog.find(x=>x.plan===plan);
 $("licensePriceNote").textContent=price?"Software license: "+money(price)+" · "+price.included_broker_accounts+" linked broker-account seat(s) · TRADING EQUITY NOT INCLUDED":"Price unavailable";
 if(price)formValue($("licenseForm"),"seats",price.included_broker_accounts);
}
function signedOut(){for(const key of ["loading","loginRequired","notAuthorized","mfaSection"])hidden(key,true);hidden("adminPanel",true);hidden("authShell",false)}
function authScreen(id){signedOut();hidden(id,false)}
async function startup(){if(initializing)return;initializing=true;try{const x=await request(API+"me");$("emailHint").textContent=x.email;if(x.mfa_authenticated){hidden("authShell",true);hidden("adminPanel",false);await navigate("overview")}else authScreen("mfaSection")}catch(e){authScreen(e.status===403?"notAuthorized":"loginRequired");notify(errorMsg(e),true)}finally{initializing=false}}
async function navigate(tab){section=tab;document.querySelectorAll(".tab").forEach(x=>x.hidden=x.id!=="tab-"+tab);
 document.querySelectorAll("[data-tab]").forEach(x=>x.classList.toggle("active",x.dataset.tab===tab));
 $("crumb").textContent=tab==="billing"?"Subscriptions":tab.charAt(0).toUpperCase()+tab.slice(1);
 try{if(tab==="overview")await summary();if(tab==="clients")await clients();if(tab==="brokers")await brokers();if(tab==="licenses")await licenses();if(tab==="billing")await billing();if(tab==="support")await tickets();if(tab==="activity")await activity()}catch(e){notify(errorMsg(e),true);if(e.status===401||e.status===403)await startup()}}
async function summary(){const x=await get("summary");for(const [id,v] of Object.entries({statClients:x.client_count,statActive:x.client_states?.approved||0,statLicenses:x.active_license_records,statSubs:x.active_subscription_records,statBrokers:x.broker_requests,statConnected:x.connected_deriv_demo_accounts??0,statTradingOn:x.automatic_trading_enabled_accounts??0,statTickets:x.open_tickets,statTrials:x.active_trials||0,statBuyRequests:x.purchase_requests_pending||0,statDue:x.subscription_due_soon||0,statOverdue:x.subscription_overdue||0}))$(id).textContent=String(v);drawActivity($("recentActivity"),x.recent_activity);
 const connected=Number(x.connected_deriv_demo_accounts||0),trading=Number(x.automatic_trading_enabled_accounts||0);
 const broker=$("brokerBridgeState"),execution=$("brokerExecutionState");
 broker.textContent=connected+" CONNECTED";
 broker.className="state "+(connected>0?"good":"neutral");
 execution.textContent=trading+" CRM SWITCHES ON / "+(x.connected_accounts||0)+" CONNECTED · BROKER PROOF SEPARATE";
 execution.className="state neutral";
}
function drawActivity(parent,data){parent.replaceChildren();if(!data?.length)return empty(parent,"No administrative activity yet.");for(const x of data){const row=elem("div","logline"),details=elem("div",""),name=elem("b","",x.action.replaceAll("_"," ")),desc=elem("small","",x.detail||x.subject||"Administrative change");details.append(name,desc);row.append(details,elem("time","",when(x.happened_at)));parent.append(row)}}
async function clients(){const q=$("clientSearch").value.trim(),status=$("clientFilter").value;const x=await get("clients?q="+encodeURIComponent(q)+"&status="+encodeURIComponent(status));allClients=x.clients;$("clientCount").textContent=x.clients.length+" clients";const parent=$("clientRows");parent.replaceChildren();if(!x.clients.length){const tr=elem("tr");const td=cell(tr,"No matching clients");td.colSpan=6;parent.append(tr)}
 for(const a of x.clients){const tr=elem("tr"),name=cell(tr,a.full_name);name.append(elem("small","table-sub",a.email));cell(tr,"").append(pill(a.status));cell(tr,a.segment);cell(tr,a.license_plan||"Not assigned");cell(tr,a.broker_requests);const last=cell(tr,"");last.append(actionButton("Manage →",()=>openClient(a.id)));parent.append(tr)}
 await loadTicketClientOptions();if(selected&&allClients.some(x=>x.id===selected))hidden("clientDetail",false)}
async function loadTicketClientOptions(){const select=$("ticketClient");if(select.options.length>1)return;let list=allClients;if(!list.length){try{list=(await get("clients")).clients}catch(e){return}}select.replaceChildren();select.append(elem("option","", "Select client"));select.options[0].value="";for(const x of list){const o=elem("option","",x.full_name+" — "+x.email);o.value=x.id;select.append(o)}}
function formValue(form,name,value){const input=form.elements.namedItem(name);if(input)input.value=value??""}
function detailsList(parent,records,makeText){parent.replaceChildren();if(!records?.length)return empty(parent,"No records.");for(const x of records){const block=elem("div","listitem",makeText(x));parent.append(block)}}
async function openClient(id){selected=id;const x=await get("client?id="+encodeURIComponent(id));const a=x.client,p=x.profile||{},l=x.license||{},s=x.subscription||{};planCatalog=x.pricing||planCatalog;const tr=x.trial||{},requests=x.purchase_requests||[];
 $("trialAdminState").replaceChildren(elem("div","listitem",
   tr.status==="active"?"TRIAL ACTIVE · Expires "+tr.expires_at:
   tr.status==="expired"?"TRIAL EXPIRED · Purchase required":tr.status==="owner_exempt"?"OPERATOR / SUPERADMIN · Customer trial excluded":"Trial not started — awaiting first successfully verified DEMO broker connection"));
 const requestList=$("trialCustomerRequests");requestList.replaceChildren();
 if(requests.length)for(const r of requests){requestList.append(elem("div","listitem",
  "License request: "+r.requested_plan+" · "+r.requested_seats+" seat(s) · "+r.status+" · "+r.created_at))}
 $("detailName").textContent=a.full_name;$("detailEmail").textContent=a.email+" · "+a.country+" · "+stateLabel(a.status);
 const pf=$("profileForm");for(const [k,v] of Object.entries({full_name:a.full_name,segment:p.segment||"standard",tags:p.tags||"",internal_notes:p.internal_notes||""}))formValue(pf,k,v);
 $("detailState").textContent="Access: "+stateLabel(a.status)+". Changing this status does not change broker trading permissions.";
 const btn=$("accountAction");btn.hidden=!["approved","disabled"].includes(a.status);btn.dataset.action=a.status==="approved"?"suspend":"reactivate";btn.textContent=a.status==="approved"?"Suspend access":"Reactivate access";btn.className=a.status==="approved"?"btn danger":"btn";
 const lf=$("licenseForm");for(const [k,v] of Object.entries({plan:l.plan||"Starter",status:l.status||"paused",seats:l.seats??1,expires_on:l.expires_on||"",internal_notes:l.internal_notes||""}))formValue(lf,k,v);
 $("detailLicenseCode").textContent=l.license_code||"Not assigned — a new code is generated on save";
 updateLicensePrice();
 const revoke=x.license_policy?.revocation||null;
 const control=$("licenseRevoke");
 control.disabled=!l.license_code;
 control.dataset.action=revoke?"restore":"revoke";
 control.textContent=revoke?"Clear revocation":"Revoke license";
 control.className=revoke?"btn":"btn danger";
 $("licenseRevokeReasonLabel").hidden=Boolean(revoke);
 $("licenseRevokeReason").value="";
 $("licenseRevocationNote").textContent=revoke
   ?"REVOKED "+revoke.revoked_at+" — "+revoke.reason+" · New entries denied. Existing protective exits preserved."
   :"New entries need a valid parent license and assigned broker-account seat. Existing exits are not disabled by expiry or revocation.";
 const sf=$("subscriptionForm");for(const [k,v] of Object.entries({plan:s.plan||"Starter",currency:s.currency||"ZAR",amount:((s.amount_minor||100000)/100).toFixed(2),billing_interval:s.billing_interval||"monthly",status:s.status||"trial",renewal_on:s.renewal_on||""}))formValue(sf,k,v);
 updateCommercialPrice();
 $("renewSubscriptionBtn").disabled=!s.plan||!("active"===s.status||"trial"===s.status)||s.billing_interval==="one_time";
 $("renewState").textContent=s.plan?"Renewal: "+(s.renewal_on||"Not scheduled")+" · "+(s.renewal_state||"manual record"):"Create a subscription before adjusting renewal dates.";
 $("renewNewDate").value="";$("renewReason").value="";
 const history=$("detailSubscriptionHistory");history.replaceChildren();
 if(!x.subscription_history?.length)empty(history,"No subscription changes yet.");
 for(const item of x.subscription_history||[]){const line=elem("div","listitem");line.append(elem("b","",item.action.replaceAll("_"," ")),elem("small","",item.created_at+" · "+(item.reason||"Administrative update")));history.append(line)}
 detailsList($("detailBrokers"),[...x.broker_connections.map(z=>({...z,type:"connected"})),...x.broker_requests.map(z=>({...z,type:"request"}))],z=>z.broker+" / "+z.platform??"MT5");
 const brokers=$("detailBrokers");brokers.replaceChildren();const arr=[...x.broker_connections.map(z=>({...z,platform:"MT5"})),...x.broker_requests];if(!arr.length)empty(brokers,"No broker accounts or requests.");for(const z of arr){const block=elem("div","listitem");block.append(elem("b","",z.broker+" · "+z.platform+" · "+z.environment));block.append(elem("small","",z.account_reference+" / "+z.broker_server+" / "+stateLabel(z.status)));brokers.append(block)}
 const licList=$("detailAccountLicenses");licList.replaceChildren();
 const entitlements=x.account_licenses||[];
 if(!entitlements.length)empty(licList,"No broker-account seats allocated.");
 for(const ent of entitlements){const row=elem("div","listitem");row.append(elem("b","",ent.broker+" · "+ent.platform+" · "+ent.environment+" · "+ent.account_reference));row.append(elem("small","",ent.state+" / "+ent.broker_connection_status+" / expiry "+(ent.expires_on||"none")+" / CRM effective: "+(ent.crm_entitlement_valid?"yes":"no")));
 if(ent.state==="assigned")row.append(actionButton("Pause this seat",async()=>{
    if(!window.confirm("Pause this broker-account license allocation? CRM will deny new-entry entitlement for this seat. No broker positions are closed."))return;
    await post("account-license/pause",{account_id:currentId(),allocation_id:ent.id});
    notify("Account license seat paused; existing protective orders unchanged.");await openClient(selected)
 }));
 licList.append(row)}
 const sourceSelect=$("brokerLicenseSource");sourceSelect.replaceChildren();
 for(const req of x.broker_requests){const o=elem("option","",req.broker+" / "+req.platform+" / "+req.environment+" / "+req.account_reference+" (pending)");o.value="request:"+req.id;sourceSelect.append(o)}
 for(const con of x.broker_connections){const o=elem("option","",con.broker+" / MT5 / "+con.environment+" / "+con.account_reference+" (connected)");o.value="connection:"+con.id;sourceSelect.append(o)}
 $("saveAccountLicense").disabled=!sourceSelect.options.length;
 detailsList($("detailTickets"),x.tickets,z=>z.subject+" · "+stateLabel(z.status));hidden("clientDetail",false);if(section!=="clients")await navigate("clients");$("clientDetail").scrollIntoView({behavior:"smooth",block:"start"})}
function currentId(){if(!selected)throw new Error("Select a client.");return selected}
async function saveProfile(e){e.preventDefault();const f=e.currentTarget,d=new FormData(f);await post("client/update",{account_id:currentId(),full_name:d.get("full_name"),segment:d.get("segment"),tags:d.get("tags"),internal_notes:d.get("internal_notes")});notify("Client profile saved.");await clients();await openClient(selected)}
async function actAccount(){const a=$("accountAction").dataset.action;if(!window.confirm((a==="suspend"?"Suspend":"Reactivate")+" this client's portal access?"))return;await post("client/update",{account_id:currentId(),account_action:a});notify("Account access updated.");await clients();await openClient(selected)}
async function saveLicense(e){e.preventDefault();const d=new FormData(e.currentTarget);await post("license/save",{account_id:currentId(),plan:d.get("plan"),status:d.get("status"),seats:Number(d.get("seats")),expires_on:d.get("expires_on")||null,internal_notes:d.get("internal_notes")});notify("CRM license saved.");await openClient(selected)}
async function changeRevocation(){
 const action=$("licenseRevoke").dataset.action;
 const reason=$("licenseRevokeReason").value.trim();
 if(action==="revoke" && reason.length<5)throw new Error("Enter a revocation reason (at least 5 characters).");
 if(!window.confirm(action==="revoke"?"Revoke this customer license? New trades will be denied by the CRM entitlement policy. Existing broker-side SL/TP will remain.":"Clear the license revocation? Other license, broker and trading gates still apply."))return;
 await post("license/revocation",{account_id:currentId(),action,reason});
 notify(action==="revoke"?"License revoked in CRM.":"Revocation cleared. Other trading gates remain.");
 await openClient(selected);
}
async function saveAccountLicense(e){e.preventDefault();const d=new FormData(e.currentTarget),source=String(d.get("source")||"");
 const index=source.indexOf(":");if(index<0)throw new Error("Select a broker account.");
 const source_type=source.slice(0,index),source_id=source.slice(index+1);
 await post("account-license/save",{account_id:currentId(),source_type,source_id,state:d.get("state"),expires_on:d.get("expires_on")||null});
 notify("Broker account seat updated. No trading permissions were activated.");await openClient(selected);
}
async function saveSubscription(e){e.preventDefault();const d=new FormData(e.currentTarget),number=Number(d.get("amount"));if(!Number.isFinite(number)||number<0)throw new Error("Invalid subscription amount.");await post("subscription/save",{account_id:currentId(),plan:d.get("plan"),currency:d.get("currency"),amount_minor:Math.round(number*100),billing_interval:d.get("billing_interval"),status:d.get("status"),renewal_on:d.get("renewal_on")||null});notify("Subscription record saved.");await openClient(selected)}
async function renewSubscription(){
 const id=currentId(),date=$("renewNewDate").value,reason=$("renewReason").value.trim();
 if(!date||reason.length<5)throw new Error("Provide a new renewal date and reason of at least 5 characters.");
 const current=await get("client?id="+encodeURIComponent(id));
 if(!window.confirm("Update this subscription renewal date? This records no payment and does not activate trading."))return;
 await post("subscription/renew",{account_id:id,renewal_on:date,expected_renewal_on:current.subscription?.renewal_on??null,reason});
 notify("Renewal date updated and audited. Payment not collected.");await openClient(id)
}
async function brokers(){const x=await get("brokers"),grid=$("brokerCatalog");grid.replaceChildren();for(const c of x.catalog){const card=elem("div","broker-card"),header=elem("div","broker-header");header.append(elem("strong","",c.broker),pill(c.accepting_requests?"active":"paused"));card.append(header,elem("p","",c.platform+" · "+c.request_count+" request(s)"));card.append(elem("small","",c.accepting_requests?"New account requests accepted":"New account requests paused"));const b=actionButton(c.accepting_requests?"Pause intake":"Enable intake",async()=>{const accepting=!Boolean(c.accepting_requests);await post("broker/catalog/update",{broker:c.broker,platform:c.platform,accepting_requests:accepting,notes:c.notes||""});notify("Broker intake updated — trading execution unchanged.");await brokers()});card.append(b);grid.append(card)}
 const tb=$("brokerRequests");tb.replaceChildren();if(!x.requests.length){const tr=elem("tr");cell(tr,"No broker requests").colSpan=6;tb.append(tr)}
 for(const r of x.requests){const tr=elem("tr");cell(tr,r.full_name).append(elem("small","table-sub",r.email));cell(tr,r.broker+" / "+r.platform);cell(tr,r.environment);cell(tr,r.account_reference).append(elem("small","table-sub",r.broker_server));cell(tr,"").append(pill(r.status));cell(tr,"").append(actionButton("Remove",async()=>{if(!window.confirm("Remove this pending broker-link request?"))return;await post("broker/request/remove",{request_id:r.id});notify("Request removed.");await brokers()},"mini-btn subtle"));tb.append(tr)}
 const connections=$("brokerConnections");connections.replaceChildren();if(!x.connections.length)empty(connections,"No authenticated client broker connections. Pending requests do not represent trading connections.");for(const c of x.connections){const el=elem("div","listitem");el.append(elem("b","",c.broker+" / MT5 / "+c.environment+" — "+c.account_reference));el.append(elem("small","",c.email+" · "+c.status+" · Trading "+(c.trading_enabled?"ON":"OFF")));connections.append(el)}}
function renderPurchases(items){
 const table=$("licenseRequestsRows");table.replaceChildren();
 if(!items.length){const tr=elem("tr");cell(tr,"No license purchase requests yet.").colSpan=6;table.append(tr);return}
 for(const p of items){
   const row=elem("tr");cell(row,p.full_name).append(elem("small","table-sub",p.email));
   cell(row,p.requested_plan).append(elem("small","table-sub",p.quoted_amount_minor==null?"Historical request — no quote saved":money({amount_minor:p.quoted_amount_minor})+" · "+p.requested_seats+" seat(s) · NO EQUITY"));cell(row,p.requested_seats);cell(row,"").append(pill(p.status));
   cell(row,(p.created_at||"").slice(0,16));const actions=cell(row,"");
   if(p.status==="requested"||p.status==="contacted"){
     actions.append(actionButton("Contacted",async()=>{
       await post("purchase-request/manage",{request_id:p.id,action:"contacted"});notify("Customer contact recorded.");await licenses()
     }));
     actions.append(actionButton("Activate paid license",async()=>{
       const ref=window.prompt("External payment reference (confirmed funds received):");
       if(ref===null)return;
       const expires_on=window.prompt("Paid license expiry date (YYYY-MM-DD):");
       if(expires_on===null)return;
       if(!window.confirm("I have independently confirmed payment outside ABUTRON. Activate "+p.requested_plan+" / "+p.requested_seats+" seats for "+p.email+"?"))return;
       await post("purchase-request/manage",{request_id:p.id,action:"activate",
         external_payment_confirmed:true,external_payment_reference:ref.trim(),expires_on:expires_on.trim()});
       notify("Paid license activated. Allocate broker-account seats in the client profile.");await licenses()
     }));
     actions.append(actionButton("Cancel",async()=>{
       if(!window.confirm("Cancel this license request?"))return;
       await post("purchase-request/manage",{request_id:p.id,action:"cancel"});notify("License request cancelled.");await licenses()
     },"mini-btn subtle"));
   }
   table.append(row)
 }
}
async function licenses(){const [x,buy]=await Promise.all([get("licenses"),get("purchase-requests")]);renderPurchases(buy.requests||[]);const tb=$("licenseRows"),revoked=new Set((x.revocations||[]).map(a=>a.account_id));tb.replaceChildren();if(!x.licenses.length){const tr=elem("tr");cell(tr,"No license records. Assign one from Clients.").colSpan=7;tb.append(tr)}
 for(const a of x.licenses){const tr=elem("tr");cell(tr,a.full_name).append(elem("small","table-sub",a.email));cell(tr,a.license_code);cell(tr,a.plan);cell(tr,"").append(pill(revoked.has(a.account_id)?"revoked":(a.effective_status||a.status)));cell(tr,a.seats);cell(tr,a.expires_on||"No expiry");cell(tr,"").append(actionButton("Edit →",()=>openClient(a.account_id)));tb.append(tr)}
 const allocations=$("accountLicenseRows");allocations.replaceChildren();
 if(!x.account_licenses?.length){const tr=elem("tr");cell(tr,"No account allocations yet.").colSpan=6;allocations.append(tr)}
 for(const e of x.account_licenses||[]){const tr=elem("tr");cell(tr,e.full_name).append(elem("small","table-sub",e.email));cell(tr,e.broker+" / "+e.platform+" / "+e.account_reference);cell(tr,e.environment);cell(tr,"").append(pill(e.state));cell(tr,e.broker_connection_status);cell(tr,"").append(actionButton("Manage →",()=>openClient(e.account_id)));allocations.append(tr)}}
async function billing(){const x=await get("subscriptions"),tb=$("subscriptionRows");planCatalog=x.pricing||planCatalog;
 const priceList=$("pricingOverview");priceList.replaceChildren();
 for(const p of planCatalog){const item=elem("div","listitem");item.append(elem("b","",p.plan),elem("small","",money(p)+" · "+p.included_broker_accounts+" linked broker-account seat(s) · NO TRADING EQUITY INCLUDED"));priceList.append(item)}
 tb.replaceChildren();if(!x.subscriptions.length){const tr=elem("tr");cell(tr,"No subscription records. Add one from Clients.").colSpan=7;tb.append(tr)}
 for(const a of x.subscriptions){const tr=elem("tr");cell(tr,a.full_name).append(elem("small","table-sub",a.email));cell(tr,a.plan);cell(tr,a.currency+" "+(a.amount_minor/100).toFixed(2));cell(tr,a.billing_interval);cell(tr,"").append(pill(a.renewal_state==="overdue"?"overdue":a.status));cell(tr,(a.renewal_on||"—")+" · "+(a.renewal_state||"unknown"));cell(tr,"").append(actionButton("Edit →",()=>openClient(a.account_id)));tb.append(tr)}}
async function tickets(){await loadTicketClientOptions();const x=await get("tickets"),list=$("ticketList");list.replaceChildren();if(!x.tickets.length)return empty(list,"No support cases have been created.");
 for(const t of x.tickets){const item=elem("article","ticket");const top=elem("div","ticket-top");top.append(elem("strong","",t.subject),pill(t.status));item.append(top,elem("small","",t.full_name+" · "+t.email+" · "+t.priority+" priority"));const note=elem("textarea","");note.value=t.internal_notes||"";note.maxLength=2000;note.rows=2;item.append(note);const actions=elem("div","form-actions");const select=elem("select");for(const [v,name] of [["open","Open"],["in_progress","In progress"],["resolved","Resolved"]]){const opt=elem("option","",name);opt.value=v;opt.selected=v===t.status;select.append(opt)}actions.append(select,actionButton("Save ticket",async()=>{await post("ticket/update",{ticket_id:t.id,status:select.value,internal_notes:note.value});notify("Ticket updated.");await tickets()}));item.append(actions);list.append(item)}}
async function createTicket(e){e.preventDefault();const d=new FormData(e.currentTarget);if(!d.get("account_id"))throw new Error("Select a client.");await post("ticket/create",{account_id:d.get("account_id"),subject:d.get("subject"),priority:d.get("priority"),internal_notes:d.get("internal_notes")});e.currentTarget.reset();notify("Support case created.");await tickets()}
async function activity(){drawActivity($("activityList"),(await get("activity")).activity)}
function withErrors(fn){return async e=>{try{await fn(e)}catch(err){notify(errorMsg(err),true)}}}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.tab)));
document.querySelectorAll("[data-goto]").forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.goto)));
$("refreshBtn").addEventListener("click",()=>navigate("overview"));
$("clientRefresh").addEventListener("click",()=>clients().catch(e=>notify(errorMsg(e),true)));
$("clientSearch").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();clients().catch(x=>notify(errorMsg(x),true))}});
$("clientFilter").addEventListener("change",()=>clients().catch(e=>notify(errorMsg(e),true)));
$("closeDetail").addEventListener("click",()=>{selected=null;hidden("clientDetail",true)});
$("profileForm").addEventListener("submit",withErrors(saveProfile));
$("licenseForm").addEventListener("submit",withErrors(saveLicense));
$("licenseRevoke").addEventListener("click",withErrors(changeRevocation));
$("subscriptionForm").addEventListener("submit",withErrors(saveSubscription));
$("subscriptionForm").elements.namedItem("plan").addEventListener("change",updateCommercialPrice);
$("licenseForm").elements.namedItem("plan").addEventListener("change",updateLicensePrice);
$("renewSubscriptionBtn").addEventListener("click",withErrors(renewSubscription));
$("brokerLicenseForm").addEventListener("submit",withErrors(saveAccountLicense));
$("accountAction").addEventListener("click",withErrors(actAccount));
$("newTicketForm").addEventListener("submit",withErrors(createTicket));
$("requestCode").addEventListener("click",withErrors(async()=>{const d=await request(API+"mfa/request",{});notify(d.message||"Code requested.")}));
$("verifyForm").addEventListener("submit",withErrors(async e=>{e.preventDefault();const code=$("verificationCode").value.trim();await request(API+"mfa/verify",{code});$("verificationCode").value="";await startup()}));
$("endAdmin").addEventListener("click",withErrors(async()=>{await request(API+"logout",{});await startup();notify("Admin session ended.")}));
startup();
})();