/* ABUTRON APEX: broker-isolated FP Markets panels on the live operator pages.
   Deriv renderer, order router and original chart remain completely untouched. */
(() => {
 "use strict";
 const API="/apex/api/";
 const FRAMES=["M1","M5","M15","H1","H4","D1"];
 const views=["overview","markets","scanner","signals","compare","account","execution","systems"];
 const data={snapshot:null,symbol:"EURUSD",frame:"M5",busy:false,accountSlot:0,accounts:[]};
 const $=id=>document.getElementById(id);
 const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=String(txt);return n;};
 const num=(x,d=4)=>typeof x==="number"&&Number.isFinite(x)?x.toLocaleString("en-US",{maximumFractionDigits:d}):"—";
 const utc=x=>{const d=new Date(x);return Number.isFinite(d.getTime())?d.toLocaleString("en-GB",{timeZone:"UTC",dateStyle:"short",timeStyle:"medium"})+" UTC":"—";};
 const text=(id,value)=>{const node=$(id);if(node)node.textContent=String(value??"—");};
 const headings={
  overview:["FP MARKETS · NATIVE DATA","Broker-native feed and separate research controls"],
  markets:["FP MARKETS · MARKET WATCH","13 FP Markets symbols · genuine bid/ask and M5 closed candles"],
  scanner:["DETERMINISTIC MULTI-TIMEFRAME RESEARCH","All 13 FP Markets strategy proposals"],
  signals:["FP MARKETS DEMO · CURRENT RESEARCH POLICY","M5 candle qualification · TradingAgents · native broker risk"],
  compare:["FP MARKETS DEMO · 6 VERIFIED TIMEFRAMES","APEX strategy signal vs. completed candle and EMA/RSI trend"],
  account:["FP MARKETS · ACCOUNT & TRADE HISTORY","Broker session and verified trading data availability"],
  execution:["FP MARKETS · EXECUTION STATUS","Distinct FP DEMO execution state; existing Deriv unchanged"],
  systems:["FP MARKETS · DATA INFRASTRUCTURE","Native collector, scanner and model publication health"]
 };
 function panel(id,view){
  const home=$(view);if(!home)return null;
  const section=el("article","panel fp-panel");section.id="fp-panel-"+id;
  const h=el("div","panel-head fp-panel-head");
  const left=el("div");left.append(el("p","panel-kicker",headings[id][0]),el("h2","",headings[id][1]));
  h.append(left,el("span","fp-tag","READ-ONLY · DEMO"));
  section.append(h);
  home.append(section);return section;
 }
 const roots=Object.fromEntries(views.map(v=>[v,panel(v,v)]));
 const accountSelectors=[];
 for(const root of Object.values(roots)){
   if(!root)continue;
   const label=el("label","fp-muted","FP Markets DEMO account · ");
   const select=el("select","fp-account-chooser");
   select.setAttribute("aria-label","Choose verified FP Markets DEMO account");
   label.append(select);root.append(label);accountSelectors.push(select);
   select.addEventListener("change",()=>{
     const next=Number(select.value);
     if(!Number.isInteger(next)||next<0||next>5)return;
     data.accountSlot=next;
     for(const other of accountSelectors)other.value=String(next);
     void refresh();
   });
 }
 function chooseAccounts(accounts){
   data.accounts=Array.isArray(accounts)?accounts.filter(x=>Number.isInteger(x.slot)&&x.slot>=0&&x.slot<=5):[];
   if(!data.accounts.some(x=>x.slot===data.accountSlot))data.accountSlot=0;
   for(const select of accountSelectors){
     select.replaceChildren();
     for(const account of data.accounts){
       const option=el("option","","FP "+account.account_masked+" · "+account.fresh_quotes+"/13"+
         (account.available?" verified":" unavailable"));
       option.value=String(account.slot);select.append(option);
     }
     select.value=String(data.accountSlot);
   }
 }
 // One persistent broker choice across the three strategy research views.
 // Keep the original Deriv DOM and renderers intact: no trading-path rewrites.
 const brokerViews=["scanner","compare","signals"];
 const originalSections={};
 const brokerButtons={};
 const extraFpSections={signals:[]};
 const brokerLabel=document.querySelector(".broker-title");
 const originalBrokerLabel=brokerLabel?.textContent||"Deriv MT5 · DEMO";
 let selectedBroker="deriv";
 for(const view of brokerViews){
   const home=$(view);
   if(!home||!roots[view])continue;
   originalSections[view]=Array.from(home.children).filter(n=>n!==roots[view]);
   const choice=el("div","fp-broker-switch");
   choice.setAttribute("role","group");
   choice.setAttribute("aria-label",view+" broker selection");
   const deriv=el("button","fp-broker-button fp-broker-selected","DERIV · 13 INDICES");
   const fp=el("button","fp-broker-button","FP MARKETS · 13 INSTRUMENTS");
   for(const btn of [deriv,fp])btn.type="button";
   choice.append(deriv,fp);
   home.prepend(choice);
   brokerButtons[view]={deriv,fp};
   deriv.addEventListener("click",()=>selectBroker("deriv"));
   fp.addEventListener("click",()=>selectBroker("fp"));
 }
 function applyBrokerSelection(){
   const useFp=selectedBroker==="fp";
   for(const view of brokerViews){
     for(const native of originalSections[view]||[])native.hidden=useFp;
     if(roots[view])roots[view].hidden=!useFp;
     for(const section of extraFpSections[view]||[])section.hidden=!useFp;
     const buttons=brokerButtons[view];
     if(!buttons)continue;
     buttons.deriv.classList.toggle("fp-broker-selected",!useFp);
     buttons.fp.classList.toggle("fp-broker-selected",useFp);
     buttons.deriv.setAttribute("aria-pressed",String(!useFp));
     buttons.fp.setAttribute("aria-pressed",String(useFp));
   }
   const active=document.querySelector(".view.active")?.id;
   const inBrokerView=brokerViews.includes(active);
   if(brokerLabel)brokerLabel.textContent=useFp&&inBrokerView?
     "FP Markets MT5 · DEMO":originalBrokerLabel;
   if(inBrokerView&&useFp){
     const label={scanner:"Strategy Scanner",compare:"Candle Comparison",signals:"AI Decisions"}[active];
     for(const id of ["screenName","pageHeading"]){const n=$(id);if(n)n.textContent=label+" · FP Markets";}
     const sub=$("pageSubhead");if(sub)sub.textContent="FP Markets broker-native DEMO data · same research page, independent execution status";
   }
 }
 function selectBroker(next){
   selectedBroker=next;
   applyBrokerSelection();
   const view=document.querySelector(".view.active")?.id;
   if(next==="fp"&&view==="compare"){
     if(!valid())void refresh();
     else{void comparison();void chart();}
   }
   if(next==="fp"&&!valid())void refresh();
 }
 document.querySelectorAll(".navitem[data-view]").forEach(button=>button.addEventListener("click",()=>{
   applyBrokerSelection();
   if(button.dataset.view==="compare"&&selectedBroker==="fp"){
     if(!valid())void refresh();else{void comparison();void chart();}
   }
 }));
 function makeTable(root,headers,id){
  const wrap=el("div","table-scroll fp-scroll");
  const table=el("table","fp-table");const thead=el("thead");
  const tr=el("tr");headers.forEach(x=>tr.append(el("th","",x)));thead.append(tr);
  const tbody=el("tbody");tbody.id=id;
  table.append(thead,tbody);wrap.append(table);root.append(wrap);return tbody;
 }
 function row(tbody,values){
  const tr=el("tr");values.forEach(v=>{
   const td=el("td");
   if(typeof v==="object"&&v){td.textContent=String(v.text??"");td.className=v.className??"";}
   else td.textContent=String(v??"—");
   tr.append(td);
  });tbody.append(tr);
 }
 function message(root,textValue){
  const n=el("p","fp-muted",textValue);root.append(n);return n;
 }
 const metrics=el("div","fp-metrics");roots.overview?.append(metrics);
 const overviewNote=message(roots.overview,"Waiting for FP Markets broker data…");
 const marketSearch=el("input","search fp-search");marketSearch.type="search";marketSearch.placeholder="Filter FP Markets instruments";
 marketSearch.setAttribute("aria-label","Filter FP Markets instruments");
 roots.markets?.append(marketSearch);
 const marketRows=makeTable(roots.markets,["Symbol","MT5 broker symbol","Bid","Ask","Quote age","M5 close","M5 change","M15","H1","Decision"],"fp-market-rows");
 const scannerRows=makeTable(roots.scanner,["Instrument","Family","M1 trend","M5 candle body (NOT signal)",
   "M5 EMA/RSI trend","M5 EMA/RSI direction","M15 trend","H1 trend","H4 trend","D1 trend",
   "RSI M5","APEX strategy signal","Qwen research (advisory)","M5 entry screening",
   "Native account control","Evidence / Reason"],"fp-scanner-rows");
 scannerRows.parentElement.querySelector("table")?.classList.add("fp-parity-table");
 const scannerNote=message(roots.scanner,"FP Markets · 13 native MT5 instruments · M1/M5/M15/H1/H4/D1 completed-candle evidence. Original APEX EMA/RSI, M15/H1/H4, closed-M5 quality screening and independent TradingAgents review. Native order authority is separate.");
 const signalsRows=makeTable(roots.signals,["Symbol","APEX","Qwen AI","SMC","ICT","Combined","Final","Veto / reason"],"fp-signal-rows");
 const signalNote=message(roots.signals,"FP Markets research decisions do not independently authorize broker orders.");
 // The full Deriv-format FP decision panels below supersede this legacy mini-table.
 signalsRows.parentElement.hidden=true;
 signalNote.hidden=true;
 // Match Deriv's AI Decisions hierarchy: policy metrics, account eligibility,
 // mandatory decision evidence, and a separate ranked research panel.
 const fpAiIntro=el("p","muted","Original APEX EMA/RSI with strict M15/H1/H4 alignment and M5 entry-quality checks. Qwen agreement and native broker/risk gates are separate. Only the verified APEX entry gate can create scanner proposals.");
 roots.signals.insertBefore(fpAiIntro,roots.signals.children[1]||null);
 const aiPolicyStats=el("div","ai-stats fp-ai-stats");roots.signals.append(aiPolicyStats);
 const fpAiAccountTitle=el("h3","ai-subtitle","Account-level order eligibility and reconciliation");
 roots.signals.append(fpAiAccountTitle);
 const aiAccountRows=makeTable(roots.signals,["DEMO account","Automatic trading","Broker open","Ledger active","Position reconciliation","Current filter"],"fp-ai-account-rows");
 roots.signals.append(el("h3","ai-subtitle","Latest M5 entry quality and TradingAgents decisions"));
 const aiDecisionRows=makeTable(roots.signals,["Account","Symbol","APEX","Qwen AI","M5 candle","Higher TF","Decision","Recorded · UTC","Broker status"],"fp-ai-decision-rows");
 roots.signals.append(el("p","table-foot","Research decisions are not broker fills. Native execution, receipts and positions are verified independently."));
 const aiResearchPanel=el("article","panel ai-insights fp-panel");
 const aiResearchHead=el("div","panel-head");
 const aiResearchLeft=el("div");
 aiResearchLeft.append(el("p","panel-kicker","FP MARKETS DEMO · BROKER-NATIVE RESEARCH"),
   el("h2","","AI Decisions · current setup intelligence"));
 aiResearchHead.append(aiResearchLeft,el("span","chip","RESEARCH ONLY"));
 aiResearchPanel.append(aiResearchHead);
 aiResearchPanel.append(el("p","muted","Original APEX M5 scanner and actual FP Markets MT5 completed candles. Confluence is descriptive rule evidence, not a win-rate or order authorization."));
 const aiResearchStats=el("div","ai-stats fp-ai-stats");aiResearchPanel.append(aiResearchStats);
 aiResearchPanel.append(el("h3","ai-subtitle","Top three research setups · not executable"));
 const aiTopThree=el("div","ai-top-grid fp-ai-top-grid");aiResearchPanel.append(aiTopThree);
 aiResearchPanel.append(el("p","table-foot","No setup qualifies without a completed M5 entry-quality pass, exact-candle AI agreement, native authorization and broker-risk verification."));
 aiResearchPanel.append(el("h3","ai-subtitle","All 13 symbols · ranked by current research evidence"));
 const aiRankRows=makeTable(aiResearchPanel,["Rank","Instrument","APEX proposal","M5 candle","Higher TF alignment","M5 coverage","Volatility · ATR","Qwen advisory","Reason / limit"],"fp-ai-rank-rows");
 aiResearchPanel.append(el("p","table-foot","Ordering is descriptive, not a predicted win rate. Entry-quality evidence, broker receipts and actual P/L are separate."));
 $("signals")?.append(aiResearchPanel);
 extraFpSections.signals.push(aiResearchPanel);
 function fillAiStats(container,pairs){
   container.replaceChildren();
   for(const [name,value] of pairs){const item=el("div");item.append(el("span","",name),el("strong","",String(value)));container.append(item);}
 }
 // Mirror Deriv's four comparison metrics and seven-column timeframe table.
 const compareStrip=el("div","account-strip comparison-strip fp-compare-strip");
 const compareMetrics={};
 for(const [key,heading] of [
   ["strategy","APEX STRATEGY SIGNAL · SAME AS SCANNER"],
   ["body","M5 CANDLE BODY · NOT A TRADE SIGNAL"],
   ["trend","M5 MULTI-CANDLE EMA/RSI TREND"],
   ["sync","SCANNER / BROKER SNAPSHOT SYNC"]]){
   const item=el("article","metric");const strong=el("strong","","—");const small=el("small","","Verifying FP broker candles");
   item.append(el("span","",heading),strong,small);compareStrip.append(item);
   compareMetrics[key]={strong,small};
 }
 roots.compare?.append(compareStrip);
 const comparisonNotice=el("div","notice fp-comparison-notice");
 const noticeBody=el("div");const noticeTitle=el("b","","Verifying FP Strategy Scanner alignment");
 const noticeDesc=el("span","","Comparing the same M5 broker candle with the FP scanner.");
 noticeBody.append(noticeTitle,noticeDesc);
 comparisonNotice.append(el("span","notice-icon","◈"),noticeBody);
 roots.compare?.append(comparisonNotice);
 const compareLead=el("p","muted","APEX strategy signals and broker execution are separate. M5 candle bias is not an order. See the verified execution health panel for current account controls.");
 roots.compare?.append(compareLead);
 const compareRows=makeTable(roots.compare,["Timeframe","Candle body (NOT a signal)","EMA/RSI trend","Open","Close","Closed at (UTC)","Time since close"],"fp-comparison-rows");
 compareRows.parentElement.querySelector("table")?.classList.add("fp-comparison-table");
 roots.compare?.append(el("p","table-foot","Six verified FP timeframes: M1, M5, M15, H1, H4, D1. MT5 candle time is the opening timestamp; close time is opening + timeframe interval. Deriv's extra M3/M30 rows are not fabricated."));
 const chartControls=el("div","fp-controls");
 const symbolSelect=el("select","");symbolSelect.setAttribute("aria-label","FP Markets chart symbol");
 const frameSelect=el("select","");frameSelect.setAttribute("aria-label","FP Markets chart timeframe");
 FRAMES.forEach(tf=>{const opt=el("option","",tf);opt.value=tf;frameSelect.append(opt)});
 frameSelect.value=data.frame;
 chartControls.append(el("label","fp-label","Instrument"),symbolSelect,el("label","fp-label","Timeframe"),frameSelect);
 roots.compare?.append(chartControls);
 const chartNote=message(roots.compare,"Completed broker candles only; a chart is not an order signal.");
 const canvas=el("canvas","fp-chart");canvas.setAttribute("role","img");canvas.setAttribute("aria-label","FP Markets broker-native completed-candle chart");
 roots.compare?.append(canvas);
 const accountBody=el("div","fp-account");
 roots.account?.append(accountBody);
 const executionBody=el("div","fp-account");
 roots.execution?.append(executionBody);
 const systemBody=el("div","fp-account");
 roots.systems?.append(systemBody);
 applyBrokerSelection();
 const valid=()=>data.snapshot?.available===true;
 function setContent(container,items){
  container.replaceChildren();
  for(const [heading,value] of items){
   const card=el("div","fp-stat");
   card.append(el("span","",heading),el("strong","",String(value)));
   container.append(card);
  }
 }
 function setRows(tbody,cols,items){
  tbody.replaceChildren();
  for(const item of items)row(tbody,cols(item));
  if(!items.length)row(tbody,["No current matching FP Markets data"]);
 }
 function render(){
  const x=data.snapshot;
  if(!valid()){
   for(const body of [marketRows,scannerRows,signalsRows]){body.replaceChildren();row(body,["FP Markets native data unavailable or stale. No inferred signals."])}
   metrics.replaceChildren();overviewNote.textContent="FP Markets data unavailable or stale · "+(x?.reason||"refresh required");
   fillAiStats(aiPolicyStats,[["FP DEMO trading accounts ON","UNVERIFIED"],["Current M5 APEX candidates","UNAVAILABLE"],
      ["M5 entry-quality HOLDs","UNAVAILABLE"],["AI direction agreements","UNAVAILABLE"]]);
   fillAiStats(aiResearchStats,[["Symbols reviewed","UNAVAILABLE"],["Current BUY/SELL setups","UNAVAILABLE"],
      ["Verified timeframe series","UNAVAILABLE"],["Native feed timestamp","UNAVAILABLE"]]);
   aiTopThree.replaceChildren(el("div","empty","FP Markets broker data unavailable; no entries can be inferred."));
   for(const body of [aiAccountRows,aiDecisionRows,aiRankRows,compareRows]){
     body.replaceChildren();row(body,["FP Markets evidence unavailable; no inferred trades."]);
   }
   setContent(accountBody,[["FP Markets","Feed unavailable"],["Trade history","Not verified"]]);
   setContent(executionBody,[["FP Markets automatic trading","OFF / UNAVAILABLE"],["Order routing","Not connected"]]);
   setContent(systemBody,[["Native feed","Unavailable"],["Scanner","Unavailable"]]);return;
  }
  setContent(metrics,[
   ["FP Markets quotes",x.fresh_quotes+"/"+x.quote_count],
   ["Completed-candle series",x.timeframe_series+"/78"],
   ["APEX proposals",x.scanner_proposals],
   ["AI matches",x.ai_agreements],
   ["TradingAgents approvals",x.tradingagents_ai_agreements],
   ["FP auto trading",x.trading_controls?.effective_enabled?"ON":"OFF"]
  ]);
  overviewNote.textContent="Connected FP Markets "+x.environment+" "+x.account_masked+
    " · "+x.broker_server+" · "+x.fresh_quotes+"/13 verified broker symbols"+
    (x.coverage_complete===false?" · PARTIAL / NOT CERTIFIED · XAUUSD and USOIL unavailable":"")+
    " · Feed "+utc(x.native_feed_at_utc)+" · Broker orders require independent native risk approval.";
  const rows=x.symbols;
  const keyword=marketSearch.value.trim().toLowerCase();
  setRows(marketRows,r=>[r.symbol,r.broker_symbol,num(r.bid,6),num(r.ask,6),num(r.quote_age_seconds,0)+" s",
    num(r.m5_last_close,6),num(r.m5_change_pct,3)+"%",r.higher_timeframe_direction,
    r.m5_direction,{text:r.final_decision,className:"fp-hold"}],
    rows.filter(r=>!keyword||r.symbol.toLowerCase().includes(keyword)||r.broker_symbol.toLowerCase().includes(keyword)));
  const direction=x=>({text:x||"—",className:
    x==="UP"||x==="BUY"?"fp-pass":x==="DOWN"||x==="SELL"?"fp-veto":"fp-neutral"});
  setRows(scannerRows,r=>{
    const t=r.timeframe_trends||{};
    const advisor=r.ai_direction||"PENDING";
    const evidence=r.scanner_reason||"ENTRY_EVIDENCE_UNAVAILABLE";
    return [r.symbol,r.family||"—",direction(t.M1),direction(r.m5_candle_body),
       direction(t.M5),direction(r.m5_direction),direction(t.M15),direction(t.H1),
       direction(t.H4),direction(t.D1),num(r.rsi14,2),direction(r.proposal),
       direction(advisor),{text:r.proposal==="HOLD"?"HOLD":"M5 APPROVED",className:r.proposal==="HOLD"?"fp-hold":"fp-pass"},
       {text:x.trading_controls?.effective_enabled?"CONTROL ON · RISK GATED":"CONTROL OFF",className:"fp-neutral"},evidence];
  },rows);
  scannerNote.textContent="FP Markets native MT5 · "+x.fresh_quotes+"/13 verified symbols · "+
    x.timeframe_series+"/78 broker-native timeframe series"+
    (x.unavailable_symbols?.length?" · UNAVAILABLE: "+x.unavailable_symbols.join(", "):"")+
    " · Broker "+utc(x.native_feed_at_utc)+" · Scanner "+utc(x.scanner_at_utc)+
    " · Broker authorization remains independent. Partial coverage is shown explicitly.";
  setRows(signalsRows,r=>[r.symbol,r.proposal,r.ai_status+
    (r.ai_direction?" / "+r.ai_direction:""),{text:r.smc,className:r.smc==="VETO"?"fp-veto":"fp-pass"},
    {text:r.ict,className:r.ict==="VETO"?"fp-veto":"fp-pass"},
    r.research_direction,{text:r.final_decision,className:"fp-hold"},
    r.smc_reason||r.scanner_reason||"No positive combined confirmation"],rows);
  signalNote.textContent="Model "+(rows.find(r=>r.ai_model)?.ai_model||"Qwen advisory pending")+
    " · Last AI "+utc(x.ai_review_at_utc)+
    " · SMC/ICT are rule-based candle evidence, not institutional order-flow proof.";
  const candidates=rows.filter(r=>r.proposal==="BUY"||r.proposal==="SELL");
  const entryHolds=rows.filter(r=>String(r.scanner_reason||"").startsWith("ENTRY_QUALITY_")).length;
  const matchedAi=candidates.filter(r=>r.ai_direction===r.proposal&&r.ai_status==="PASS").length;
  fillAiStats(aiPolicyStats,[
    ["FP DEMO trading accounts ON",x.trading_controls?.effective_enabled?"1":"0"],
    ["Current M5 APEX candidates",candidates.length],
    ["M5 entry-quality HOLDs",entryHolds],
    ["AI direction agreements",matchedAi]
  ]);
  setRows(aiAccountRows,r=>r,[
    ["FP DEMO "+x.account_masked,x.trading_controls?.effective_enabled?"ON · NATIVE RISK GATED":"OFF",
     x.verified_open_positions_count??"UNVERIFIED","SEE NATIVE ORDER JOURNAL",
     "BROKER HISTORY / RECEIPTS","SEE EXECUTION HEALTH PANEL"]
  ]);
  setRows(aiDecisionRows,r=>[
    "FP "+x.account_masked,r.symbol,r.proposal,
    r.ai_status+(r.ai_direction?" / "+r.ai_direction:""),
    r.m5_candle_body||"UNVERIFIED",
    r.higher_timeframe_direction||"UNVERIFIED",
    {text:r.final_decision,className:"fp-hold"},
    r.ai_status==="MODEL_REVIEW_COMPLETED"?utc(x.ai_review_at_utc):"NOT REVIEWED",
    {text:x.trading_controls?.effective_enabled?"CONTROL ON · BROKER VERIFIED SEPARATELY":"CONTROL OFF",className:"fp-neutral"}
  ],rows);
  fillAiStats(aiResearchStats,[
    ["Broker verified symbols",x.fresh_quotes+" / 13"],
    ["Current BUY/SELL setups",candidates.length],
    ["Verified timeframe series",x.timeframe_series+" / 78"],
    ["Native feed timestamp",utc(x.native_feed_at_utc)]
  ]);
  aiTopThree.replaceChildren();
  const highest=[...candidates].sort((a,b)=>a.symbol.localeCompare(b.symbol)).slice(0,3);
  if(!highest.length)aiTopThree.append(el("div","empty","No BUY/SELL research setups on the latest FP M5 broker snapshot. No order is permitted."));
  for(const r of highest){
    const card=el("article","fp-ai-top-card");
    card.append(el("b","",r.symbol+" · "+r.proposal),
      el("small","","M5 candle "+r.m5_candle_body+" · M15/H1/H4 "+r.higher_timeframe_direction),
      el("small","","Qwen: "+r.ai_status+(r.ai_direction?" / "+r.ai_direction:"")),
      el("small","fp-hold","Research only · broker order evidence separate"));
    aiTopThree.append(card);
  }
  const ordered=[...rows].sort((a,b)=>
    Number(b.proposal!=="HOLD")-Number(a.proposal!=="HOLD")||a.symbol.localeCompare(b.symbol));
  setRows(aiRankRows,r=>[ordered.indexOf(r)+1,r.symbol,r.proposal,
    r.m5_candle_body+" / "+r.m5_direction,r.higher_timeframe_direction,
    typeof r.m5_bar_time==="number"?"BROKER VERIFIED":"NO CANDLE PROOF",
    num(r.atr14,6),r.ai_status+(r.ai_direction?" / "+r.ai_direction:""),
    r.scanner_reason||"No qualified entry"],ordered);
  setContent(accountBody,[
   ["Broker","FP Markets"],["Account",x.account_masked],
   ["Session",x.status+" · "+x.environment],["Automated trading",x.trading_controls.effective_enabled?"ON":"OFF"],
   ["Open positions",x.verified_open_positions_count??"UNVERIFIED"],["Realized / floating P&L","See broker trade history"]
  ]);
  if(!$("fp-history-warning")){const note=message(roots.account,x.trade_history_notice);note.id="fp-history-warning";}
  setContent(executionBody,[
   ["FP account",x.account_masked],["Automatic FP orders","OFF"],
   ["Broker execution adapter","Not installed"],["Research output","HOLD only"],
   ["Deriv execution settings","Unchanged by FP UI"]
  ]);
  setContent(systemBody,[
   ["Native quote freshness",x.fresh_quotes+"/13"],["Timeframe coverage",x.timeframe_series+"/78"],
   ["Collector timestamp",utc(x.native_feed_at_utc)],["Scanner timestamp",utc(x.scanner_at_utc)],
   ["Qwen timestamp",utc(x.ai_review_at_utc)],["UI publication",utc(x.generated_at_utc)]
  ]);
  const selected=data.symbol;
  symbolSelect.replaceChildren();
  for(const s of rows.filter(r=>r.available!==false)){
   const op=el("option","",s.symbol+" · "+s.broker_symbol);op.value=s.symbol;symbolSelect.append(op);
  }
  if(!rows.some(r=>r.symbol===selected&&r.available!==false)){
    const first=rows.find(r=>r.available!==false);
    data.symbol=first?.symbol||"EURUSD";
  }
  symbolSelect.value=data.symbol;
 }
 function plot(bars){
  if(!canvas.isConnected)return;
  const width=Math.max(290,Math.floor(canvas.clientWidth||760));
  const height=280,ratio=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
  const ctx=canvas.getContext("2d");if(!ctx)return;
  ctx.scale(ratio,ratio);ctx.clearRect(0,0,width,height);
  ctx.fillStyle="#091729";ctx.fillRect(0,0,width,height);
  if(!bars.length)return;
  const min=Math.min(...bars.map(b=>b.l)),max=Math.max(...bars.map(b=>b.h));
  const span=Math.max(max-min,0.00001);const top=16,bottom=height-26;
  const scaleY=y=>bottom-(y-min)/span*(bottom-top);
  ctx.strokeStyle="#283d54";ctx.lineWidth=1;
  for(let i=0;i<5;i++){const y=top+i*(bottom-top)/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
  const dx=(width-24)/bars.length;
  for(let i=0;i<bars.length;i++){
   const b=bars[i],x=12+(i+.5)*dx,up=b.c>=b.o;
   ctx.strokeStyle=up?"#3bd7a0":"#ff7777";ctx.fillStyle=ctx.strokeStyle;
   ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,scaleY(b.h));ctx.lineTo(x,scaleY(b.l));ctx.stroke();
   const y1=scaleY(Math.max(b.o,b.c)),y2=scaleY(Math.min(b.o,b.c));
   ctx.fillRect(x-Math.max(1,dx*.26),y1,Math.max(2,dx*.52),Math.max(1,y2-y1));
  }
  ctx.font="12px sans-serif";ctx.fillStyle="#c3d5e4";
  ctx.fillText(num(max,6),10,13);ctx.fillText(num(min,6),10,height-7);
 }
 const FRAME_SECONDS={M1:60,M5:300,M15:900,H1:3600,H4:14400,D1:86400};
 function setCompareMetric(key,value,description){
   compareMetrics[key].strong.textContent=String(value);
   compareMetrics[key].small.textContent=String(description);
 }
 async function comparison(){
  const home=$("compare");
  if(selectedBroker!=="fp"||!home?.classList.contains("active")||!valid())return;
  const selected=data.symbol;
  const generation=(data.comparisonGeneration||0)+1;
  data.comparisonGeneration=generation;
  const snapshot=data.snapshot;
  const row=snapshot.symbols.find(r=>r.symbol===selected);
  if(!row){setRows(compareRows,r=>r,[["No verified FP broker symbol selected"]]);return;}
  setCompareMetric("strategy",row.proposal,"APEX M5 scanner proposal · not an order");
  setCompareMetric("body",row.m5_candle_body,"Single completed candle; price movement only");
  setCompareMetric("trend",row.timeframe_trends?.M5||"UNVERIFIED","M5 direction "+row.m5_direction);
  setCompareMetric("sync","VERIFYING","Matching FP native broker M5 to scanner timestamp");
  try{
    const docs=await Promise.all(FRAMES.map(async tf=>{
      const url=API+"fp-market-account-chart?slot="+data.accountSlot+"&symbol="+encodeURIComponent(selected)+"&timeframe="+encodeURIComponent(tf);
      const response=await fetch(url,{credentials:"same-origin",cache:"no-store"});
      if(!response.ok)throw Error(tf+" native candles HTTP "+response.status);
      const result=await response.json();
      if(result.ok!==true||result.broker!=="FP Markets"||result.environment!=="DEMO"||
         result.execution_enabled!==false||result.symbol!==selected||result.timeframe!==tf||
         !Array.isArray(result.bars)||!result.bars.length)throw Error(tf+" unverified broker candle series");
      const last=result.bars[result.bars.length-1];
      if(![last.t,last.o,last.h,last.l,last.c].every(v=>typeof v==="number"&&Number.isFinite(v)))
        throw Error(tf+" invalid OHLC proof");
      return {tf,last,count:result.bars.length};
    }));
    if(generation!==data.comparisonGeneration||data.symbol!==selected||selectedBroker!=="fp")return;
    const lastM5=docs.find(e=>e.tf==="M5").last;
    const sameBar=row.m5_bar_time===lastM5.t;
    const sameClose=Math.abs(Number(row.m5_last_close)-lastM5.c)<=
       Math.max(0.000001,Math.abs(lastM5.c)*0.00000002);
    const matched=sameBar&&sameClose;
    setCompareMetric("sync",matched?"MATCHED":"UNVERIFIED",
       matched?"M5 timestamp and close match Strategy Scanner":"FP scanner and chart not from same M5 broker snapshot");
    noticeTitle.textContent=matched?"Strategy Scanner / FP broker candle verified":
       "FP broker candle and scanner not yet synchronized";
    noticeDesc.textContent=selected+" · APEX "+row.proposal+
       " · Entry: "+(row.scanner_reason||"UNVERIFIED")+
       " · Broker execution is independently verified; candle bias is not an executed trade.";
    setRows(compareRows,entry=>{
      const bar=entry.last;
      const closeAt=bar.t+FRAME_SECONDS[entry.tf];
      const candle=bar.c>bar.o?"BUY":bar.c<bar.o?"SELL":"FLAT";
      const minutes=Math.max(0,Math.floor((Date.now()/1000-closeAt)/60));
      return [entry.tf,{text:candle,className:candle==="BUY"?"fp-pass":candle==="SELL"?"fp-veto":"fp-neutral"},
        {text:row.timeframe_trends?.[entry.tf]||"UNVERIFIED",className:"fp-neutral"},
        num(bar.o,6),num(bar.c,6),utc(new Date(closeAt*1000).toISOString()),
        Number.isFinite(minutes)?minutes+" min":"UNAVAILABLE"];
    },docs);
  }catch(e){
    if(generation!==data.comparisonGeneration)return;
    noticeTitle.textContent="FP comparison evidence unavailable";
    noticeDesc.textContent=String(e.message||"Broker data unavailable")+" · No inferred signal.";
    setCompareMetric("sync","UNVERIFIED","Could not prove matching broker and scanner candles");
    setRows(compareRows,r=>r,[["FP native completed candles unavailable; no synthetic substitutions"]]);
  }
 }
 async function chart(){
  if(!valid()||selectedBroker!=="fp"||!$("compare")?.classList.contains("active"))return;
  try{
   const u=API+"fp-market-account-chart?slot="+data.accountSlot+"&symbol="+encodeURIComponent(data.symbol)+"&timeframe="+encodeURIComponent(data.frame);
   const r=await fetch(u,{credentials:"same-origin",cache:"no-store"});
   if(!r.ok)throw Error("Native completed candles currently unavailable");
   const x=await r.json();
   if(x.ok!==true||x.execution_enabled!==false||x.broker!=="FP Markets"||!Array.isArray(x.bars))throw Error("Untrusted chart");
   plot(x.bars);chartNote.textContent=x.symbol+" / "+x.timeframe+
       " · "+x.bars.length+" completed FP broker candles · "+utc(x.generated_at_utc)+" · Research only";
  }catch(e){chartNote.textContent=e.message;const c=canvas.getContext("2d");c?.clearRect(0,0,canvas.width,canvas.height);}
 }
 async function refresh(){
  if(data.busy)return;data.busy=true;
  try{
   const list=await fetch(API+"fp-market-accounts",{credentials:"same-origin",cache:"no-store"});
   if(!list.ok)throw Error("Account feed unavailable");
   const summary=await list.json();
   chooseAccounts(summary.accounts);
   if(!data.accounts.length)throw Error("No verified FP account publication");
   const r=await fetch(API+"fp-market-account?slot="+data.accountSlot,{credentials:"same-origin",cache:"no-store"});
   data.snapshot=await r.json();
   if(!r.ok)data.snapshot={available:false,reason:"FP UI returned HTTP "+r.status};
  }catch(_){data.snapshot={available:false,reason:"FP Markets source unreachable"};}
  finally{data.busy=false;}
  render();
  if(selectedBroker==="fp"&&$("compare")?.classList.contains("active")){
    void comparison();void chart();
  }
 }
 marketSearch.addEventListener("input",()=>{if(valid())render()});
 symbolSelect.addEventListener("change",()=>{data.symbol=symbolSelect.value;void comparison();void chart()});
 frameSelect.addEventListener("change",()=>{data.frame=frameSelect.value;void chart()});
 window.addEventListener("resize",()=>{if(selectedBroker==="fp"&&$("compare")?.classList.contains("active"))void chart()});
 $("refreshNow")?.addEventListener("click",()=>void refresh());
 void refresh();
 setInterval(()=>{if(!document.hidden)void refresh()},45000);
})();
