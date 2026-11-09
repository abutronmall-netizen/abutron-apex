#!/usr/bin/env python3
"""APEX broker-only adapter for original TauricResearch TradingAgents v0.7.1.

This program NEVER imports MetaTrader5 and has NO order placing, amending,
closing, authentication or execution functionality. It runs the upstream
TradingAgentsGraph with its market tool set substituted to read verified
completed Deriv DEMO candles. Intended as the automatic research/decision stage
before an independently approved deterministic trade executor.

Copyright (c) APEX integration authors; uses upstream TradingAgents separately.
"""
from __future__ import annotations
from typing import Annotated

import argparse
import copy
import dataclasses
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

SNAPSHOT = Path('/var/lib/apex/mt5-market/deriv_demo_bars.json')
RISK = Path('/var/lib/apex/mt5-market/contract_risk_latest.json')
OUT = Path('/var/lib/apex/agentic')
TIMEFRAMES = ('M1', 'M5', 'M15', 'H1', 'H4', 'D1')
SYMBOLS = (
    'Volatility 10 Index.0', 'Volatility 25 Index.0',
    'Volatility 50 Index.0', 'Volatility 75 Index.0',
    'Volatility 100 Index.0', 'Crash 150 Index.0',
    'Crash 300 Index.0', 'Crash 600 Index.0',
    'Crash 1000 Index.0', 'Boom 150 Index.0',
    'Boom 300 Index.0', 'Boom 600 Index.0',
    'Boom 1000 Index.0',
)
MODEL = 'qwen2.5:1.5b-instruct'


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(text: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError('Missing UTC timezone')
    return parsed.astimezone(dt.timezone.utc)


def read_snapshot(path: Path = SNAPSHOT, now: dt.datetime | None = None) -> dict:
    """Fail closed on stale/malformed/untrusted broker data."""
    now = now or _utcnow()
    blob = path.read_bytes()
    if len(blob) > 7_000_000 or len(blob) < 100:
        raise ValueError('Broker snapshot size invalid')
    data = json.loads(blob)
    if (data.get('schema') != 'apex.mt5.market.v1'
            or data.get('source') != 'Deriv DEMO MT5'
            or data.get('execution_enabled') is not False):
        raise ValueError('Untrusted broker snapshot')
    when = _timestamp(data['generated_at_utc'])
    delay = (now - when).total_seconds()
    if delay < -120 or delay > 900:
        raise ValueError('Broker snapshot is stale or from future')
    instruments = data.get('data')
    if not isinstance(instruments, dict) or set(instruments) != set(SYMBOLS):
        raise ValueError('Missing/unknown Deriv instruments')
    for symbol, frames in instruments.items():
        if set(frames) != set(TIMEFRAMES):
            raise ValueError('Incomplete timeframes: '+symbol)
        for frame, bars in frames.items():
            if not isinstance(bars, list) or len(bars) < 60:
                raise ValueError('Insufficient broker candles')
            prev = -1
            for bar in bars:
                stamp = bar.get('time')
                if type(stamp) is not int or stamp <= prev or stamp > now.timestamp():
                    raise ValueError('Invalid/unsorted candle timestamp')
                prev = stamp
                vals = [bar.get(k) for k in ('open','high','low','close')]
                if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in vals):
                    raise ValueError('Invalid candle quote')
                if not (bar['high'] >= max(bar['open'],bar['close']) and
                        bar['low'] <= min(bar['open'],bar['close'])):
                    raise ValueError('Invalid candle OHLC shape')
            if frame == 'M5' and now.timestamp() - prev > 1200:
                raise ValueError('Stale five-minute broker candles for '+symbol)
    return data


def read_risk(path: Path = RISK, now: dt.datetime | None = None) -> dict:
    """Advisory estimates ONLY, never order authorization."""
    now = now or _utcnow()
    data = json.loads(path.read_text())
    if (data.get('status') != 'inspection_only'
            or data.get('orders_placed') != 0
            or data.get('calculated_count') != 13
            or data.get('source') != 'Deriv USD DEMO MT5'):
        raise ValueError('Risk estimate provenance invalid')
    age = (now - _timestamp(data['checked_at_utc'])).total_seconds()
    if age < -120 or age > 7200:
        raise ValueError('Risk estimate stale')
    instruments = data.get('instruments')
    if not isinstance(instruments, list) or {i.get('symbol') for i in instruments} != set(SYMBOLS):
        raise ValueError('Incomplete broker contract risk check')
    return {x['symbol']:x for x in instruments}


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError('Not enough bars for EMA')
    factor = 2/(period+1)
    mean = sum(values[:period])/period
    for value in values[period:]:
        mean = factor * value + (1-factor)*mean
    return mean


def atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) <= period:
        raise ValueError('Insufficient candles for ATR')
    tr = []
    for i in range(1,len(bars)):
        row, prev = bars[i], bars[i-1]['close']
        tr.append(max(row['high'] - row['low'], abs(row['high'] - prev), abs(row['low'] - prev)))
    return sum(tr[-period:])/period


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError('Insufficient candles for RSI')
    diffs = [values[i] - values[i-1] for i in range(1,len(values))]
    ups = sum(max(0,x) for x in diffs[:period])/period
    downs = sum(max(0,-x) for x in diffs[:period])/period
    for change in diffs[period:]:
        ups = ((period-1)*ups + max(0,change))/period
        downs = ((period-1)*downs + max(0,-change))/period
    return 100.0 if downs == 0 else 100-(100/(1+ups/downs))


def frame_summary(rows: list[dict]) -> dict:
    closes = [float(x['close']) for x in rows]
    e9, e21 = ema(closes,9), ema(closes,21)
    return {'close':round(closes[-1],8), 'ema9':round(e9,8),
            'ema21':round(e21,8), 'atr14':round(atr(rows),8),
            'rsi14':round(rsi(closes),3),
            'trend': 'UP' if e9>e21 else 'DOWN' if e9<e21 else 'FLAT',
            'last_candle_utc':dt.datetime.fromtimestamp(rows[-1]['time'],dt.timezone.utc).isoformat()}


def source_report(snapshot: dict, symbol: str, risk: dict | None = None) -> str:
    """A deterministic report made only from completed broker candles."""
    if symbol not in SYMBOLS:
        raise ValueError('Symbol not allowlisted')
    out = [f'DERIV DEMO MT5 VERIFIED CLOSED-CANDLE SNAPSHOT: {symbol}',
           f'Generated UTC: {snapshot["generated_at_utc"]}',
           'Asset: broker synthetic index (NOT a company or equity).',
           'No stocks, dividends, company fundamentals or external news sources apply.',
           'MT5 tick volume is NOT exchange-cleared contract volume.',
           'Avoid claims about edge, profitability, execution or fills.']
    for frame in ('M1','M5','M15','H1','H4','D1'):
        out.append(f'{frame}: '+json.dumps(frame_summary(snapshot['data'][symbol][frame]),sort_keys=True))
    recent = snapshot['data'][symbol]['H1'][-12:]
    out.append('Most recent 12 completed H1 OHLCV candles:')
    out += [json.dumps(x,sort_keys=True) for x in recent]
    if risk:
        r = risk.get(symbol)
        if r:
            out += [f'MT5 contract check: min_lot={r.get("minimum_lot")}, '
                    f'estimated BUY stop loss USD={r.get("buy_sl_est_usd")}, '
                    f'estimated SELL stop loss USD={r.get("sell_sl_est_usd")}; '
                    'No preselected dollar-loss threshold is asserted. '
                    'These are simulated order_calc_profit estimates, not execution guarantees.']
    return '\n'.join(out)


