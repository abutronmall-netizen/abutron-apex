/* APEX-owned Deriv MT5 DEMO Account Center extension.
 * No edits to third-party Vue bundles or their broker execution routes.
 * Adds a native-looking account rail entry and same-origin read-only panel.
 */
(() => {
  'use strict';
  const PATH='/apex/deriv/?embedded=1';
  const RAIL='data-apex-deriv-rail';
  const MENU='data-apex-deriv-dropdown';
  const FRAME='data-apex-deriv-frame';
  let active=false;
  let pending=false;
  const styles=[
    '.apex-deriv-logo{display:inline-flex;width:24px;height:24px;align-items:center;',
    'justify-content:center;background:#e53358;color:#fff;font-weight:800;',
    'border-radius:50%;font-size:15px;flex:0 0 24px}',
    '.apex-deriv-menu-logo{width:16px;height:16px;font-size:11px;margin-right:7px;flex-basis:16px}',
    /* QuantDinger Vue uses scoped styles: injected elements need explicit matching CSS. */
    '.broker-accounts [data-apex-deriv-rail]{width:100%;min-height:58px;',
    'padding:8px 10px;display:flex;align-items:center;gap:10px;',
    'border:0;border-radius:9px;background:transparent;color:inherit;',
    'text-align:left;cursor:pointer;box-sizing:border-box;}',
    '.broker-accounts [data-apex-deriv-rail]:hover{background:#1a2636;}',
    '.broker-accounts [data-apex-deriv-rail] .ba-provider-icon{',
    'display:inline-flex;align-items:center;justify-content:center;',
    'width:34px;height:34px;flex:0 0 34px;border-radius:9px;',
    'background:#301b2c;border:1px solid #553244;}',
    '.broker-accounts [data-apex-deriv-rail] .ba-provider-copy{',
    'display:flex;flex-direction:column;gap:3px;min-width:0;overflow:hidden;flex:1 1 auto;}',
    '.broker-accounts [data-apex-deriv-rail] .ba-provider-copy strong{',
    'display:block;font-size:13px;font-weight:650;line-height:18px;',
    'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:inherit;}',
    '.broker-accounts [data-apex-deriv-rail] .ba-provider-copy small{',
    'display:block;font-size:11px;line-height:16px;min-height:16px;',
    'color:#9da9ba;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
    '.broker-accounts [data-apex-deriv-rail].active{',
    'background:#173222!important;color:#86d853!important;',
    'box-shadow:inset 3px 0 0 #70c63a!important;}',
    '.broker-accounts[data-apex-deriv-active="true"]',
    ' .ba-rail-group > .ba-provider-row.active:not([data-apex-deriv-rail]){',
    'background:transparent!important;color:inherit!important;box-shadow:none!important;}',
    '.broker-accounts .ba-detail [data-apex-deriv-frame]{',
    'width:100%;height:100%;min-height:0;border:0;display:none;',
    'background:#0a1220;border-radius:0;}',
    '.broker-accounts[data-apex-deriv-active="true"] .ba-detail{',
    'padding:0!important;overflow:hidden!important;}',
    '.broker-accounts[data-apex-deriv-active="true"] .ba-detail > :not([data-apex-deriv-frame])',
    '{display:none!important}',
    '.broker-accounts[data-apex-deriv-active="true"] .ba-detail [data-apex-deriv-frame]',
    '{display:block!important;}',
    '@media(max-width:760px){.broker-accounts[data-apex-deriv-active="true"]',
    ' .ba-detail [data-apex-deriv-frame]{height:950px!important;}}'
  ].join('');
  function addStyle() {
    if(document.getElementById('apex-deriv-menu-style'))return;
    const style=document.createElement('style');
    style.id='apex-deriv-menu-style';
    style.textContent=styles;
    document.head.appendChild(style);
  }
  function isAccountCenter() {
    return /(?:^|\/)broker-accounts(?:$|[/?])/i.test(location.hash.replace(/^#\/?/,''));
  }
  function root() {
    return document.querySelector('.broker-accounts');
  }
  function setActive(enabled) {
    active=Boolean(enabled);
    const page=root();
    if(page)page.setAttribute('data-apex-deriv-active',String(active));
    const rail=page?.querySelector('['+RAIL+']');
    if(rail)rail.classList.toggle('active',active);
    if(active)ensurePanel();
  }
  function ensurePanel() {
    const page=root();
    if(!page)return false;
    const detail=page.querySelector('.ba-detail');
    if(!detail)return false;
    if(!detail.querySelector('['+FRAME+']')) {
      const iframe=document.createElement('iframe');
      iframe.setAttribute(FRAME,'');
      iframe.setAttribute('title','Deriv MT5 DEMO accounts');
      iframe.setAttribute('referrerpolicy','no-referrer');
      iframe.setAttribute('loading','eager');
      iframe.src=PATH;
      detail.appendChild(iframe);
    }
    return true;
  }
  function showDeriv(e) {
    if(e) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation?.();
    }
    if(!isAccountCenter() || !root()) {
      location.assign('/#/broker-accounts');
      return;
    }
    setActive(true);
    schedule();
  }
  function makeRail() {
    const page=root();
    const group=page?.querySelector('.ba-rail-group');
    if(!group)return;
    if(group.querySelector('['+RAIL+']'))return;
    const button=document.createElement('button');
    button.type='button';
    button.className='ba-provider-row';
    button.setAttribute(RAIL,'');
    button.setAttribute('aria-label','Deriv MT5 DEMO account profiles');
    const img=document.createElement('span');
    img.className='ba-provider-icon ba-provider-icon--broker';
    img.style.setProperty('--brand-color','#e53358');
    const logo=document.createElement('span');
    logo.className='apex-deriv-logo';
    logo.textContent='D';
    img.appendChild(logo);
    const copy=document.createElement('span');
    copy.className='ba-provider-copy';
    const title=document.createElement('strong');
    title.textContent='Deriv MT5 DEMO';
    const status=document.createElement('small');
    status.textContent='Not connected · DEMO';
    copy.append(title,status);
    button.append(img,copy);
    button.addEventListener('click',showDeriv,true);
    group.appendChild(button);
    button.classList.toggle('active',active);
    // Count the APEX extension in the visible broker list without modifying Vue state.
    const counter=group.querySelector('.ba-rail-label strong');
    if(counter && /^[0-9]+$/.test(counter.textContent.trim())) {
      const nativeCount=group.querySelectorAll('button.ba-provider-row:not(['+RAIL+'])').length;
      const expected=String(nativeCount+1);
      if(counter.textContent.trim()!==expected)counter.textContent=expected;
    }
  }
  function makeDropdown(menu) {
    if(menu.querySelector('['+MENU+']'))return;
    const items=Array.from(menu.querySelectorAll(':scope > li'));
    const alpaca=items.find(el=>/alpaca markets/i.test(el.textContent||''));
    const ibkr=items.find(el=>/interactive brokers/i.test(el.textContent||''));
    if(!alpaca||!ibkr)return;
    const item=document.createElement('li');
    item.className=(ibkr.className||'ant-dropdown-menu-item')+' apex-deriv-dropdown-item';
    item.setAttribute(MENU,'');
    item.setAttribute('role','menuitem');
    item.setAttribute('tabindex','0');
    item.setAttribute('aria-label','Connect Deriv MT5 DEMO');
    const logo=document.createElement('span');
    logo.className='apex-deriv-logo apex-deriv-menu-logo';
    logo.textContent='D';
    const label=document.createElement('span');
    label.textContent='Deriv MT5 DEMO';
    item.append(logo,label);
    item.addEventListener('click',showDeriv,true);
    item.addEventListener('keydown',e=>{
      if(e.key==='Enter'||e.key===' ')showDeriv(e);
    },true);
    ibkr.after(item);
  }
  function setupRootListener() {
    const page=root();
    if(!page||page.hasAttribute('data-apex-deriv-click-listener'))return;
    page.setAttribute('data-apex-deriv-click-listener','yes');
    page.addEventListener('click',e=>{
      const selected=e.target.closest?.('button.ba-provider-row');
      if(selected&&!selected.hasAttribute(RAIL))setActive(false);
    },true);
  }
  function check() {
    pending=false;
    if(!isAccountCenter())return;
    addStyle();
    makeRail();
    setupRootListener();
    if(active)setActive(true);
    document.querySelectorAll('ul.ant-dropdown-menu').forEach(makeDropdown);
  }
  function schedule() {
    if(pending)return;
    pending=true;
    requestAnimationFrame(check);
  }
  function start() {
    window.addEventListener('message',event=>{
      const page=root();
      const frame=page?.querySelector('['+FRAME+']');
      if(!frame || event.source!==frame.contentWindow ||
         event.origin!==window.location.origin ||
         !event.data || event.data.type!=='APEX_DERIV_STATUS' ||
         typeof event.data.connected!=='boolean')return;
      const rail=page.querySelector('['+RAIL+']');
      const status=rail?.querySelector('.ba-provider-copy small');
      if(status)status.textContent=event.data.connected?'Connected · DEMO':'Not connected · DEMO';
    });
    const observer=new MutationObserver(schedule);
    observer.observe(document.body,{childList:true,subtree:true});
    window.addEventListener('hashchange',()=>{
      if(!isAccountCenter())active=false;
      schedule();
    });
    document.addEventListener('click',schedule,true);
    schedule();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();
