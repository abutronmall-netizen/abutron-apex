/* ABUTRON Client Workspace: visual/navigation shell only. Existing client API remains authoritative. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const portal = $("portalSection");
  if (!portal || !window.MutationObserver) return;
  const iconPaths = {
    dashboard:'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    trading:'<path d="M3 17l6-6 4 4 8-9"/><path d="M15 6h6v6"/>',
    accounts:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 10h18M7 15h4"/>',
    trades:'<path d="M4 4v16h16"/><path d="M7 14l4-5 3 3 5-7"/>',
    licenses:'<circle cx="8" cy="12" r="4"/><path d="M12 12h9m-3 0v3m-3-3v3"/>',
    subscriptions:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h3"/>',
    notifications:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    prop:'<path d="m3 10 9-7 9 7M5 10v10h14V10M9 20v-7h6v7"/>',
    profile:'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-5 3-7 8-7s8 2 8 7"/>',
    support:'<path d="M4 13v-2a8 8 0 0 1 16 0v2M4 13H2v5h4v-5H4m16 0h2v5h-4v-5h2m0 5c0 3-3 4-7 4"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    link:'<path d="M5 12h14m-5-5 5 5-5 5"/>'
  };
  const svg = (name,size=19) => '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+(iconPaths[name]||iconPaths.dashboard)+'</svg>';
  const definitions = [
    {id:"dashboard",name:"Dashboard",description:"Your ABUTRON account at a glance"},
    {id:"trading",name:"Trading",description:"Independent account-specific trading controls"},
    {id:"accounts",name:"Trading accounts",description:"Link and manage existing broker accounts"},
    {id:"trades",name:"Trade history",description:"Broker-sourced open and closed trades"},
    {id:"licenses",name:"Licenses",description:"Your ABUTRON software license and free trial"},
    {id:"subscriptions",name:"Subscriptions",description:"Your current subscription and billing status"},
    {id:"notifications",name:"Notifications",description:"Account notifications"},
    {id:"prop",name:"Prop Firm",description:"Prop Firm account information"},
    {id:"profile",name:"Profile & security",description:"Your registered details and account security"},
    {id:"support",name:"Support",description:"Getting help with your ABUTRON account"}
  ];
  const create = (tag,className,text) => {
    const el=document.createElement(tag);
    if(className) el.className=className;
    if(text!==undefined) el.textContent=text;
    return el;
  };
  const shell=create("div","apex-workspace");
  const sidebar=create("aside","apex-sidebar");
  sidebar.setAttribute("aria-label","Client navigation");
  const sideBrand=create("div","apex-side-brand");
  sideBrand.innerHTML='<span class="apex-side-mark" aria-hidden="true">A</span><span><strong>ABUTRON</strong><small>CLIENT WORKSPACE</small></span>';
  sidebar.append(sideBrand);
  sidebar.append(create("p","apex-nav-label","WORKSPACE"));
  const navigation=create("nav","apex-side-links");
  navigation.setAttribute("aria-label","Client sections");
  definitions.forEach(def => {
    const btn=create("button","apex-side-link");
    btn.type="button"; btn.dataset.view=def.id;
    btn.innerHTML=svg(def.id)+'<span>'+def.name+'</span>';
    btn.addEventListener("click",()=>activate(def.id));
    navigation.append(btn);
  });
  sidebar.append(navigation);
  const sideFoot=create("div","apex-side-foot");
  sideFoot.innerHTML='<span class="apex-session-dot" aria-hidden="true"></span><span>Secure account session</span>';
  sidebar.append(sideFoot);
  const main=create("div","apex-main");
  const toolbar=create("div","apex-toolbar");
  const menuBtn=create("button","apex-menu-toggle");
  menuBtn.type="button"; menuBtn.setAttribute("aria-label","Open navigation");
  menuBtn.setAttribute("aria-expanded","false");
  menuBtn.innerHTML=svg("menu",22);
  menuBtn.addEventListener("click",()=>setMenu(!shell.classList.contains("menu-open")));
  const titleArea=create("div","apex-toolbar-labels");
  const eyebrow=create("span","apex-overline","ABUTRON / CLIENT WORKSPACE");
  const screenTitle=create("h1","apex-screen-title","Dashboard");
  const screenSubtitle=create("p","apex-screen-subtitle","Your ABUTRON account at a glance");
  titleArea.append(eyebrow,screenTitle,screenSubtitle);
  const headerRight=create("div","apex-toolbar-right");
  const badge=create("span","apex-privacy-chip","PRIVATE ACCOUNT");
  headerRight.append(badge);
  toolbar.append(menuBtn,titleArea,headerRight);
  const content=create("div","apex-content");
  const views={};
  definitions.forEach(def => {
    const section=create("section","apex-view");
    section.id="apex-view-"+def.id;section.dataset.view=def.id;
    section.setAttribute("aria-label",def.name);
    section.hidden=true;
    views[def.id]=section;content.append(section);
  });
  const top=portal.querySelector(".account-top");
  const stats=portal.querySelector(".stats");
  const shop=$("licenseShop");
  const accounts=portal.querySelector(".split");
  const controls=portal.querySelector(".trade-controls");
  if(!top||!stats||!shop||!accounts||!controls)return;
  views.dashboard.append(top,stats);
  const actionBar=create("div","apex-action-bar");
  actionBar.innerHTML='<div><strong>Manage your trading workspace</strong><p>Broker account access and software subscriptions are managed separately.</p></div>';
  const actionBtns=create("div","apex-action-buttons");
  const makeJump=(label,view,primary=false)=>{
    const b=create("button","apex-action "+(primary?"accent":""),label);
    b.type="button";b.addEventListener("click",()=>activate(view));return b;
  };
  actionBtns.append(makeJump("Add broker account","accounts",true),makeJump("Trading controls","trading"));
  actionBar.append(actionBtns);
  const information=create("div","apex-info-grid");
  const panels=[
    ["ACCOUNT CONNECTIONS","Accounts are connected only after real broker authorization. A submitted request is not an active connection."],
    ["BALANCE & EQUITY","Account balances, margin and P&L will appear when a broker data connection is available. No estimates are shown."],
    ["RECENT TRADES","Open and closed broker trades will appear here once the account-specific history API is connected."]
  ];
  panels.forEach(([heading,desc])=>{
    const card=create("div","apex-info-card");
    card.append(create("span","apex-overline",heading),create("p","",desc));
    information.append(card);
  });
  views.dashboard.append(actionBar,information);
  const tradingHead=create("div","apex-section-head");
  tradingHead.append(create("h2","","Your trading controls"),create("p","","Each broker account has its own independent DEMO or LIVE trading authorization. OFF means no new automated orders for that account; it does not close existing positions."));
  views.trading.append(tradingHead,controls);
  const accountsHead=create("div","apex-section-head");
  accountsHead.append(create("h2","","Connect your broker account"),create("p","","Select Deriv, IC Markets or FP Markets, then choose the supported platform and account environment. Account linking does not activate trading."));
  const brokerTiles=create("div","apex-broker-tiles");
  [["Deriv","Deriv MT5"],["IC Markets","MT5 / cTrader"],["FP Markets","MT5 / cTrader"]].forEach(([broker,platform])=>{
    const tile=create("button","apex-broker-tile");
    tile.type="button";
    const letter=broker==="Deriv"?"D":broker==="IC Markets"?"IC":"FP";
    tile.innerHTML='<span class="apex-broker-letter">'+letter+'</span><span><strong>'+broker+'</strong><small>'+platform+'</small></span>';
    tile.addEventListener("click",()=>{
      $("broker").value=broker;
      $("broker").dispatchEvent(new Event("change",{bubbles:true}));
      $("broker").focus();
      accounts.scrollIntoView({behavior:"smooth",block:"start"});
    });
    brokerTiles.append(tile);
  });
  views.accounts.append(accountsHead,brokerTiles,accounts);
  views.licenses.append(shop);
  const history=create("div","apex-placeholder panel");
  history.innerHTML='<span class="eyebrow">TRADE HISTORY</span><h2>Your open and closed trades</h2><p>Search, sort and filter trades by date, symbol, side, volume, entry, exit, status and P&amp;L when authenticated broker-history data is available.</p><div class="apex-unavailable"><strong>No verified trade history available</strong><span>The ABUTRON customer API does not yet expose account-specific broker trades. No sample trades or fabricated balances are shown.</span></div>';
  views.trades.append(history);
  const subscription=create("div","panel apex-placeholder");
  subscription.innerHTML='<span class="eyebrow">BILLING / SUBSCRIPTIONS</span><h2>Your subscription</h2><div class="apex-detail-grid"><div><span class="apex-detail-caption">Current subscription</span><strong id="apexSubPlan">Not assigned</strong></div><div><span class="apex-detail-caption">Renewal / billing</span><strong id="apexSubNote">Managed by ABUTRON Admin</strong></div></div><p>Subscriptions are currently administered by ABUTRON CRM. Online checkout and automatic payment processing are not connected.</p>';
  subscription.append(makeJump("View license options","licenses",true));
  views.subscriptions.append(subscription);
  const notify=create("div","panel apex-placeholder");
  notify.innerHTML='<span class="eyebrow">NOTIFICATIONS</span><h2>Account notifications</h2><div class="apex-unavailable"><strong>No notification feed connected</strong><span>ABUTRON customer notifications have not yet been connected to this view. Important account changes remain in the relevant account sections.</span></div>';
  views.notifications.append(notify);
  const prop=create("div","panel apex-placeholder");
  prop.innerHTML='<span class="eyebrow">PROP FIRM</span><h2>Abutron Prop Firm</h2><p>Your Prop Firm membership and challenge information will be accessible here after that service is connected to the ABUTRON customer identity.</p><div class="apex-unavailable"><strong>Not linked</strong><span>No Prop Firm account information is available through the current ABUTRON customer API.</span></div>';
  views.prop.append(prop);
  const profile=create("div","panel apex-placeholder");
  profile.innerHTML='<span class="eyebrow">ACCOUNT / PROFILE</span><h2>Your profile &amp; security</h2><div class="apex-detail-grid"><div><span class="apex-detail-caption">Name</span><strong id="apexProfileName">—</strong></div><div><span class="apex-detail-caption">Email address</span><strong id="apexProfileEmail">—</strong></div><div><span class="apex-detail-caption">Account status</span><strong id="apexProfileStatus">—</strong></div><div><span class="apex-detail-caption">Authentication</span><strong>Protected client session</strong></div></div><p>Profile editing and address updates are not yet connected. For security, passwords and broker credentials are never displayed here.</p><a class="button secondary apex-inline-action" href="/account/reset/">Reset password</a>';
  views.profile.append(profile);
  const support=create("div","panel apex-placeholder");
  support.innerHTML='<span class="eyebrow">CUSTOMER SUPPORT</span><h2>ABUTRON support</h2><p>For help with account sign-in, start with password recovery. Broker linking requests and licenses can be checked in their corresponding sections.</p><div class="apex-unavailable"><strong>Customer support tickets not yet connected</strong><span>The CRM has internal support records, but the customer self-service ticket endpoint has not been implemented. A ticket cannot be submitted from this view yet.</span></div><a class="button secondary apex-inline-action" href="/account/reset/">Password recovery</a>';
  views.support.append(support);
  main.append(toolbar,content);
  shell.append(sidebar,main);
  portal.append(shell);
  let current="";
  function setMenu(open) {
    shell.classList.toggle("menu-open",open);
    menuBtn.setAttribute("aria-expanded",String(open));
    menuBtn.setAttribute("aria-label",open?"Close navigation":"Open navigation");
  }
  function updateReadouts() {
    $("apexSubPlan").textContent=$("crmSubscription").textContent||"Not assigned";
    $("apexSubNote").textContent=$("crmSubscriptionNote").textContent||"Managed by ABUTRON Admin";
    $("apexProfileName").textContent=$("clientName").textContent||"—";
    $("apexProfileEmail").textContent=$("clientEmail").textContent||"—";
    $("apexProfileStatus").textContent=$("accountStatus").textContent||"—";
  }
  function activate(id,scroll=true) {
    if (!views[id]) id="dashboard";
    current=id;
    definitions.forEach(def=>{
      const active=def.id===id;
      views[def.id].hidden=!active;
      const button=navigation.querySelector('[data-view="'+def.id+'"]');
      button.classList.toggle("active",active);
      if (active) button.setAttribute("aria-current","page");
      else button.removeAttribute("aria-current");
    });
    const def=definitions.find(x=>x.id===id);
    screenTitle.textContent=def.name;
    screenSubtitle.textContent=def.description;
    updateReadouts();
    setMenu(false);
    if (location.hash!=="#"+id) window.history.replaceState(null,"","#"+id);
    if(scroll)window.scrollTo({top:0,behavior:"instant"});
  }
  window.addEventListener("hashchange",()=>{
    const value=location.hash.replace(/^#/,"");
    if(views[value] && value!==current)activate(value);
  });
  const syncAuth=()=>{
    const signedIn=!portal.hidden;
    document.body.classList.toggle("apex-authenticated",signedIn);
    if(signedIn)updateReadouts();
    if(!signedIn)setMenu(false);
  };
  new MutationObserver(syncAuth).observe(portal,{attributes:true,attributeFilter:["hidden"]});
  const readouts=[$("crmSubscription"),$("crmSubscriptionNote"),$("clientName"),$("clientEmail"),$("accountStatus")];
  readouts.forEach(el=>{if(el)new MutationObserver(updateReadouts).observe(el,{childList:true,characterData:true,subtree:true})});
  activate(location.hash.substring(1)||"dashboard",false);
  syncAuth();
})();