def prepare_original_tradingagents_tools(snapshot:dict,risk:dict):
    """Inject narrow broker data tools into upstream TradingAgents; do not alter repo files."""
    from typing import Annotated
    from langchain_core.tools import tool
    global InjectedState
    from langgraph.prebuilt import InjectedState
    from tradingagents.agents.analysts import market_analyst
    from tradingagents.graph import analyst_execution

    @tool
    def get_stock_data(
        symbol: Annotated[str,InjectedState('company_of_interest')],
        start_date: Annotated[str,'Start date YYYY-MM-DD'],
        end_date: Annotated[str,'End date YYYY-MM-DD'],
        trade_date: Annotated[str,InjectedState('trade_date')] = '',
    ) -> str:
        """Verified completed Deriv MT5 OHLCV candles; broker-only source."""
        if symbol not in SYMBOLS:
            return 'REJECTED: unapproved instrument'
        return source_report(snapshot,symbol,risk)

    @tool
    def get_indicators(
        symbol: Annotated[str,InjectedState('company_of_interest')],
        indicator: Annotated[str,'Indicator name e.g. atr/rsi/close_10_ema'],
        curr_date: Annotated[str,'Current date YYYY-MM-DD'],
        look_back_days: Annotated[int,'Lookback period']=30,
        trade_date: Annotated[str,InjectedState('trade_date')]='',
    ) -> str:
        """Verified MT5 technical indicator values across H1 and H4 timeframes."""
        if symbol not in SYMBOLS:
            return 'REJECTED: unapproved instrument'
        allowed={'atr','rsi','close_10_ema','close_50_sma','close_200_sma',
                 'macd','macds','macdh','boll','boll_ub','boll_lb'}
        names=[x.strip().lower() for x in indicator.split(',') if x.strip()]
        invalid=[x for x in names if x not in allowed]
        if invalid:
            return 'UNAVAILABLE: '+','.join(invalid)+'. No unverified indicators will be fabricated.'
        lines=[]
        for timeframe in ('H1','H4'):
            bars=snapshot['data'][symbol][timeframe]
            closes=[float(c['close']) for c in bars]
            s=frame_summary(bars)
            mid=sum(closes[-20:])/20
            std=(sum((v-mid)**2 for v in closes[-20:])/20)**0.5
            def emalist(series, n):
                k=2/(n+1)
                e=series[0]
                values=[]
                for v in series:
                    e=k*v+(1-k)*e
                    values.append(e)
                return values
            e12,e26=emalist(closes,12),emalist(closes,26)
            md=[a-b for a,b in zip(e12,e26)]
            ms=emalist(md,9)[-1]
            values={'atr':s['atr14'],'rsi':s['rsi14'],
                    'close_10_ema':ema(closes,10),
                    'close_50_sma':sum(closes[-50:])/50,
                    'close_200_sma':sum(closes[-200:])/200,
                    'macd':md[-1], 'macds':ms,'macdh':md[-1]-ms,
                    'boll':mid,'boll_ub':mid+2*std,'boll_lb':mid-2*std}
            for n in names:
                lines.append(f'{symbol} {timeframe} {n}: {values[n]:.8f} '
                             f'(computed from closed Deriv DEMO bars, as of {s["last_candle_utc"]})')
        return '\n'.join(lines)

    @tool
    def get_verified_market_snapshot(
        symbol: Annotated[str,InjectedState('company_of_interest')],
        curr_date: Annotated[str,'Current date YYYY-MM-DD'],
        look_back_days: Annotated[int,'Recent candles to display']=30,
        trade_date: Annotated[str,InjectedState('trade_date')]='',
    ) -> str:
        """Fail-closed deterministic Deriv broker-only verified OHLCV and indicators."""
        if symbol not in SYMBOLS:
            return 'REJECTED: unapproved instrument'
        return source_report(snapshot,symbol,risk)

    tools=(get_stock_data,get_indicators,get_verified_market_snapshot)
    market_analyst.TOOLS=tools
    spec=analyst_execution.ANALYST_NODE_SPECS['market']
    analyst_execution.ANALYST_NODE_SPECS['market']=dataclasses.replace(spec,tools=tools)


def verify_broker_only_reasoning(note: str) -> tuple[bool,str]:
    """Reject synthetic-index reports based on fabricated equity fundamentals."""
    if not isinstance(note,str) or not note.strip():
        return False, "Empty agent rationale"
    lower=note.lower()
    forbidden=(
        "revenue", "earnings", "dividend", "company", "shareholder",
        "balance sheet", "financial projection", "growth potential",
        "market expansion", "stock price", "equity valuation", "cash flow",
        "annual report", "corporate", "profitability",
    )
    if any(term in lower for term in forbidden):
        return False, "Equity or corporate fundamentals in synthetic-index analysis"
    if not any(term in lower for term in ("deriv", "synthetic", "volatility", "crash", "boom")):
        return False, "Missing verified synthetic-index identity"
    if not any(term in lower for term in ("m1", "m5", "m15", "h1", "h4", "d1", "ema", "rsi", "atr", "candle", "price")):
        return False, "Missing actual candle or indicator evidence"
    return True, ""


