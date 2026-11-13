#!/usr/bin/python3
"""Selective, broker-only TradingAgents Qwen reviewer. No trading/order IO.

TradingAgentsGraph is used as an isolated single market-analyst LLM client;
the stock/news/full debate graph is deliberately NOT invoked because it
would request non-broker data. APEX remains the sole signal detector.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,math,re,time,sys
from pathlib import Path

TA_HOME=Path('/opt/apex/apps/tradingagents')
if str(TA_HOME) not in sys.path:sys.path.insert(0,str(TA_HOME))

MODEL='qwen2.5:1.5b-instruct'
FRAMES=('M1','M5','M15','H1','H4','D1')
_FIELDS=('trend','rsi14','ema9','ema21','atr14')
_CONFIG=None
_CLIENT=None

def stamp(raw):
    d=dt.datetime.fromisoformat(str(raw).replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('NAIVE_TIMESTAMP')
    return d.timestamp()

def validate_evidence(broker,symbol,bar,proposal,indicators):
    if broker not in ('Deriv DEMO MT5','FP Markets DEMO MT5'):
        raise ValueError('INVALID_BROKER_SCOPE')
    if not isinstance(symbol,str) or not 1<=len(symbol)<=80:
        raise ValueError('INVALID_BROKER_SYMBOL')
    if proposal not in ('BUY','SELL') or type(bar) is not int or bar%300:
        raise ValueError('INVALID_OR_NON_CLOSED_BAR')
    now=time.time()
    if not 0<=now-(bar+300)<=240:raise ValueError('STALE_OR_INCOMPLETE_M5_CANDLE')
    # Separate Deriv worker M1 streams have independent snapshot boundaries.
    # Use the synchronized closed M5/H1/D1 trajectory for broker-proof binding;
    # FP Markets uses all six timeframes from its one isolated account.
    evidence_frames=FRAMES if broker=='FP Markets DEMO MT5' else FRAMES[1:]
    if not isinstance(indicators,dict) or not all(tf in indicators for tf in evidence_frames):
        raise ValueError('INCOMPLETE_BROKER_INDICATORS')
    evidence={}
    for tf in evidence_frames:
        frame=indicators[tf]
        if not isinstance(frame,dict) or not all(k in frame for k in _FIELDS):
            raise ValueError('INDICATORS_MISSING')
        if frame['trend'] not in ('UP','DOWN','MIXED'):
            raise ValueError('UNTRUSTED_TREND')
        if any(type(frame[k]) not in (int,float) or not math.isfinite(frame[k])
               for k in _FIELDS if k!='trend'):
            raise ValueError('NONFINITE_INDICATORS')
        evidence[tf]={k:frame[k] for k in _FIELDS}
    payload={'broker':broker,'symbol':symbol,'m5_closed_bar':bar,
             'scanner_proposal':proposal,'indicators':evidence}
    return payload,hashlib.sha256(json.dumps(payload,separators=(',',':'),sort_keys=True).encode()).hexdigest()

def get_client():
    global _CLIENT
    if _CLIENT is None:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        cfg=dict(DEFAULT_CONFIG)
        cfg.update(llm_provider='ollama',quick_think_llm=MODEL,deep_think_llm=MODEL,
                   backend_url='http://127.0.0.1:11434/v1',temperature=0,
                   max_tokens=12,llm_max_retries=0,max_tool_rounds=2,max_recur_limit=30,
                   results_dir='/tmp/abutron-ta-broker-only/reports',
                   data_cache_dir='/tmp/abutron-ta-broker-only/cache',
                   memory_log_path='/tmp/abutron-ta-broker-only/memory.md',
                   checkpoint_enabled=False)
        # Construct official TradingAgents agent model but never call
        # propagate(), which fetches external financial/news sources.
        graph=TradingAgentsGraph(selected_analysts=('market',),config=cfg)
        _CLIENT=graph.quick_thinking_llm
    return _CLIENT

def review(broker,symbol,bar,proposal,indicators,client=None):
    payload,digest=validate_evidence(broker,symbol,bar,proposal,indicators)
    start=time.monotonic()
    llm=client if client is not None else get_client()
    from langchain_core.messages import SystemMessage,HumanMessage
    answer=llm.invoke([
      SystemMessage(content='ABUTRON APEX TradingAgents market analyst. '
         'ONLY the authenticated broker M1/M5/M15/H1/H4/D1 indicators supplied. '
         'No news, external prices, 200-period MA, institutions or fabricated indicators. '
         'Judge the APEX proposal, but never submit any trade. '
         'Respond EXACTLY one uppercase word: BUY, SELL, or HOLD. '
         'When indicators conflict or evidence is weak, reply HOLD.'),
      HumanMessage(content=json.dumps(payload,separators=(',',':'),sort_keys=True))])
    elapsed=time.monotonic()-start
    response=str(answer.content).strip().replace('\n',' ')[:220]
    m=re.fullmatch(r'(BUY|SELL|HOLD)',response.upper())
    direction=m.group(1) if m else 'HOLD'
    # The AI never has authority to reverse the original APEX scanner signal.
    approval=direction==proposal and m is not None and elapsed<=90
    return {'schema':'abutron.apex.tradingagents.selective.v1',
            'broker':broker,'symbol':symbol,'m5_closed_bar':bar,'scanner_proposal':proposal,
            'evidence_sha256':digest,'model':MODEL,
            'direction':direction if approval else 'HOLD',
            'raw_model_direction':direction,'approved':approval,
            'reviewed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'latency_seconds':round(elapsed,3),
            'analysis':response,'no_broker_order_execution':True,
            'execution_authorized':False}
