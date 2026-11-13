/* APEX operations frontend — no trading, credentials, or external calls. */
"use strict";
const $ = (id) => document.getElementById(id);
const ui = { overview: null, symbol: "", compareSymbol:"", frame: "M5", chart: [], busy: false, view: "overview", symbolInitialized: false };
const API = "/apex/api/";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number = (v) => v == null || v === "" || !Number.isFinite(Number(v)) ? "—" : Number(v).toLocaleString("en-US",{maximumFractionDigits:4});
const clock = (value) => { try { return new Date(value).toLocaleString("en-GB",{timeZone:"UTC",dateStyle:"short",timeStyle:"short"})+" UTC"; }catch(_){return "—";} };
// Never substitute the wall clock for a missing broker trade timestamp.
const brokerStamp = (value, fallbackLabel="NOT RECORDED") => {
  if(typeof value!=="string" || !value.trim())return '<span class="stamp-missing">'+esc(fallbackLabel)+'</span>';
  const d=new Date(value);
  if(!Number.isFinite(d.getTime()))return '<span class="stamp-missing">INVALID TIMESTAMP</span>';
  const date=new Intl.DateTimeFormat("en-GB",{day:"2-digit",month:"short",year:"numeric",timeZone:"UTC"}).format(d);
  const time=new Intl.DateTimeFormat("en-GB",{hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23",timeZone:"UTC"}).format(d);
  return '<span class="trade-stamp" title="'+esc(d.toISOString())+'"><strong>'+esc(date)+'</strong><small>'+esc(time)+' UTC</small></span>';
};
const age = (v) => v == null ? "unavailable" : v < 60 ? v+" sec ago" : v < 3600 ? Math.round(v/60)+" min ago" : Math.floor(v/3600)+"h "+Math.floor(v%3600/60)+"m ago";
const cls = (v) => String(v||"").toLowerCase().replace(/[^a-z]/g,"");
function text(id,value){ const el=$(id);if(el) el.textContent=String(value??"—"); }
function badgeTrend(v) {const v2=String(v||"UNKNOWN");return '<span class="trend '+cls(v2)+'">'+esc(v2)+'</span>';}
function pretty(v) {return cls(v).includes("hold")?"hold":cls(v).includes("buy")?"buy":cls(v).includes("sell")?"sell":"";}
function changeUI(view) {
  const views=["overview","apexengines","markets","signals","agents","scanner","compare","account","execution","systems"];
  if(!views.includes(view)) return;
  ui.view=view;
  document.querySelectorAll(".view").forEach((el)=>el.classList.toggle("active",el.id===view));
  document.querySelectorAll(".navitem").forEach((el)=>el.classList.toggle("active",el.dataset.view===view));
  const title={overview:"Operations Overview",apexengines:"APEX 1.1 Engines",markets:"Market Watch",signals:"APEX Signals",agents:"Legacy AI diagnostics",scanner:"Legacy scanner",compare:"Candle Comparison",account:"Account & Trades",execution:"Execution Checks",systems:"System & Risk"};
  const subtitle={overview:"Broker data, APEX 1.1 native decision journals and actual execution evidence.",apexengines:"Six account-bound research components and DEMO account-specific M5 signals; no claimed broker orders.",markets:"13 Deriv synthetic instruments · Six completed-candle timeframes.",signals:"Current APEX 1.1 account-bound M5 directions; older research appears separately as legacy history.",agents:"Historical legacy model diagnostics, not APEX 1.1 execution authority.",scanner:"Historical scanner display; current APEX 1.1 decisions are in the Engines and Signals views.",compare:"Eight completed broker candle periods, with candle bias separate from EMA/RSI trend.",account:"Broker-confirmed positions and APEX-only entry records. Broker deal history is not fully exported.",execution:"Broker-verified protected-order prechecks and durable intent tracking.",systems:"Live infrastructure checks and estimated broker contract exposure."};
  text("screenName",title[view]);text("pageHeading",title[view]);  text("pageSubhead",subtitle[view]);
  if(view==="signals"){void loadDecisionIntelligence();}
}
function renderServices(d) {
  const services=[
    ["operator_dashboard","Operator dashboard"],["client_portal","Client portal"],
    ["mt5_manager","MT5 account manager"],["native_feed","Native broker feed · 60s"],
    ["research_fanout","APEX research signal fanout"],["execution_preflight","Order preflight · no execution"],
    ["handover_watch","Execution handover checks"],["destination_shadow","APEX local research"],
    ["local_model","Local model · supplementary"],["auto_orders","Automatic Deriv DEMO dispatcher"],
    ["remote_management","Remote desktop management"]
  ];
  const native=d.operator_native||{};
  const connected=native.fresh===true;
  const rows=(connected && Array.isArray(native.accounts))?native.accounts:[];
  const clientNames={};
  const accounts=rows.map((a,i)=>{
    const label=a.label==="Primary owner"?"Primary owner MT5":("Client MT5 "+(i+1));
    const state=a.connected?"CONNECTED":"UNVERIFIED";
    const stateTag=a.connected?"active":"inactive";
    const bridge=a.bridge_ready?" · bridge loaded":" · bridge unverified";
    return '<div class="service-item"><div class="service-name"><i class="dot '+(a.connected?"good":"bad")+'"></i>'+esc(label)+esc(bridge)+'</div><span class="status-tag '+stateTag+'">'+state+'</span></div>';
  }).join("");
  const runtime=native.execution_runtime||{};
  const liveLabel=connected?native.sessions_connected+"/"+native.sessions_total+" connected · "+native.bridges_ready+" bridges"+
     (runtime.ledger_available===true?" · "+runtime.verified_protected_positions+" protected APEX positions":" · execution evidence unavailable"):"Native broker status unavailable";
  const intro='<div class="service-item"><div class="service-name"><b>MT5 DEMO sessions · '+esc(liveLabel)+'</b></div><span class="status-tag '+(connected?"active":"inactive")+'">'+(connected?"DEMO":"STALE")+'</span></div>';
  const items=services.map(([key,label])=>{
    const status=d.services?.[key]||"unknown";
    const xr=native.execution_runtime||{};
    const display=key==="auto_orders"&&status==="active"?
      (native.fresh!==true||xr.ledger_available!==true?"RUNNING · PROOF STALE":
       Number(native.trading_enabled)>0?"RUNNING · ENTRIES ENABLED":
       Number(xr.verified_protected_positions)>0?"RUNNING · POSITIONS OPEN":"RUNNING · ENTRIES PAUSED"):
      status.toUpperCase();
    return '<div class="service-item"><div class="service-name"><i class="dot '+(status==="active"?"good":"bad")+'"></i>'+esc(label)+'</div><span class="status-tag '+cls(status)+'">'+esc(display)+'</span></div>';
  }).join("");
  $("servicePreview").innerHTML=intro+accounts+items;
  $("serviceDetails").innerHTML=intro+accounts+items;
  const research=d.services?.research_fanout==="active";
  text("agentCycleChip",research?"RESEARCH ONLY":"RESEARCH OFF");
  text("analysisStatus",research?"RESEARCH":"OFF");
}
function renderSignals(d){
  const latest=d.agents.latest;
  const scanner=d.scanner||{};
  const nativeCurrent=scanner.available && !scanner.stale && d.operator_native?.fresh===true;
  const qualified=nativeCurrent?(scanner.instruments||[]).filter(x=>x.proposal==="BUY"||x.proposal==="SELL"):[];
  text("decisionSymbol",latest?.symbol||"No current historical AI decision");
  text("technicalAction",latest?.technical_direction||"—");
  text("agentRating",latest?.rating?.toUpperCase()||"—");
  text("shadowAction",latest?.shadow_direction||"—");
  text("decisionReason",latest?.reason||"Historical TradingAgents archive only. Current APEX research is displayed on the Overview and Strategy Scanner.");
  text("decisionModel",latest?.model||"HISTORICAL ARCHIVE");
  text("decisionTime",latest?.timestamp_utc?clock(latest.timestamp_utc):"—");
  text("kpiSignal",qualified.length?qualified[0].proposal+" · RESEARCH":"NO EXECUTED SIGNAL");
  text("kpiSignalName",qualified.length?qualified[0].symbol:"APEX research · broker orders separate");
  $("signalPreview").innerHTML=!nativeCurrent
   ?'<div class="empty">Native scanner unavailable or stale. Historical AI decisions are archived separately.</div>'
   :qualified.length?qualified.slice(0,5).map(x=>'<div class="history-row"><div><b>'+esc(x.symbol)+'</b><small>APEX · '+esc(x.proposal)+' research · SEE BROKER TRADES</small></div><span class="signal '+pretty(x.proposal)+'">'+esc(x.proposal)+'</span></div>').join("")
    :'<div class="empty">13-symbol native scanner current. No BUY/SELL research candidates. New entries depend on account controls.</div>';
  const sigs=d.agents.signals||[];
  $("signalsBody").innerHTML=sigs.length?sigs.map(x=>'<tr><td>'+esc(clock(x.timestamp_utc))+'</td><td class="symboltext">'+esc(x.symbol)+'</td><td>'+esc(x.technical_direction)+'</td><td><span class="signal '+pretty(x.rating)+'">'+esc(x.rating)+'</span></td><td><span class="signal '+pretty(x.shadow_direction)+'">'+esc(x.shadow_direction)+'</span></td><td>HISTORICAL · NOT ORDERED</td></tr>').join(""):'<tr><td colspan="6">No historical AI decision records.</td></tr>';
}
function renderRisk(d){
  const risk=d.risk||{};
  text("riskBelow",risk.available?risk.verified_contracts:"—");
  text("riskAbove",risk.available?risk.unverified_contracts:"—");
  text("riskAge",risk.available?"Broker contract estimates last calculated "+age(risk.age_seconds)+". Risk certification remains pending.":"No validated risk estimates are available.");
  const entries=Object.entries(risk.instruments||{});
  $("riskBody").innerHTML=entries.length?entries.map(([name,r])=>'<tr><td class="symboltext">'+esc(name)+'</td><td>'+esc(number(r.minimum_lot))+'</td><td>$'+esc(number(r.buy_estimate_usd))+'</td><td>$'+esc(number(r.sell_estimate_usd))+'</td><td>'+(r.verified?'<span class="val-up">ESTIMATED</span>':'<span class="val-down">UNVERIFIED</span>')+'</td></tr>').join(""):'<tr><td colspan="5">No risk estimate available</td></tr>';
}
function renderMarkets(d){
  const m=d.market||{};
  text("kpiSymbols",m.count?m.count+"/13":"—");
  text("kpiTimeframes",m.count?m.count*6+"/78":"—");
  text("kpiFreshness",m.stale?"STALE":"FRESH");
  text("kpiAge",age(m.age_seconds));
  text("chartUpdated",m.generated_at_utc?"Native MT5 snapshot: "+clock(m.generated_at_utc):"Native MT5 snapshot unavailable");
  const symbols=m.instruments||[];
  const selector=$("symbolSelect");
  const selected=ui.symbol;
  selector.replaceChildren(...symbols.map((item)=>{const option=document.createElement("option");option.value=item.name;option.textContent=item.name;return option;}));
  if(!ui.symbolInitialized && symbols.length){
    ui.symbol=(d.agents.latest?.symbol && symbols.some(x=>x.name===d.agents.latest.symbol))?d.agents.latest.symbol:symbols[0].name;
    ui.symbolInitialized=true;
  }else if(symbols.some((x)=>x.name===selected)){ui.symbol=selected;}
  else if(symbols.length){ui.symbol=symbols[0].name;}
  selector.value=ui.symbol;
  const q=$("marketSearch").value.toLowerCase();
  const rows=symbols.filter((r)=>r.name.toLowerCase().includes(q));
  $("marketsBody").innerHTML=rows.map((r)=>
    '<tr class="selectable" data-symbol="'+esc(r.name)+'"><td class="symboltext">'+esc(r.name)+'</td><td>'+esc(number(r.price))+'</td><td class="'+(r.change_pct>=0?"val-up":"val-down")+'">'+esc((r.change_pct>=0?"+":"")+number(r.change_pct))+'%</td><td>'+badgeTrend(r.trend.M15)+'</td><td>'+badgeTrend(r.trend.H1)+'</td><td>'+badgeTrend(r.trend.H4)+'</td><td>'+esc(clock(r.last_bar_utc))+'</td></tr>').join("") || '<tr><td colspan="7">No matching instruments.</td></tr>';
  $("marketsBody").querySelectorAll("tr[data-symbol]").forEach((r)=>r.addEventListener("click",()=>{ui.symbol=r.dataset.symbol;changeUI("overview");loadChart();}));
  const current=symbols.find((x)=>x.name===ui.symbol);
  if(current){
    text("chartTitle",current.name);
    text("lastPrice",number(current.price));
    text("priceChange",(current.change_pct>=0?"+":"")+number(current.change_pct)+"% / M5");
    $("priceChange").classList.toggle("neg",current.change_pct<0);
  }
  const native=d.operator_native||{};
  const alive=!m.stale&&m.count===13&&native.fresh===true;
  const connected=native.fresh===true && native.sessions_connected>0;
  const xr=native.execution_runtime||{};
  const entryNote=Number(native.trading_enabled)>0?" · new-entry accounts: "+native.trading_enabled:
    xr.ledger_available===true&&Number(xr.verified_protected_positions)>0?" · "+xr.verified_protected_positions+" protected positions · entries paused":" · new entries OFF";
  text("connectionLabel",alive?native.sessions_connected+"/"+native.sessions_total+" MT5 DEMO connected"+entryNote:connected?native.sessions_connected+"/"+native.sessions_total+" broker sessions; market data stale":"Broker connections unavailable or unverified");
  $("connectionDot").className="dot "+(alive?"good":"bad");
  text("refreshLabel",alive?"NATIVE BROKER FEED":"FEED STALE");
}
async function getJson(path){
  const response=await fetch(API+path,{cache:"no-store",credentials:"same-origin"});
  if(!response.ok)throw Error("Server returned HTTP "+response.status);
  return response.json();
}

function renderAccount(d){
  const a=d.broker_account||{};
  const valid=a.available===true;
  const bal=valid?"$"+number(a.balance_usd):"—";
  const equ=valid?"$"+number(a.equity_usd):"—";
  text("homeBalance",bal);text("homeEquity",equ);text("homePositions",valid?a.open_positions:"—");
  text("accountBalance",bal);text("accountEquity",equ);
  text("accountFreeMargin",valid?"$"+number(a.free_margin_usd):"—");
  text("accountTodayPnl",valid?"$"+number(a.realized_today_usd):"—");
  text("accountFreshness",!valid?"UNAVAILABLE":a.stale?"STALE":age(a.age_seconds));
  const positions=a.positions||[];
  $("accountPositions").innerHTML=positions.length?positions.map((p)=>
    '<tr><td>'+esc(p.ticket)+'</td><td>'+brokerStamp(p.request_utc)+'</td><td class="symboltext">'+esc(p.symbol)+'</td><td>'+esc(p.side)+'</td><td>'+esc(number(p.volume))+'</td><td>'+esc(number(p.price_open))+'</td><td>'+esc(number(p.price_current))+'</td><td>'+esc(number(p.sl))+'</td><td>'+esc(number(p.tp))+'</td><td class="'+(p.profit_usd>=0?"val-up":"val-down")+'">'+esc(number(p.profit_usd))+'</td></tr>').join(""):'<tr><td colspan="10">'+(valid?"No broker positions currently open.":"Broker account data unavailable.")+'</td></tr>';
  const deals=a.recent_deals||[];
  $("accountDeals").innerHTML=deals.length?deals.map((v)=>
   '<tr><td>'+brokerStamp(v.time_utc)+'</td><td>'+esc(v.deal)+'</td><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.side)+'</td><td>'+esc(v.entry)+'</td><td>'+esc(number(v.volume))+'</td><td>'+esc(number(v.price))+'</td><td class="'+(v.profit_usd>=0?"val-up":"val-down")+'">'+esc(number(v.profit_usd))+'</td><td class="'+(v.net_cashflow_usd>=0?"val-up":"val-down")+'">'+esc(number(v.net_cashflow_usd))+'</td></tr>').join(""):'<tr><td colspan="9">No broker deal records available.</td></tr>';
}
function renderScanner(d){
  const s=d.scanner||{},g=d.risk_governor||{};
  text("scanSymbols",s.available?s.symbols+"/13":"—");
  text("scanCandidates",s.available?s.candidates:"—");
  text("scanFreshness",s.stale?"STALE":"CURRENT");
  text("scannerLlmState","QWEN "+(s.llm?.status||"PENDING"));
  text("scanAge",age(s.age_seconds));
  text("scanRisk",g.kill_switch||"LOCKED");
  text("homeRiskLock",g.kill_switch||"LOCKED");
  text("governorHeadroom",g.available&&g.risk_parameters_configured?"$"+number(g.headroom_estimated_usd):"NOT SET");
  text("governorSingle",g.available&&g.risk_parameters_configured?"$"+number(g.max_single_reference_usd):"NOT SET");
  text("governorKill",g.kill_switch||"LOCKED");
  text("governorNotes","Risk status: "+(g.status||"BLOCKED")+
    " · "+(g.blockers||["NO VERIFIED RISK CONTROLS"]).join(" · ")+
    " · Last validation: "+age(g.age_seconds)+".");
  const bySymbol=new Map((g.proposals||[]).map(x=>[x.symbol,x]));
  const a=d.broker_account||{},auto=d.demo_auto||{};
  const timerOn=d.services?.auto_orders==="active"&&d.operator_native?.fresh===true;
  const rows=s.instruments||[];
  $("scannerBody").innerHTML=rows.map((v)=>{
    const risk=bySymbol.get(v.symbol)||{};
    // Broker account magic + confirmed server SL/TP distinguish actual open
    // APEX DEMO positions from research proposals, checks, or other trades.
    const opened=(a.positions||[]).some(p=>p.symbol===v.symbol &&
      Number(p.magic)===20261031 && (auto.controller_version==="basket_v1" || (Number(p.sl)>0 && Number(p.tp)>0)));
    let mode,kind;
    if(opened){mode="OPEN IN MT5";kind="val-up";}
    else if(!timerOn){mode="CONTROLLER OFF";kind="val-down";}
    else if(v.proposal==="HOLD"){mode=v.family==="Crash"||v.family==="Boom"?"HOLD · SPIKE MODEL":"HOLD · STRATEGY";kind="signal hold";}
    else if(!a.available||a.stale){mode="ACCOUNT STALE";kind="val-down";}
    else {mode="PER-SYMBOL ENTRY CHECK";kind="signal hold";}
    return '<tr class="selectable" data-compare-symbol="'+esc(v.symbol)+'"><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.family)+'</td><td>'+badgeTrend(v.m1_trend)+'</td><td><span class="signal '+pretty(v.m5_candle_bias)+'">'+esc(v.m5_candle_bias||"UNAVAILABLE")+'</span></td><td>'+badgeTrend(v.m5_trend)+'</td><td><span class="signal '+pretty(v.m5_signal)+'">'+esc(v.m5_signal||"HOLD")+'</span></td><td>'+badgeTrend(v.m15_trend)+'</td><td>'+badgeTrend(v.h1_trend)+'</td><td>'+badgeTrend(v.h4_trend)+'</td><td>'+badgeTrend(v.d1_trend)+'</td><td>'+esc(number(v.m5_rsi))+'</td><td><span class="signal '+pretty(v.proposal)+'">'+esc(v.proposal)+'</span></td><td><span class="signal '+pretty(v.llm_rating)+'" title="'+esc(v.llm_analysis||"Model review pending for current M5 candle")+'">'+esc(v.llm_rating||"PENDING")+'</span></td><td><span class="val-down">'+esc(risk.status||"BLOCKED")+'</span></td><td><span class="'+kind+'">'+esc(mode)+'</span></td><td>'+esc(v.reason)+'</td></tr>';
  }).join("")||'<tr><td colspan="16">Scanner output unavailable or unverified.</td></tr>';
  $("scannerBody").querySelectorAll("tr[data-compare-symbol]").forEach((row)=>row.addEventListener("click",()=>{
    ui.compareSymbol=row.dataset.compareSymbol;
    changeUI("compare");
    syncComparisonSelector(ui.overview);
    loadComparison();
  }));
}


function renderExecution(d){
  const p=d.broker_prechecks||{},e=d.execution_preview||{},auto=d.demo_auto||{},a=d.broker_account||{};
  const active=auto.enabled===true && auto.timer_active===true && auto.stale===false;
  const basketMode=auto.controller_version==="basket_v1";
  const waiting=auto.reason==="NO_FRESH_M5_QUALIFIED_SIGNAL" || auto.status==="NO_NEW_SIGNAL";
  const mode=!active?"LOCKED":basketMode?(auto.status==="BASKET_CLOSING"?"BASKET CLOSING":auto.status==="BASKET_CLOSED"?"RE-SCANNING":"BASKET ACTIVE"):auto.status==="OPEN_PROTECTED"?"POSITION OPEN":
    auto.status==="POSITION_OPEN"?"POSITION OPEN":auto.status==="FULL"?"13/13 OPEN":
    auto.status==="SCANNING"||waiting?"SCANNING":
    auto.status==="BLOCKED"?"SAFETY BLOCK":"READY";
  text("demoProfileState",basketMode?"BASKET +$100 / −$50":auto.usd_profile_active===true?"ACTIVE · USD":"UNVERIFIED");
  const usdRows=Array.isArray(auto.usd_profiles)?auto.usd_profiles:[];
  $("demoUsdProfiles").innerHTML=usdRows.length?usdRows.map(p=>{
    const eligible=auto.usd_profile_active===true;
    const contract=(a.contracts||[]).find(c=>c.symbol===p.symbol);
    const step=Number(contract?.lot_step), minimum=Number(contract?.min_lot);
    const validLot=contract?.ok===true && step>0 && Number(p.lots)>=minimum-1e-7 &&
      Number(p.lots)<=Number(contract.max_lot)+1e-7 &&
      Math.abs((Number(p.lots)-minimum)/step-Math.round((Number(p.lots)-minimum)/step))<1e-4;
    const caption=!validLot?"BLOCKED · INVALID BROKER LOT":
      !eligible?"UNVERIFIED PROFILE":"LOT VALID · SIGNAL/MT5 GATED";
    return '<tr><td class="symboltext">'+esc(p.symbol)+'</td><td>'+esc(number(p.lots))+
    '</td><td>'+(basketMode?"BASKET":"$"+esc(number(p.stop_usd)))+'</td><td>'+(basketMode?"BASKET":"$"+esc(number(p.target_usd)))+
    '</td><td><span class="'+(validLot&&eligible?"val-up":"val-down")+'">'+esc(caption)+'</span></td></tr>';
  }).join(""):'<tr><td colspan="5">No verified active USD workbook profile found.</td></tr>';
  text("demoModeValue",mode);
  $("demoMode").classList.toggle("on",active);
  $("demoMode").classList.toggle("off",!active);
  text("safetyNoticeText",active
    ? (basketMode?"APEX DERIV DEMO BASKET ACTIVE · TP +$100 / SL −$50 combined floating USD · Individual broker SL/TP removed · Software exits are not guaranteed at trigger prices · LIVE disabled.":"APEX Deriv DEMO multi-symbol controller enabled: up to 13 simultaneous positions, one per symbol, individual broker-side USD SL/TP. No account-wide loss cap; LIVE disabled.")
    :"APEX DEMO controller inactive or blocked; check last cycle diagnostics. LIVE remains disabled.");
  text("execEvaluated",p.available?p.evaluated:"—");
  text("execAccepted",p.available?p.accepted:"—");
  text("execOrders",auto.stale?"—":(auto.broker_confirmed_orders??"—"));
  text("execOrdersNote",auto.stale?"Legacy execution ledger STALE · not current confirmed orders":"Broker-confirmed APEX positions from this controller");
  text("execLock",mode);
  text("execGateNote",active?(basketMode?"Basket +$100 / −$50 · fresh M5 signals after closure":"Recurring DEMO checks · one entry per symbol"):"Controller data unavailable or stale");
  text("demoConfirmedTotal",auto.stale?"—":(auto.broker_confirmed_orders??"—"));
  text("demoUncertainTotal",auto.unreconciled_attempts??"—");
  text("demoBudgetRemaining",auto.stale?"—":(auto.open_apex_positions??"—")+"/13");
  text("demoCycleFreshness",!auto.available?"UNAVAILABLE":auto.stale?"STALE":age(auto.age_seconds));
  text("demoLastReason", (basketMode?"Basket floating P&L: $"+number(auto.basket_floating_pnl_usd)+" · TP +$100 / SL −$50 · ":"")+"Last DEMO cycle: "+(auto.status||"UNKNOWN")+
    " · "+(auto.reason||"No open trade or stop failure reported")+
    " · UTC "+(auto.checked_at_utc?clock(auto.checked_at_utc):"unavailable"));
  text("execIntents",e.available?e.total_intents:"—");
  text("execUncertain",e.available?e.unreconciled_orders:"—");
  text("execMode",e.status||"LOCKED");
  text("execFreshness",!p.available?"UNAVAILABLE":p.stale?"STALE":age(p.age_seconds));
  text("executionCheckAge",!p.available?"UNAVAILABLE":p.stale?"STALE · "+age(p.age_seconds):age(p.age_seconds));
  const rows=p.results||[];
  $("execPrechecks").innerHTML=rows.map((x)=>{
    const accepted=x.order_check_accepted===true;
    const exact=x.checked_at_utc;
    const checked=brokerStamp(exact || p.generated_at_utc);
    return '<tr><td class="symboltext">'+esc(x.symbol)+'</td><td>'+esc(x.side)+'</td><td>'+esc(number(x.minimum_lot))+'</td><td>'+esc(number(x.sl))+'</td><td>'+esc(number(x.tp))+'</td><td>$'+esc(number(x.buffered_stop_estimate_usd))+'</td><td><span class="'+(accepted?"val-up":"val-down")+'">'+esc(accepted?"CHECK ACCEPTED":"BLOCKED")+'</span></td><td>'+checked+(exact?'':'<small class="batch-tag">BATCH SNAPSHOT</small>')+'</td></tr>';
  }).join("")||'<tr><td colspan="8">No verified broker precheck records yet.</td></tr>';
  // New native DEMO order status overrides retired single-owner controller labels.
  const rt=d.operator_native?.execution_runtime||{};
  const current=d.operator_native?.fresh===true&&rt.ledger_available===true;
  const dispatcher=d.services?.auto_orders==="active";
  if(current){
    const entries=Number(d.operator_native.trading_enabled||0);
    const open=Number(rt.verified_protected_positions||0);
    const state=!dispatcher?"DISPATCHER STOPPED":entries>0?"NEW ENTRIES ENABLED":
      open>0?"POSITIONS OPEN · ENTRIES PAUSED":"NEW ENTRIES PAUSED";
    text("demoModeValue",state);
    $("demoMode").classList.toggle("on",dispatcher);
    $("demoMode").classList.toggle("off",!dispatcher);
    text("safetyNoticeText","Deriv DEMO native dispatcher "+(dispatcher?"RUNNING":"STOPPED")+
       " · "+open+" broker-verified protected APEX positions · "+entries+
       " accounts authorized for new entries · LIVE trading OFF.");
    text("execOrders",rt.broker_acknowledged_deals??"—");
    text("demoConfirmedTotal",rt.broker_acknowledged_deals??"—");
    text("demoUncertainTotal",rt.unreconciled_attempts??"—");
    text("execOrdersNote","Historical broker-acknowledged APEX DEMO deals, not currently open orders");
    text("execLock",state);
    text("execGateNote",open>0?"Existing broker positions pause new entries until reconciliation":"Entry permission remains per-customer");
    text("execMode",state);
    text("demoCycleFreshness",age(d.operator_native.age_seconds));
    text("demoLastReason","Native dispatcher "+(dispatcher?"running":"stopped")+
         " · "+open+" protected open · "+(rt.unreconciled_attempts??"—")+
         " unresolved attempts · Deriv DEMO only");
  }
}


function syncComparisonSelector(d){
  const list=d?.market?.instruments||[];
  const select=$("comparisonSymbol");
  const existing=ui.compareSymbol;
  select.replaceChildren(...list.map(x=>{
    const opt=document.createElement("option");
    opt.value=x.name;opt.textContent=x.name;return opt;
  }));
  if(!list.some(x=>x.name===existing)){
    ui.compareSymbol=list.find(x=>x.name==="Volatility 75 Index.0")?.name || list[0]?.name || "";
  }
  select.value=ui.compareSymbol;
}
async function loadComparison(){
  if(!ui.compareSymbol)return;
  const chosen=ui.compareSymbol;
  try{
    const data=await getJson("candle-comparison?symbol="+encodeURIComponent(chosen));
    if(chosen!==ui.compareSymbol)return;
    if(!data.rows||data.rows.length!==8||data.orders_enabled!==false)throw Error("Invalid broker comparison");
    const m5=data.rows.find(x=>x.timeframe==="M5");
    text("comparisonM5Bias",m5?.candle_bias||"—");
    text("comparisonM5Trend",m5?.ema_rsi_trend||"—");
    text("comparisonM5Time",m5?.candle_closed_utc?
      "Closed "+new Date(m5.candle_closed_utc).toISOString().slice(0,19).replace("T"," ")+" UTC":"Unavailable");
    const verdict=data.scanner_comparison||{};
    const matched=verdict.status==="MATCHED";
    // Use the identical verified scanner decision only when six timeframe
    // bar timestamps and EMA/RSI calculations match. Otherwise fail closed.
    const proposal=matched?verdict.strategy_gate:"SYNC PENDING";
    text("comparisonStrategyGate",proposal||"HOLD");
    const decisionCard=$("comparisonStrategyGate");
    decisionCard.className=matched?"signal "+pretty(proposal):"signal hold";
    text("comparisonStrategyGateMeta",matched?
      "Same M5 candle UTC as Strategy Scanner · "+(verdict.m5_candle_closed_utc||"unknown"):
      "Not verified against current scanner · No executable signal displayed");
    text("comparisonM5Direction",matched?
      "Scanner M5 EMA/RSI direction: "+(verdict.m5_direction||"HOLD"):
      "Scanner direction pending same-candle validation");
    text("comparisonSource",matched?"MATCHED":(verdict.status||"UNAVAILABLE").replaceAll("_"," "));
    text("comparisonFreshness","Deriv DEMO MT5 · "+age(Math.max(data.main_snapshot_age_seconds,data.extra_snapshot_age_seconds)));
    const closeUtc=verdict.m5_candle_closed_utc?
      new Date(verdict.m5_candle_closed_utc).toISOString().slice(0,19).replace("T"," ")+" UTC":"unavailable";
    text("comparisonScannerMatch",matched?"Strategy Scanner matches this candle":
      "Scanner alignment: "+(verdict.status||"UNAVAILABLE").replaceAll("_"," "));
    text("comparisonScannerDetails","M5 candle "+(m5?.candle_bias||"—")+
      " · EMA/RSI "+(m5?.ema_rsi_trend||"—")+
      " · Scanner M5 direction "+(verdict.m5_direction||"—")+
      " · Final Strategy Gate "+(verdict.strategy_gate||"—")+
      " · Candle closed "+closeUtc);
    text("comparisonScannerReason",matched?(verdict.strategy_reason||"All comparisons match"):
      "Scanner or broker timeframe snapshots differ. Wait for both views to refresh and show MATCHED before comparing entry decisions. "+(verdict.strategy_reason||""));
    $("comparisonRows").innerHTML=data.rows.map(x=>
      '<tr><td class="symboltext">'+esc(x.timeframe)+'</td>'+
      '<td><span class="signal '+pretty(x.candle_bias)+'">'+esc(x.candle_bias)+'</span></td>'+
      '<td>'+badgeTrend(x.ema_rsi_trend)+'</td>'+
      '<td>'+esc(number(x.open))+'</td><td>'+esc(number(x.close))+'</td>'+
      '<td>'+esc(new Date(x.candle_closed_utc).toISOString().slice(0,19).replace("T"," "))+'</td>'+
      '<td>'+esc(age(x.closed_age_seconds))+'</td></tr>'
    ).join("");
  }catch(err){
    text("comparisonSource","UNAVAILABLE");
    text("comparisonStrategyGate","SYNC PENDING");
    $("comparisonStrategyGate").className="signal hold";
    text("comparisonStrategyGateMeta","No verified strategy signal");
    text("comparisonM5Direction","Scanner direction unavailable");
    text("comparisonFreshness","Broker data stale or not verified");
    text("comparisonM5Bias","—");
    text("comparisonM5Trend","—");
    text("comparisonM5Time","No verified M5 candle");
    text("comparisonScannerMatch","Scanner alignment unavailable");
    text("comparisonScannerDetails","Unable to verify identical broker candle timestamps.");
    text("comparisonScannerReason","Do not use stale or mismatched comparisons as an entry signal.");
    $("comparisonRows").innerHTML='<tr><td colspan="7">Broker candle comparison unavailable: '+esc(err.message)+'</td></tr>';
  }
}

async function refreshOverview(){
  if(ui.busy)return;
  ui.busy=true;
  try{
    const d=await getJson("overview");
    ui.overview=d;
    renderServices(d);
    renderSignals(d);
    renderRisk(d);
    renderAccount(d);
    renderScanner(d);
    renderExecution(d);
    syncComparisonSelector(d);
    if(ui.view==="compare")loadComparison();
    if(ui.view==="signals"){void loadDecisionIntelligence();}
    const before=ui.symbol;
    renderMarkets(d);
    if(before!==ui.symbol || !ui.chart.length)await loadChart();
    text("footerUpdated","Last synced "+new Date().toLocaleTimeString()+" · Refresh every 20 sec");
    $("safetyNotice").classList.remove("error-band");
  }catch(err){
    $("connectionDot").className="dot bad";
    text("connectionLabel","APEX feed unavailable");
    text("refreshLabel","DISCONNECTED");
    $("safetyNotice").classList.add("error-band");
    text("footerUpdated","Unable to refresh: "+err.message);
  }finally{ui.busy=false;}
}
async function loadChart(){
  if(!ui.symbol)return;
  try{
    const data=await getJson("chart?symbol="+encodeURIComponent(ui.symbol)+"&timeframe="+encodeURIComponent(ui.frame));
    if(ui.symbol!==data.symbol)return;
    ui.chart=data.bars||[];
    $("chartEmpty").style.display=ui.chart.length?"none":"block";
    paint();
  }catch(_){ui.chart=[];$("chartEmpty").style.display="block";text("chartEmpty","Market candles unavailable");}
}
function paint(){
  const canvas=$("marketChart");
  if(!canvas)return;
  const rect=canvas.getBoundingClientRect();
  if(!rect.width||!rect.height)return;
  const pixelRatio=window.devicePixelRatio||1;
  canvas.width=Math.round(rect.width*pixelRatio);
  canvas.height=Math.round(rect.height*pixelRatio);
  const ctx=canvas.getContext("2d");ctx.setTransform(pixelRatio,0,0,pixelRatio,0,0);
  const w=rect.width,h=rect.height;
  ctx.clearRect(0,0,w,h);
  const bars=ui.chart.slice(-95);
  if(!bars.length)return;
  const left=9,right=65,top=16,bottom=27;
  const plotW=w-left-right, plotH=h-top-bottom;
  const high=Math.max(...bars.map(x=>x.h)), low=Math.min(...bars.map(x=>x.l));
  const spread=Math.max(high-low,Number.EPSILON),padding=spread*.09;
  const max=high+padding,min=low-padding;
  const y=(p)=>top+plotH*(max-p)/(max-min);
  ctx.font="10px Inter,system-ui,sans-serif";
  ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const yy=top+i*plotH/4;
    ctx.strokeStyle="#233246";ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(w-right+5,yy);ctx.stroke();
    const val=max-(max-min)*i/4;
    ctx.fillStyle="#8094ad";ctx.fillText(number(val),w-right+9,yy+3);
  }
  const step=plotW/bars.length;
  bars.forEach((b,i)=>{
    const x=left+step*(i+.5),up=b.c>=b.o;
    ctx.strokeStyle=up?"#40cfa0":"#f16a87";ctx.fillStyle=ctx.strokeStyle;
    ctx.beginPath();ctx.moveTo(x,y(b.h));ctx.lineTo(x,y(b.l));ctx.stroke();
    const yo=y(b.o),yc=y(b.c),rh=Math.max(1,Math.abs(yc-yo));
    ctx.fillRect(x-Math.max(1,step*.27),Math.min(yo,yc),Math.max(2,step*.54),rh);
  });
  [0,Math.floor(bars.length/2),bars.length-1].forEach((i)=>{
    const bar=bars[i];if(!bar)return;
    const x=left+step*(i+.5);
    ctx.fillStyle="#7f93ac";ctx.font="10px Inter,system-ui,sans-serif";
    ctx.fillText(new Date(bar.t*1000).toISOString().slice(5,16).replace("T"," "),Math.min(x,w-right-70),h-5);
  });
  const last=bars.at(-1);
  if(last){
    const yy=y(last.c);
    ctx.setLineDash([3,4]);ctx.strokeStyle="#6fd8f9";ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(w-right,yy);ctx.stroke();ctx.setLineDash([]);
  }
}
/* Read-only ABUTRON APEX mandatory AI, SMC and ICT status. */
async function loadAiSmcIctModel(){
 if(ui.view!=="signals")return;
 try{
  const d=await getJson("ai-smc-ict-status");
  if(ui.view!=="signals")return;
  if(d.available!==true||d.schema!=="abutron.apex.ai_smc_ict.operator_status.v1"||
     d.environment!=="DEMO"||d.live_trading_allowed!==false||
     !Array.isArray(d.accounts)||!Array.isArray(d.recent_decisions))
   throw Error("Decision source not trusted");
  const tally=d.post_mandatory_enabled_decisions||{};
  const n=k=>Number(tally[k])||0;
  const holds=["VETO_SMC","VETO_AI","HOLD_AI","HOLD_SMC","HOLD_ICT","HOLD_BAD_EVIDENCE"].reduce((a,k)=>a+n(k),0);
  const mode=d.filter_enabled===true&&d.confirmation_mode==="mandatory_confirm"?"MANDATORY · DEMO":
             d.filter_enabled===true?"VETO ONLY · DEMO":"OFF";
  text("aiModelMode",mode);
  text("aiModelOn",d.accounts.filter(a=>a.effective_enabled===true).length+"/"+d.accounts.length);
  text("aiModelChecks",Number(d.post_mandatory_enabled_total)||0);
  text("aiModelHolds",holds);
  text("aiModelConfirmed",n("CONFIRMED_ALL"));
  const mark=(yes,y,z)=>'<span class="'+(yes?"val-up":"val-down")+'">'+esc(yes?y:z)+'</span>';
  $("aiModelAccountRows").innerHTML=d.accounts.length?d.accounts.map(a=>
   '<tr><td class="symboltext">'+esc(a.account_suffix)+'</td>'+
   '<td>'+mark(a.effective_enabled===true,"ON","OFF")+'</td>'+
   '<td>'+esc(a.broker_feed_fresh===true?a.broker_open_positions:"UNVERIFIED")+'</td>'+
   '<td>'+esc(a.ledger_active_positions??"UNVERIFIED")+'</td>'+
   '<td>'+mark(a.broker_feed_fresh===true&&!a.broker_ledger_mismatch,"MATCHED",
     a.broker_ledger_mismatch?"BROKER / LEDGER MISMATCH":"NOT VERIFIED")+'</td>'+
   '<td>'+esc(a.filter_mode||"UNVERIFIED")+(a.safety_hold?" · SAFETY HOLD":"")+'</td></tr>'
  ).join(""):'<tr><td colspan="6">No verified DEMO accounts.</td></tr>';
  const activation=Date.parse(d.mandatory_activated_at_utc||"");
  const entries=d.recent_decisions.filter(e=>Number.isFinite(activation)&&
    Date.parse(e.recorded_at_utc)>=activation).slice(0,12);
  $("aiModelDecisionRows").innerHTML=entries.length?entries.map(e=>
   '<tr><td>'+esc(e.account_suffix)+(e.account_enabled_when_recorded?"":" · OFF")+'</td>'+
   '<td class="symboltext">'+esc(e.symbol)+'</td>'+
   '<td>'+esc(e.side)+'</td><td>'+esc(e.ai||"UNREVIEWED")+'</td>'+
   '<td>'+esc(e.smc||"NOT CONFIRMED")+'</td>'+
   '<td>'+esc(e.ict||"NOT CONFIRMED")+
     (e.ict_pattern?" · "+esc(e.ict_pattern):"")+'</td>'+
   '<td><span class="signal '+pretty(e.decision)+'">'+esc(e.decision)+'</span></td>'+
   '<td>'+esc(clock(e.recorded_at_utc))+'</td>'+
   '<td>'+esc(e.ledger_state==="NOT_ATTEMPTED"?"NO ORDER":e.ledger_state)+'</td></tr>'
  ).join(""):'<tr><td colspan="9">No post-activation mandatory decisions recorded; no broker order implied.</td></tr>';
  text("aiModelUpdated","Updated "+clock(d.generated_at_utc)+
   " · Entry-filter decisions are not verified fills or profit. Only the existing APEX order and risk router can execute DEMO orders.");
 }catch(_err){
  if(ui.view!=="signals")return;
  text("aiModelMode","UNVERIFIED · HOLD");
  ["aiModelOn","aiModelChecks","aiModelHolds","aiModelConfirmed"].forEach(k=>text(k,"—"));
  $("aiModelAccountRows").innerHTML='<tr><td colspan="6">Latest broker account and position reconciliation unavailable.</td></tr>';
  $("aiModelDecisionRows").innerHTML='<tr><td colspan="9">AI + SMC + ICT decision source unavailable or stale; no old status shown.</td></tr>';
  text("aiModelUpdated","Mandatory filter verification unavailable. The existing APEX execution gates remain authoritative.");
 }
}

/* Read-only native broker and historical decision intelligence.
   Neither authorizes nor transmits broker orders. */
async function loadDecisionIntelligence(){
  if(ui.view!=="signals")return;
  try{
    const data=await getJson("decision-intelligence");
    if(ui.view!=="signals")return;
    if(data.available!==true || data.total_symbols!==13 ||
       !Array.isArray(data.all_symbols) || data.all_symbols.length!==13 ||
       !Array.isArray(data.top_three) || data.top_three.length>3)
       throw Error("Broker research verification failed");
    const top=data.top_three;
    const all=data.all_symbols;
    const span=all.length?all[0].historical.historical_span_hours:null;
    text("aiResearchStatus","VERIFIED RESEARCH ONLY");
    text("aiSymbolCount",data.total_symbols+"/13");
    text("aiCandidateCount",data.qualified_research_count);
    text("aiHistorySpan",span==null?"—":number(span)+" hours");
    text("aiFeedAge",age(data.market_age_seconds));
    text("aiResearchUpdated","Broker snapshot: "+clock(data.broker_snapshot_utc)+
      " · Scanner: "+clock(data.scanner_snapshot_utc)+
      " · Scanner rankings are advisory; mandatory Qwen/SMC/ICT results appear in the panel above.");
    text("aiHistoryCaveat",data.historical_limitations+
      " Historical M5 volatility cannot establish a profitable edge or validated win rate. "+
      "The original broker, risk and one-position-per-symbol controls remain in force.");
    const flags=(r)=>"<span class='signal "+pretty(r.proposal)+"'>"+esc(r.proposal)+"</span>";
    $("aiTopThree").innerHTML=top.length?top.map((r,i)=>
      '<article class="ai-top-card"><div class="panel-head">'+
      '<span class="ai-flag">RANK '+esc(i+1)+'</span>'+flags(r)+'</div>'+
      '<div class="ai-symbol">'+esc(r.symbol)+'</div>'+
      '<div class="ai-data">Rule confluence: <strong>'+esc(r.evidence_score)+'/100</strong> · '+esc(r.higher_tf_confirmations)+
      '/3 higher-timeframe confirmations · RSI '+esc(number(r.m5_rsi))+'</div>'+
      '<div class="ai-data">Local Qwen: '+esc(r.qwen_advisory)+' · '+esc(r.reason)+'</div>'+
      '<div class="ai-historical">History: '+esc(r.historical.completed_m5_returns)+
      ' completed M5 returns / '+esc(r.historical.historical_span_hours)+
      'h · Volatility: '+esc(r.historical.volatility_context)+
      ' · Source: '+esc(r.historical.source)+
      ' · Historical win rate: NOT VALIDATED</div></article>'
    ).join(""):'<div class="ai-research-empty">No current BUY/SELL setup passes the original APEX scanner rules. The system will not invent a top-three list.</div>';
    const slotCount=Math.max(0,3-top.length);
    if(slotCount){
      $("aiTopThree").innerHTML+=Array.from({length:slotCount},(_,i)=>
       '<div class="ai-research-empty">Slot '+esc(top.length+i+1)+
       ' · No other qualified setup at this broker snapshot</div>').join("");
    }
    $("aiAllSymbols").innerHTML=all.map((r,i)=>{
      const qualified=r.evidence_score!==null;
      const historical=r.historical;
      return '<tr><td>'+esc(qualified?i+1:"—")+'</td>'+
        '<td class="symboltext">'+esc(r.symbol)+'</td>'+
        '<td>'+flags(r)+'</td>'+
        '<td>'+esc(qualified?r.evidence_score+"/100":"—")+'</td>'+
        '<td>'+esc(r.higher_tf_confirmations)+'/3</td>'+
        '<td>'+esc(historical.closed_m5_bars)+' ('+esc(historical.evidence_depth)+')</td>'+
        '<td>'+esc(historical.volatility_context)+'</td>'+
        '<td>'+esc(r.qwen_advisory)+'</td>'+
        '<td>'+esc(r.reason)+'</td></tr>';
    }).join("");
  }catch(err){
    if(ui.view!=="signals")return;
    text("aiResearchStatus","REVERIFYING · SAFE HOLD");
    // Recover from a transient broker/scanner publication window without
    // suppressing errors or weakening any broker execution safeguards.
    if(!ui.aiRetryScheduled){
      ui.aiRetryScheduled=true;
      setTimeout(()=>{
        ui.aiRetryScheduled=false;
        if(ui.view==="signals")void loadDecisionIntelligence();
      },4000);
    }
    text("aiSymbolCount","—");
    text("aiCandidateCount","—");
    text("aiHistorySpan","—");
    text("aiFeedAge","—");
    text("aiResearchUpdated","Verified research unavailable. No stale setup is displayed or sent to execution.");
    $("aiTopThree").innerHTML='<div class="ai-research-empty">Current native broker or historical evidence is unavailable. No research recommendations.</div>';
    $("aiAllSymbols").innerHTML='<tr><td colspan="9">No verified broker and historical snapshot: '+esc(err.message)+'</td></tr>';
  }
}

document.querySelectorAll("[data-view]").forEach((el)=>el.addEventListener("click",()=>changeUI(el.dataset.view)));
document.querySelectorAll("[data-jump]").forEach((el)=>el.addEventListener("click",()=>changeUI(el.dataset.jump)));
$("symbolSelect").addEventListener("change",(e)=>{ui.symbol=e.target.value;loadChart();});
$("comparisonSymbol").addEventListener("change",(e)=>{ui.compareSymbol=e.target.value;loadComparison();});
$("timeframeSelect").addEventListener("change",(e)=>{ui.frame=e.target.value;loadChart();});
$("marketSearch").addEventListener("input",()=>ui.overview&&renderMarkets(ui.overview));
$("refreshNow").addEventListener("click",()=>{refreshOverview();loadChart();});
window.addEventListener("resize",paint);
// Display the current UTC clock independently of the broker snapshot's collection timestamp.
function updateMarketClock(){
  const now=new Date();
  const marketTime=now.toISOString().slice(11,19)+" UTC";
  const marketDate=new Intl.DateTimeFormat("en-GB",{
    day:"2-digit",month:"short",year:"numeric",timeZone:"UTC"
  }).format(now);
  text("clockUtc",marketTime);
  text("marketDateUtc",marketDate);
  text("executionMarketTimeUtc",marketTime);
  text("executionMarketDateUtc",marketDate);
}
updateMarketClock();
setInterval(updateMarketClock,1000);
setInterval(refreshOverview,20000);
setInterval(()=>{if(ui.view==="overview")loadChart();},60000);
setInterval(()=>{if(ui.view==="compare")loadComparison();},60000);
// Deep link support for the eight-timeframe audit; never authorizes orders.
const qs=new URLSearchParams(window.location.search);
const wanted=qs.get("view");
if(wanted==="signals"){
  changeUI("signals");
}else if(wanted==="compare"){
  ui.compareSymbol=qs.get("symbol")||"Volatility 75 Index.0";
  changeUI("compare");
}else{
  changeUI("overview");
}
refreshOverview();