def run_original_agent_graph(snapshot:dict, risk:dict, symbol:str) -> tuple[str, str]:
    """Run original TradingAgents LangGraph bull/bear/trader/risk/portfolio process."""
    prepare_original_tradingagents_tools(snapshot,risk)
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    import tradingagents.graph.trading_graph as upstream_module
    from langchain_ollama import ChatOllama
    from types import SimpleNamespace

    # Use the original TradingAgents LangGraph, but connect its LLM factory
    # to Ollama's native API. The OpenAI-compatible adapter on this server
    # silently ignored maximum-generation tokens, causing 15-minute stalls.
    saved_factory = upstream_module.create_tier_client

    def native_local_factory(config, tier, **kwargs):
        local_model = ChatOllama(
            model=MODEL,
            base_url='http://127.0.0.1:11434',
            num_predict=180,
            num_ctx=4096,
            temperature=0.1,
            keep_alive='45s',
            callbacks=kwargs.get('callbacks'),
        )
        return SimpleNamespace(get_llm=lambda: local_model)

    class BrokerOnlyGraph(TradingAgentsGraph):
        def resolve_instrument_context(self,ticker,asset_type='stock',trade_date=None):
            return (f'{ticker} is a DERIV synthetic index on DEMO MT5, NOT a company, stock or cryptocurrency. '
                    'Use ONLY our substituted verified Deriv broker market tools and never infer equity '
                    'fundamentals, dividends, social sentiment or external price data. HOLD/REVIEW when data unavailable.')

        def _memory_step(self,state):
            # The upstream memory settlement uses Yahoo to mark decisions; disable
            # it for these Deriv-only instruments until native settlement exists.
            return {'past_context':'No independently settled broker decisions are available.',
                    'memory_note':'Broker-native settlement pending; past returns not certified.'}

        def record_decision(self,company_name,trade_date,final_state):
            # Our JSONL log is used below, avoiding Yahoo-backed settlement.
            return None

    cfg=copy.deepcopy(DEFAULT_CONFIG)
    cfg.update({'llm_provider':'ollama','backend_url':'http://127.0.0.1:11434/v1',
                'quick_think_llm':MODEL,'deep_think_llm':MODEL,
                'quick_think_provider':None,'deep_think_provider':None,
                'quick_think_backend_url':None,'deep_think_backend_url':None,
                'max_debate_rounds':0,'max_risk_discuss_rounds':0,
                 'max_tool_rounds':2,'max_recur_limit':70,
                 'max_tokens':240,'temperature':0.1,'llm_max_retries':0,
                'checkpoint_enabled':False,
                'results_dir':str(OUT/'upstream_reports'),
                'data_cache_dir':str(OUT/'upstream_cache'),
                'memory_log_path':str(OUT/'broker_memory.md')})
    upstream_module.create_tier_client = native_local_factory
    try:
        graph=BrokerOnlyGraph(selected_analysts=('market',),config=cfg)
    finally:
        upstream_module.create_tier_client = saved_factory
    final, rating = graph.propagate(symbol,_utcnow().date().isoformat(),asset_type='stock')
    note=final.get('final_trade_decision','')
    if not isinstance(note,str) or not note.strip():
        return 'REVIEW','No final portfolio decision returned.'
    if rating not in ('Buy','Overweight','Hold','Underweight','Sell'):
        return 'REVIEW',note[:3500]
    grounded, reason = verify_broker_only_reasoning(note)
    if not grounded:
        return 'REVIEW', 'REJECTED by APEX broker-only evidence gate: ' + reason
    return rating, note[:3500]


