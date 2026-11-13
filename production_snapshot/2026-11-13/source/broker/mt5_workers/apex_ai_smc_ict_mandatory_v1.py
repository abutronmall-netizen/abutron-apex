#!/usr/bin/python3
"""ABUTRON APEX positive-only AI + SMC + ICT proof for Deriv DEMO new orders.
No order submission methods; the existing APEX risk/identity/MT5 bridge must
independently authorize the candidate after this proof. Missing/stale => HOLD.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import re
import sys
import time
from pathlib import Path

sys.path[:0]=['/opt/apex-smc-shadow-v1','/opt/apex-client-mt5','/opt/apex/runtime']
import native_apex_feed as feed
import smc_shadow as smc
import apex_fast_scanner as fast

AI=Path('/var/lib/abutron-scanner-llm/latest.json')
ACCOUNT_ROOT=Path('/var/lib/private')
EXPECTED_SYMBOLS=frozenset(smc.SYMBOLS)
ID=re.compile(r'^[a-f0-9]{32}$')
ALLOWED_SUFFIXES=frozenset(('6207','7593','9244'))
MAX_AI_REPORT_AGE=420
MAX_AI_CANDLE_AGE=210
MIN_SMC_SCORE=smc.THRESHOLD

def timestamp(value):
    try:
        if not isinstance(value,str):return None
        t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        if t.tzinfo is None:return None
        return t.timestamp()
    except (ValueError,TypeError,OverflowError,AttributeError):
        return None

def result(decision,reason,*,ai='NOT_REVIEWED',smc_status='NOT_CONFIRMED',
           ict_status='NOT_CONFIRMED',score=None,entry_pattern=None):
    return {'decision':decision,'reason':reason,'ai':ai,'smc':smc_status,
            'ict':ict_status,'smc_score':score,'ict_pattern':entry_pattern,
            'can_authorize_orders':False,'research_model_can_submit_orders':False}

def verify_ai(report,symbol,bar,side,now):
    """Positive Qwen approval requires exact completed bar and causal timestamp."""
    if (not isinstance(report,dict) or report.get('schema')!='abutron.scanner.llm.v1'
        or report.get('order_execution_modified') is not False
        or report.get('status')!='MODEL_REVIEW_COMPLETED'):
        return 'HOLD_AI','AI_REPORT_INVALID'
    seen=timestamp(report.get('checked_at_utc'))
    if seen is None or not 0<=now-seen<=MAX_AI_REPORT_AGE:
        return 'HOLD_AI','AI_REPORT_STALE'
    rows=report.get('reviews')
    if not isinstance(rows,list) or len(rows)>100:
        return 'HOLD_AI','AI_REVIEW_COLLECTION_INVALID'
    matched=[r for r in rows if isinstance(r,dict) and
             (r.get('symbol'),r.get('m5_bar_time'),r.get('scanner_proposal'))==
             (symbol,bar,side)]
    if len(matched)!=1:
        return 'HOLD_AI','NO_UNIQUE_EXACT_CANDLE_AI_REVIEW'
    review=matched[0]
    stamped=timestamp(review.get('reviewed_at_utc'))
    if (stamped is None or stamped<bar+300-20 or stamped>now+2
        or now-stamped>MAX_AI_CANDLE_AGE or
        review.get('evidence_status')!='MODEL_REVIEW_COMPLETED'
        or review.get('execution_authorized_by_llm') is not False):
        return 'HOLD_AI','AI_REVIEW_NOT_PRETRADE_CURRENT'
    direction=review.get('llm_direction')
    if direction not in ('BUY','SELL','HOLD'):
        return 'HOLD_AI','AI_DIRECTION_INVALID'
    if direction!=side:
        return 'VETO_AI','QWEN_DISAGREES_OR_HOLD'
    return 'AI_CONFIRMED','QWEN_EXACT_CANDLE_AGREEMENT'

def _continuation_sweep_reclaim(features,side,bar,bars):
    """ICT continuation, fresh completed M5 sweep/reclaim, no chasing.

    SMC already establishes higher-timeframe trend and structural evidence.
    This independent entry timing requires a same-bar sweep AND displacement,
    near-level directional rejection, non-extreme M5 RSI and fresh broker M5.
    No paper/history replay or account-control modification is involved.
    """
    if (not isinstance(bars,list) or len(bars)<60 or
        not isinstance(features,dict) or side not in ('BUY','SELL')):
        return False
    sweep=features.get('liquidity_sweep') or {}
    displacement=features.get('displacement') or {}
    if not isinstance(sweep,dict) or not isinstance(displacement,dict):
        return False
    if (sweep.get('direction')!=side or sweep.get('bar_time')!=bar or
        displacement.get('direction')!=side or displacement.get('bar_time')!=bar):
        return False
    level=sweep.get('level')
    multiple=displacement.get('body_multiple')
    if (type(level) not in (float,int) or type(multiple) not in (float,int)
        or not math.isfinite(level) or not math.isfinite(multiple)
        or level<=0 or multiple<1.5):
        return False
    last=bars[-1]
    if not isinstance(last,dict) or last.get('time')!=bar:
        return False
    try:
        opening,high,low,close=(float(last[k]) for k in ('open','high','low','close'))
        if not all(math.isfinite(v) for v in (opening,high,low,close)):
            return False
        if not (0<low<=min(opening,close)<=max(opening,close)<=high):
            return False
        span=high-low
        if span<=0 or abs(close-opening)/span<.65:return False
        atr=smc.average_true_range(bars)
        if not math.isfinite(atr) or atr<=0:return False
        if side=='SELL':
            if not (high>level and close<level and close<opening and
                    close<=low+.40*span and level-close<=.65*atr):
                return False
        else:
            if not (low<level and close>level and close>opening and
                    close>=low+.60*span and close-level<=.65*atr):
                return False
        rsi=fast.frame_state(bars)['rsi14']
        return (isinstance(rsi,(int,float)) and math.isfinite(rsi) and
                (35<=rsi<=70 if side=='BUY' else 30<=rsi<=65))
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,ZeroDivisionError):
        return False

def grade(research,side,expected_bar,m5_bars=None):
    """Separate SMC market-structure proof from ICT entry timing proof.

    Both use the same broker candles (not independent data feeds).
    The existing SMC/ICT scanner is a rule-based proxy, not institutional order flow.
    """
    if not isinstance(research,dict) or side not in ('BUY','SELL'):
        return ('HOLD_SMC','MALFORMED_SMC_RESEARCH',None,None)
    if research.get('baseline_m5_time')!=expected_bar or research.get('apex_proposal')!=side:
        return ('HOLD_SMC','SMC_CANDLE_OR_SIDE_MISMATCH',None,None)
    if research.get('family')!='Volatility':
        return ('HOLD_ICT','SPIKE_FAMILY_EXECUTION_NOT_VALIDATED',None,None)
    if (research.get('status')!='RESEARCH_CONFIRMED'
        or type(research.get('score')) is not int or research['score']<MIN_SMC_SCORE):
        return ('HOLD_SMC','SMC_RESEARCH_NOT_CONFIRMED',research.get('score'),None)
    feat=research.get('features')
    flags=research.get('flags')
    if not isinstance(feat,dict) or not isinstance(flags,dict):
        return ('HOLD_SMC','SMC_FEATURE_PROOFS_MISSING',None,None)
    if flags.get('higher_timeframe') is not True:
        return ('HOLD_SMC','HIGHER_TIMEFRAME_NOT_ALIGNED',research['score'],None)
    structure=feat.get('structure') or {}
    sweep=feat.get('liquidity_sweep') or {}
    displace=feat.get('displacement') or {}
    fvg=feat.get('fvg_retest') or {}
    block=feat.get('order_block_proxy_retest') or {}
    if not all(isinstance(x,dict) for x in (structure,sweep,displace,fvg,block)):
        return ('HOLD_SMC','UNTRUSTED_SMC_ICT_FEATURE_TYPE',research['score'],None)
    has_structure=(structure.get('direction')==side and
                   structure.get('event') in ('BOS','CHoCH'))
    has_sweep=sweep.get('direction')==side
    if not (has_structure or has_sweep):
        return ('HOLD_SMC','NO_DIRECTIONAL_BOS_CHOCH_OR_LIQUIDITY_SWEEP',research['score'],None)
    # ICT: require a favorable, current retest of FVG/OB, or aligned
    # liquidity sweep plus displacement and favorable premium/discount.
    favorable=feat.get('premium_discount')=='FAVORABLE'
    displacement=displace.get('direction')==side
    fvg_hit=fvg.get('direction')==side and isinstance(fvg.get('retested_bar'),int)
    ob_hit=block.get('direction')==side and isinstance(block.get('created_bar'),int)
    pattern=None
    if favorable and fvg_hit:pattern='FVG_RETEST_FAVORABLE_ZONE'
    elif favorable and ob_hit:pattern='ORDER_BLOCK_PROXY_RETEST_FAVORABLE_ZONE'
    elif favorable and has_sweep and displacement:
        pattern='LIQUIDITY_SWEEP_DISPLACEMENT_FAVORABLE_ZONE'
    if pattern is None and not favorable and _continuation_sweep_reclaim(feat,side,expected_bar,m5_bars):
        pattern='ICT_CONTINUATION_SWEEP_DISPLACEMENT_NEAR_LEVEL'
    if pattern is None:
        return ('HOLD_ICT','NO_VALID_ICT_ENTRY_PATTERN',research['score'],None)
    return ('SMC_ICT_CONFIRMED','DIRECTION_AND_ENTRY_VALIDATED',research['score'],pattern)

def validate_source(cid,suffix,login,server):
    if (not isinstance(cid,str) or not ID.fullmatch(cid) or
        not isinstance(login,str) or not login.endswith(suffix) or
        suffix not in ALLOWED_SUFFIXES or server!='Deriv-Demo'):
        raise ValueError('ACCOUNT_BROKER_IDENTITY_INVALID')
    if not feed.private_manager.attest(cid,'Deriv',server):
        raise ValueError('ISOLATED_BROKER_CONNECTION_NOT_ATTESTED')
    home=ACCOUNT_ROOT/('abutron-client-mt5-'+cid)
    state=home/'worker-health.json'
    if state.is_symlink():raise ValueError('SYMLINKED_HEALTH_PROOF')
    doc=json.loads(state.read_text())
    nonce=doc.get('nonce')
    if doc.get('status')!='CONNECTED' or not isinstance(nonce,str) or not ID.fullmatch(nonce):
        raise ValueError('ACCOUNT_NATIVE_HEALTH_NOT_CONNECTED')
    return home/'terminal/MQL5/Files',nonce

def check(cid,suffix,login,server,symbol,bar,side,*,now=None,
          model_file=AI,source_override=None):
    """Can only veto/hold/confirm; router still owns final order authorization."""
    when=time.time() if now is None else float(now)
    if (not isinstance(symbol,str) or symbol not in EXPECTED_SYMBOLS
        or side not in ('BUY','SELL') or type(bar) is not int or
        bar<=0 or bar%300!=0 or not math.isfinite(when) or
        not 0<=when-(bar+300)<=240):
        return result('HOLD_BAD_EVIDENCE','INVALID_SYMBOL_SIDE_OR_CLOSED_M5')
    try:
        if source_override is None:
            folder,nonce=validate_source(cid,suffix,login,server)
            market=feed.bars_file(folder/('ABUTRON_NATIVE_BARS_V2_'+nonce+'.txt'),nonce)
            scanner=feed.scan(market)
            analysis=smc.assess(market,scanner,now=when,enforce_freshness=True)
        else:
            analysis=source_override
        if (analysis.get('schema')!=smc.SCHEMA
            or analysis.get('execution_authorized') is not False
            or analysis.get('orders_enabled') is not False):
            return result('HOLD_BAD_EVIDENCE','INVALID_NATIVE_SMC_ICT_RESEARCH_DOCUMENT')
        matches=[r for r in analysis.get('instruments',[]) if
             isinstance(r,dict) and r.get('symbol')==symbol]
        if len(matches)!=1:
            return result('HOLD_BAD_EVIDENCE','NATIVE_SMC_SYMBOL_PROOF_MISSING')
        entry=matches[0]
        broker_m5=(market.get('data',{}).get(symbol,{}).get('M5')
                   if source_override is None else None)
        proof,reason,score,pattern=grade(entry,side,bar,m5_bars=broker_m5)
        if proof!='SMC_ICT_CONFIRMED':
            return result(proof,reason,smc_status=entry.get('status','NOT_CONFIRMED'),
                          ict_status='NOT_CONFIRMED',score=score)
        if model_file.is_symlink() or not model_file.is_file() or model_file.stat().st_size>200000:
            return result('HOLD_AI','AI_REPORT_MISSING',smc_status='CONFIRMED',
                          ict_status='CONFIRMED',score=score,entry_pattern=pattern)
        report=json.loads(model_file.read_text(encoding='utf8'))
        status,reason=verify_ai(report,symbol,bar,side,when)
        if status!='AI_CONFIRMED':
            return result(status,reason,ai=status,smc_status='CONFIRMED',
                          ict_status='CONFIRMED',score=score,entry_pattern=pattern)
        return result('CONFIRMED_ALL','AI_SMC_ICT_POSITIVE_CONFIRMATIONS_CURRENT',
                      ai='CONFIRMED',smc_status='CONFIRMED',ict_status='CONFIRMED',
                      score=score,entry_pattern=pattern)
    except (OSError,ValueError,KeyError,TypeError,IndexError,OverflowError,UnicodeError,
            json.JSONDecodeError) as exc:
        return result('HOLD_BAD_EVIDENCE','MISSING_OR_INVALID_BROKER_PROOF_'+type(exc).__name__)
