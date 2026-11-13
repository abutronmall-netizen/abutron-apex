const $ = id => document.getElementById(id);
const base = '/apex/deriv';
const state = {
  accounts:[], selected:null, active:null, verifiedAt:null,
  syncing:false, historyBusy:false, historyFetchedAt:0,
  historyKey:null, historyPeriod:null, lastSyncAt:0
};
if (new URLSearchParams(window.location.search).get('embedded') === '1') {
  document.documentElement.classList.add('embedded');
}
function getToken() {
  for (const storage of [localStorage,sessionStorage]) {
    try {
      let value=storage.getItem('Access-Token');
      for(let i=0;i<2 && value;i++) {
        try {
          const p=JSON.parse(value);
          value=typeof p==='string'?p:(p && (p.token || p.value)) || value;
        } catch {break;}
      }
      if(typeof value==='string' && value.split('.').length===3 && value.length<4096) return value;
    } catch {}
  }
  return '';
}
async function api(path,options={}) {
  const token=getToken();
  if(!token) throw Error('Sign in to the ABUTRON Account Center as administrator first.');
  const response=await fetch(base+path,{
    ...options,credentials:'same-origin',cache:'no-store',
    signal:options.signal || AbortSignal.timeout(45000),
    headers:{...options.headers,'Authorization':'Bearer '+token}
  });
  let data={};
  try {data=await response.json();}catch {throw Error('Invalid connector response');}
  if(!response.ok) throw Error(data.error || 'ABUTRON connector unavailable');
  return data;
}
function message(id,value,type='') {
  const el=$(id);
  el.textContent=value;
  el.className='notice'+(type?' '+type:'');
}
function accountKey(p) {return p.login + '|' + p.server;}
function publishConnectionStatus(connected) {
  // Status only: never send credentials or account data to the parent Vue page.
  if(window.parent!==window) {
    window.parent.postMessage({type:'APEX_DERIV_STATUS',connected:connected===true},
                              window.location.origin);
  }
}
function fields() {
  const p={login:$('login').value.trim(),server:$('server').value.trim(),
           label:$('label').value.trim()};
  if(!/^\d{4,15}$/.test(p.login))throw Error('Enter a valid MT5 account number');
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/.test(p.server)||
     !p.server.toLowerCase().includes('deriv')||
     !p.server.toLowerCase().includes('demo'))throw Error('Use the exact Deriv DEMO server');
  if(p.label.length>48)throw Error('The account label is too long');
  return p;
}
function selectProfile(account) {
  state.selected=accountKey(account);
  $('login').value=account.login;
  $('server').value=account.server;
  $('label').value=account.label;
  $('password').value='';
  if(state.active && accountKey(state.active)===accountKey(account)) {
    setBrokerData(state.active);
    if(!state.syncing) void loadHistory();
  } else {
    $('connection-badge').textContent=account.login_requested_at?'Login requested · Unverified':'Saved · Not connected';
    $('connection-badge').className='chip';
    $('connection-help').textContent='Selected '+account.label+'. This profile is not the currently verified MT5 session.';
    $('account-grid').classList.add('hidden');
    renderPositions(null);
    clearHistory('This profile is not the active MT5 account.');
  }
  drawProfiles();
}
function drawProfiles() {
  const wrap=$('profiles');
  wrap.replaceChildren();
  if(!state.accounts.length) {
    const el=document.createElement('p');
    el.className='intro';
    el.textContent='No saved Deriv DEMO profiles. Enter an MT5 login and server below, then choose Save profile.';
    wrap.append(el);
    return;
  }
  for(const account of state.accounts) {
    const el=document.createElement('div');
    el.className='profile'+(state.selected===accountKey(account)?' selected':'');
    const info=document.createElement('div');
    info.className='profile-meta';
    const title=document.createElement('strong');
    title.textContent=account.label;
    const sub=document.createElement('small');
    sub.textContent=account.login + ' · ' + account.server;
    const status=document.createElement('small');
    status.className='profile-status'+(state.active && accountKey(state.active)===accountKey(account)?' good':'');
    status.textContent=state.active && accountKey(state.active)===accountKey(account)
      ?'Connected · verified DEMO'
      :(account.login_requested_at?'Login requested — unverified':'Saved profile — not connected');
    info.append(title,sub,status);
    const select=document.createElement('button');
    select.type='button';select.className='secondary profile-select';
    select.textContent='Select';
    select.addEventListener('click',()=>selectProfile(account));
    const remove=document.createElement('button');
    remove.type='button';remove.className='secondary profile-remove';
    remove.textContent='Remove';
    remove.setAttribute('aria-label','Remove '+account.label);
    remove.addEventListener('click',async()=>{
      if(!window.confirm('Remove this local profile? This does not log out an active MT5 terminal.'))return;
      remove.disabled=true;
      try {
        await api('/api/accounts/delete',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({login:account.login,server:account.server})
        });
        if(state.selected===accountKey(account))state.selected=null;
        await loadAccounts();
        message('result','Local account profile removed. Any MT5 terminal session is unchanged.','good');
      } catch(err) {message('result',err.message,'bad');}
      finally {remove.disabled=false;}
    });
    el.append(info,select,remove);
    wrap.append(el);
  }
}
async function loadAccounts() {
  const data=await api('/api/accounts');
  state.accounts=Array.isArray(data.accounts)?data.accounts:[];
  drawProfiles();
}
function renderPositions(account) {
  const section=$('positions-section');
  const body=$('positions-body');
  body.replaceChildren();
  if(!account || account.mode!=='DEMO') {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');
  const rows=Array.isArray(account.position_rows)?account.position_rows:[];
  const count=Number(account.positions)||0;
  $('positions-summary').textContent=count===0
    ?'No open positions in this verified DEMO account.'
    :count+' open position(s) in MT5'+(account.positions_truncated?' · first 50 shown':'');
  $('positions-table').classList.toggle('hidden',rows.length===0);
  for(const item of rows) {
    const row=document.createElement('tr');
    for(const value of [item.symbol,item.side,item.volume,item.open_price,item.current_price,item.profit]) {
      const cell=document.createElement('td');
      cell.textContent=String(value ?? '—');
      row.append(cell);
    }
    body.append(row);
  }
}
function setBrokerData(account) {
  const verified=Boolean(account && account.mode==='DEMO');
  $('account-grid').classList.toggle('hidden',!verified);
  renderPositions(verified?account:null);
  if(!verified)return;
  const money=value=>value===null || value===undefined?'—':
    Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+' '+String(account.currency||'');
  const vals={
    'a-login':account.login,'a-mode':'DEMO','a-company':account.company,
    'a-server':account.server,'a-balance':money(account.balance),
    'a-equity':money(account.equity),'a-used-margin':money(account.margin),
    'a-margin':money(account.free_margin),'a-profit':money(account.profit),
    'a-positions':account.positions,'a-symbols':account.symbols
  };
  for(const [id,v] of Object.entries(vals))$(id).textContent=v===null||v===undefined?'—':String(v);
  $('connection-badge').textContent='Connected · Verified DEMO';
  $('connection-badge').className='chip good';
  const when=state.verifiedAt?new Date(state.verifiedAt).toLocaleTimeString():'just now';
  $('connection-help').textContent='Last synchronized with Deriv MT5 at '+when+'. · Automatic updates enabled.';
}
function clearHistory(note='Connect a DEMO account to view trade history.') {
  state.historyKey=null;state.historyPeriod=null;state.historyFetchedAt=0;
  $('history-body').replaceChildren();
  $('history-metrics').classList.add('hidden');
  $('history-table').classList.add('hidden');
  $('history-summary').textContent=note;
  $('history-refresh').disabled=true;
}
function moneyValue(value,currency) {
  if(value===null || value===undefined || !Number.isFinite(Number(value)))return '—';
  return Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+' '+currency;
}
function renderHistory(history) {
  const currency=history.currency||'USD';
  const records=Array.isArray(history.deals)?history.deals:[];
  $('history-net').textContent=moneyValue(history.net_trading_pnl,currency);
  $('history-net').className=Number(history.net_trading_pnl)<0?'loss':'gain';
  $('history-closed').textContent=String(history.closing_executions??0);
  $('history-executions').textContent=String(history.trade_executions??0);
  const costs=Number(history.commissions||0)+Number(history.swaps||0)+Number(history.fees||0);
  $('history-costs').textContent=moneyValue(costs,currency);
  $('history-metrics').classList.remove('hidden');
  const tbody=$('history-body');
  const fragment=document.createDocumentFragment();
  for(const item of records) {
    const tr=document.createElement('tr');
    const when=new Date(item.time_utc);
    const fields=[
      Number.isNaN(when.valueOf())?'—':when.toLocaleString(),
      item.symbol,item.side,item.entry,item.volume,item.price,
      moneyValue(item.profit,currency),moneyValue(item.commission,currency),
      moneyValue(item.swap,currency),moneyValue(item.fee,currency),
      moneyValue(item.net,currency)
    ];
    for(const value of fields) {
      const td=document.createElement('td');
      td.textContent=value==null?'—':String(value);
      tr.append(td);
    }
    fragment.append(tr);
  }
  tbody.replaceChildren(fragment);
  $('history-table').classList.toggle('hidden',records.length===0);
  $('history-summary').textContent=
    history.days+'-day history · '+history.trade_executions+' trade execution(s) · '+
    history.closing_executions+' closing execution(s) · '+
    (history.truncated?'Showing latest 250 deals. ':'')+
    (records.length===0?'No trade executions in this period.':'Updated '+new Date().toLocaleTimeString());
}
async function loadHistory({force=false}={}) {
  const account=state.active;
  const profile=state.accounts.find(p=>accountKey(p)===state.selected);
  if(!account || !profile || accountKey(account)!==accountKey(profile)) {
    clearHistory('Select your connected DEMO account to view trade history.');
    return;
  }
  if(state.historyBusy)return;
  const days=Number($('history-days').value);
  if(![7,30,90].includes(days))return;
  const expected=accountKey(account);
  if(!force && state.historyKey===expected && state.historyPeriod===days &&
     Date.now()-state.historyFetchedAt<180000)return;
  state.historyBusy=true;
  $('history-refresh').disabled=true;
  $('history-summary').textContent='Updating '+days+'-day MT5 trade history…';
  try {
    const response=await api('/api/history?days='+days);
    const report=response.history;
    if(response.verified!==true || !report || report.mode!=='DEMO' ||
       accountKey(report)!==expected)throw Error('The broker account changed during synchronization');
    if(!state.active || accountKey(state.active)!==expected || state.selected!==expected) {
      clearHistory('Selected account changed. Refresh to load its history.');
      return;
    }
    state.historyKey=expected;state.historyPeriod=days;state.historyFetchedAt=Date.now();
    renderHistory(report);
  } catch(err) {
    clearHistory('Trade history unavailable: '+err.message);
  } finally {
    state.historyBusy=false;
    $('history-refresh').disabled=!(state.active && state.selected===accountKey(state.active));
  }
}
function updateSyncLabel(text,isError=false) {
  const el=$('sync-status');
  el.textContent=text;
  el.className='sync-status'+(isError?' bad':'');
}
async function refresh({automatic=false}={}) {
  if(state.syncing)return;
  if(automatic && document.visibilityState==='hidden')return;
  state.syncing=true;
  $('refresh-button').disabled=true;
  updateSyncLabel('Synchronizing with MT5…');
  try {
    await loadAccounts();
    const data=await api('/api/status');
    state.active=(data.connected===true && data.verified===true
      && data.account && data.account.mode==='DEMO')?data.account:null;
    state.verifiedAt=state.active?data.verified_at:null;
    if(state.selected && !state.accounts.some(p=>accountKey(p)===state.selected))state.selected=null;
    if(!state.selected && state.active) {
      const p=state.accounts.find(x=>accountKey(x)===accountKey(state.active));
      if(p)selectProfile(p);
    }
    if(!state.selected && data.requested && data.requested_login) {
      const p=state.accounts.find(x=>x.login===data.requested_login && x.server===data.requested_server);
      if(p)selectProfile(p);
    }
    const selected=state.accounts.find(p=>accountKey(p)===state.selected);
    if(selected && state.active && accountKey(selected)===accountKey(state.active)) {
      setBrokerData(state.active);
    } else {
      setBrokerData(null);
      $('connection-badge').textContent=selected && selected.login_requested_at
        ?'Login requested · Unverified':'Not connected';
      $('connection-badge').className='chip';
      $('connection-help').textContent=state.active
        ?'A different saved DEMO account is currently connected to MT5. Select that profile to view its broker data.'
        :'No broker-confirmed DEMO session for this selected profile. Refresh after a login.';
    }
    drawProfiles();
    publishConnectionStatus(Boolean(state.active));
    state.lastSyncAt=Date.now();
    const checkedAt=new Date(state.lastSyncAt).toLocaleTimeString();
    updateSyncLabel(state.active
      ?'Connected to Deriv DEMO · Updated '+checkedAt+' · Auto-refresh every 60s'
      :'No connected Deriv DEMO session · Checked '+checkedAt, !state.active);
    if(state.active && state.selected===accountKey(state.active)) {
      $('history-refresh').disabled=false;
      void loadHistory();
    } else {
      clearHistory('Select a connected Deriv DEMO account to view its trade history.');
    }
    message('auth-message','ABUTRON administrator authenticated. MT5 account status updated.','good');
    $('save-button').disabled=false;
    $('connect-button').disabled=false;
  } catch(err) {
    state.active=null;state.verifiedAt=null;
    setBrokerData(null);drawProfiles();
    clearHistory('Connection interrupted. Trade history will reload when MT5 reconnects.');
    publishConnectionStatus(false);
    updateSyncLabel('Connection interrupted · '+err.message, true);
    $('connection-badge').textContent='Connection unavailable';
    $('connection-badge').className='chip';
    message('auth-message',err.message,'bad');
    $('save-button').disabled=true;$('connect-button').disabled=true;
  } finally {
    state.syncing=false;
    $('refresh-button').disabled=false;
  }
}
$('save-button').addEventListener('click',async()=>{
  try {
    const packet=fields();
    const data=await api('/api/accounts',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(packet)
    });
    await loadAccounts();
    selectProfile(data.account);
    message('result','DEMO profile saved without a password. Account remains unverified.','good');
  } catch(err) {message('result',err.message,'bad');}
});
$('connect-form').addEventListener('submit',async(event)=>{
  event.preventDefault();
  let packet;
  try {packet=fields();}catch(err){message('result',err.message,'bad');return;}
  packet.password=$('password').value;
  if(!packet.password){message('result','Enter this account’s DEMO password to request an MT5 login.','bad');return;}
  $('connect-button').disabled=true;
  message('result','Submitting DEMO account details automatically in the MT5 terminal. Awaiting broker confirmation.');
  try {
    const response=await api('/api/connect',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(packet)
    });
    await loadAccounts();
    const matching=state.accounts.find(x=>x.login===packet.login && x.server===packet.server);
    if(matching)selectProfile(matching);
    await refresh(); // Read broker state again; never trust "submitted" as verified.
    const verified=Boolean(state.active && accountKey(state.active)===packet.login+'|'+packet.server);
    message('result',verified
      ?'Deriv MT5 DEMO login confirmed. Account data synchronized. Trading execution remains disabled.'
      :(response.requested
        ?'MT5 received the DEMO login. Broker confirmation is not yet available; refresh account status shortly.'
        :'Connection remains unverified.'),verified?'good':'');
  } catch(err) {
    message('result',err.message,'bad');
  } finally {
    packet.password='';
    $('password').value='';
    $('connect-button').disabled=false;
  }
});
$('refresh-button').addEventListener('click',()=>refresh());
$('history-refresh').addEventListener('click',()=>loadHistory({force:true}));
$('history-days').addEventListener('change',()=>{
  state.historyFetchedAt=0;
  void loadHistory({force:true});
});
// Refresh MT5 account data every 60 seconds while the portal tab is visible.
// History refreshes at most every 3 minutes, and only for the selected account.
setInterval(()=>{
  if(document.visibilityState==='visible')void refresh({automatic:true});
},60000);
setInterval(()=>{
  if(document.visibilityState==='hidden')return;
  if(state.lastSyncAt && Date.now()-state.lastSyncAt>120000)
    updateSyncLabel('Broker data out of date · Reconnecting…',true);
},15000);
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='visible')void refresh({automatic:true});
  else updateSyncLabel('Synchronization paused while this tab is inactive');
});
window.addEventListener('online',()=>void refresh({automatic:true}));
refresh();