def one_cycle(symbol:str | None = None, snapshot_path:Path = SNAPSHOT,
              risk_path:Path = RISK, out_dir:Path=OUT, model:bool=True) -> dict:
    now=_utcnow()
    snap=read_snapshot(snapshot_path,now)
    # Risk is advisory only; if unavailable run research but block any trade-ready flag.
    try:
        risk=read_risk(risk_path,now)
        risk_state='ok'
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
        risk={}
        risk_state='not-certified'
    out_dir.mkdir(parents=True,exist_ok=True)
    position_file=out_dir/'rotation.json'
    if symbol is None:
        try:
            old=json.loads(position_file.read_text())
            index=int(old.get('next_index',0))%len(SYMBOLS)
        except (OSError,ValueError,TypeError,json.JSONDecodeError):
            index=0
        symbol=SYMBOLS[index]
        tmp=out_dir/'.rotation.tmp'
        tmp.write_text(json.dumps({'next_index':(index+1)%len(SYMBOLS)}))
        tmp.replace(position_file)
    if symbol not in SYMBOLS:
        raise ValueError('Symbol not allowlisted')
    technical={k:frame_summary(snap['data'][symbol][k]) for k in ('M1','M5','M15','H1','H4','D1')}
    # M5 is primary research, with higher TF alignment kept as a separate
    # context check. The LLM is never an execution authorization mechanism.
    m5=technical['M5']
    deterministic=('BUY' if m5['trend']=='UP' and m5['rsi14']>=50 else
                   'SELL' if m5['trend']=='DOWN' and m5['rsi14']<=50 else 'HOLD')
    candidates=[technical[k]['trend'] for k in ('M15','H1','H4')]
    higher_tf=('BUY' if candidates==['UP']*3 else
               'SELL' if candidates==['DOWN']*3 else 'MIXED')
    rating,narrative=('REVIEW','Model disabled for preflight.')
    if model:
        rating,narrative=run_original_agent_graph(snap,risk,symbol)
    ai_signal= 'BUY' if rating=='Buy' else 'SELL' if rating=='Sell' else 'HOLD'
    if deterministic=='HOLD':
        final='HOLD'
        reason='No confirmed M5 EMA and RSI research direction'
    elif higher_tf!=deterministic:
        final='HOLD'
        reason=f'M5 {deterministic} not aligned with M15/H1/H4 context ({higher_tf})'
    elif ai_signal!=deterministic:
        final='HOLD'
        reason=f'M5 {deterministic} not confirmed by original AI rating {rating}'
    else:
        final=ai_signal
        reason='M5/Higher timeframe/agent research agree; NO broker orders authorized'
    r=risk.get(symbol,{})
    risk_estimate_valid=(r.get('verified') is True and risk_state=='ok')
    result={'schema':'apex.agent.shadow.v1','timestamp_utc':now.isoformat(),
            'market_data_timestamp_utc':snap['generated_at_utc'],
            'symbol':symbol,'data_source':'Deriv DEMO MT5 closed candles',
            'framework':'TauricResearch/TradingAgents v0.7.1 (original) + Ollama',
            'model':MODEL if model else 'preflight-only','rating':rating,
            'technical_direction':deterministic,'m5_direction':deterministic,
            'higher_timeframe_direction':higher_tf,'shadow_direction':final,
            'risk_probe_current':risk_state=='ok','broker_loss_estimate_valid':risk_estimate_valid,
            'automated_broker_orders_enabled':False, 'live_trading_enabled':False,
            'execution_authorized':False,'reason':reason,
            'timeframe_indicators':technical,'agent_summary':narrative[:3500]}
    with (out_dir/'signals.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(result,allow_nan=False)+'\n')
        f.flush();os.fsync(f.fileno())
    tmp=out_dir/'.latest.tmp'
    tmp.write_text(json.dumps(result,indent=2,allow_nan=False))
    tmp.replace(out_dir/'latest.json')
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description='APEX original TradingAgents Deriv shadow loop')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--symbol',choices=SYMBOLS)
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'cycle.lock').open('w') as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('APEX: existing agent cycle still running, skipping overlap')
            return 0
        try:
            if args.preflight:
                x=read_snapshot()
                print(json.dumps({'ok':True,'symbols':len(x['data']),
                                  'timeframes':sum(map(len,x['data'].values())),
                                  'source':x['source'],'orders_enabled':False}))
                return 0
            result=one_cycle(symbol=args.symbol,model=True)
            print(json.dumps({k:result[k] for k in ('timestamp_utc','symbol','rating','technical_direction','shadow_direction','execution_authorized')},sort_keys=True))
            return 0
        except Exception as exc:
            err={'timestamp_utc':_utcnow().isoformat(),'status':'ERROR',
                 'error_type':type(exc).__name__,'error':str(exc)[:300],
                 'broker_orders_enabled':False}
            with (OUT/'errors.jsonl').open('a') as f:
                f.write(json.dumps(err)+'\n')
            print(json.dumps(err),file=sys.stderr)
            return 1


if __name__=='__main__':
    raise SystemExit(main())
