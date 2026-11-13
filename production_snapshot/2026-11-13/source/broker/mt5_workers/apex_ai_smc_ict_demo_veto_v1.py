#!/usr/bin/env python3
"""Deterministic veto-only evidence check for APEX Deriv DEMO new entries.

Cannot authorize or dispatch orders. An exact, current SMC rejection or
independent Qwen disagreement vetoes only the proposed candidate.
Absent/review-late evidence is neutral; corrupt trusted evidence is blocked.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path

POLICY=Path('/etc/apex/ai-smc-ict-demo-veto.json')
OBS=Path('/var/lib/apex-smc-shadow/observations.sqlite3')
AI=Path('/var/lib/abutron-scanner-llm/latest.json')
VALID_SYMBOLS=frozenset(['Volatility '+x+' Index.0' for x in ('10','25','50','75','100')] +
 [x+' '+n+' Index.0' for x in ('Crash','Boom') for n in ('150','300','600','1000')])
HEX32=re.compile(r'^[0-9a-f]{32}$')
SUFFIXES=frozenset(('9244','6207','7593'))

def iso(s):
    try:
        when=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
        return when.timestamp() if when.tzinfo is not None else None
    except (AttributeError,TypeError,ValueError,OverflowError):
        return None

def read_json(p,limit):
    if p.is_symlink():
        raise ValueError('SYMLINKED_TRUSTED_SOURCE')
    if not p.is_file() or not (2 <= p.stat().st_size <= limit):
        raise ValueError('MISSING_OR_INVALID_TRUSTED_SOURCE')
    val=json.loads(p.read_text(encoding='utf8'))
    if not isinstance(val,dict):
        raise ValueError('INVALID_JSON_OBJECT')
    return val

def policy(path=POLICY):
    if path.is_symlink():
        raise ValueError('SYMLINKED_DEMO_VETO_POLICY')
    if not path.exists():
        return {'enabled':False,'mode':'veto_only','environment':'DERIV_DEMO'}
    st=path.stat()
    if st.st_uid!=0 or st.st_mode & 0o022:
        raise ValueError('UNTRUSTED_DEMO_VETO_POLICY_PERMISSIONS')
    val=read_json(path,4096)
    if (val.get('schema')!='abutron.apex.ai_smc_ict.demo_veto_policy.v1'
        or type(val.get('enabled')) is not bool
        or val.get('mode') not in ('veto_only','mandatory_confirm')
        or val.get('environment')!='DERIV_DEMO'
        or val.get('allowed_account_suffixes')!=['6207','7593','9244']):
        raise ValueError('INVALID_AI_SMC_DEMO_POLICY')
    return val

def check(account_id,suffix,symbol,bar,side,*,when=None,
          observations=OBS,ai_file=AI,enabled=True):
    """Return a non-authoritative veto decision. No writes, no broker calls."""
    now=time.time() if when is None else float(when)
    result={'decision':'PASS_NEUTRAL','reason':'NO_NEGATIVE_EVIDENCE',
       'smc':'NOT_OBSERVED','ai':'NOT_REVIEWED',
       'research_only':False,'can_authorize_orders':False}
    if not enabled:
        result.update(decision='DISABLED',reason='VETO_SWITCH_OFF')
        return result
    if (not isinstance(account_id,str) or HEX32.fullmatch(account_id) is None
        or suffix not in SUFFIXES or symbol not in VALID_SYMBOLS or side not in ('BUY','SELL')
        or type(bar) is not int or bar<1 or bar%300
        or not math.isfinite(now) or now<bar+300-20 or now>bar+540):
        result.update(decision='HOLD_BAD_EVIDENCE',reason='SIGNAL_IDENTITY_OR_CANDLE_WINDOW_INVALID')
        return result
    # Bind the research evidence to one isolated account, symbol, candle and direction.
    h=hashlib.sha256(account_id.encode('ascii')).hexdigest()[:24]
    try:
        if observations.is_symlink() or not observations.is_file():
            raise ValueError('SMC_DB_MISSING')
        with sqlite3.connect('file:'+str(observations)+'?mode=ro',uri=True,timeout=5) as c:
            c.execute('PRAGMA query_only=ON')
            rows=c.execute("""SELECT baseline,smc_status,score,observed_at_utc
              FROM observations WHERE account_hash=? AND symbol=? AND m5_close=?""",
              (h,symbol,bar)).fetchall()
        if len(rows)>1:
            raise ValueError('DUPLICATE_SMC_CANDLE_PROOF')
        if rows:
            baseline,status,score,stamp=rows[0]
            t=iso(stamp)
            if baseline!=side:
                result.update(smc='BASELINE_DIRECTION_MISMATCH')
            elif (t is not None and bar+300-20<=t<=now+2 and now-t<=210
                  and type(score) is int and 0<=score<=100):
                result['smc']=status
                if status=='RESEARCH_REJECTED':
                    result.update(decision='VETO_SMC',reason='CURRENT_ACCOUNT_SMC_ICT_REJECTED')
                    return result
                if status not in ('RESEARCH_CONFIRMED','NO_BASE_SIGNAL','SPIKE_FAMILY_RESEARCH_ONLY'):
                    raise ValueError('UNKNOWN_SMC_STATUS')
            else:
                result['smc']='STALE_OR_INVALID_SMC_EVIDENCE'
    except (sqlite3.Error,ValueError,OSError,UnicodeError) as exc:
        result.update(decision='HOLD_BAD_EVIDENCE',reason='SMC_EVIDENCE_UNAVAILABLE_'+type(exc).__name__)
        return result
    # Model may be unavailable on a candle; this is veto-only, not a mandatory
    # confirmation or a new order-authorization gate.
    try:
        model=read_json(ai_file,200000)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError):
        result['ai']='AI_REVIEW_NOT_AVAILABLE'
        return result
    t=iso(model.get('checked_at_utc'))
    if (model.get('schema')!='abutron.scanner.llm.v1'
        or model.get('status')!='MODEL_REVIEW_COMPLETED'
        or model.get('order_execution_modified') is not False
        or t is None or t>now+2 or now-t>420):
        result['ai']='AI_REVIEW_NOT_CURRENT'
        return result
    reviews=model.get('reviews')
    if not isinstance(reviews,list) or len(reviews)>100:
        result['ai']='AI_REVIEW_LIST_INVALID'
        return result
    matches=[r for r in reviews if isinstance(r,dict) and
      (r.get('symbol'),r.get('m5_bar_time'),r.get('scanner_proposal'))==(symbol,bar,side)]
    if len(matches)>1:
        result.update(decision='HOLD_BAD_EVIDENCE',reason='AMBIGUOUS_AI_CANDLE_REVIEW')
        return result
    if not matches:
        return result
    r=matches[0]
    t=iso(r.get('reviewed_at_utc'))
    if (r.get('evidence_status')!='MODEL_REVIEW_COMPLETED'
        or r.get('execution_authorized_by_llm') is not False
        or t is None or t<bar+300-20 or t>now+2 or now-t>210
        or r.get('llm_direction') not in ('BUY','SELL','HOLD')):
        result['ai']='AI_REVIEW_NOT_CAUSALLY_CURRENT'
        return result
    result['ai']=r['llm_direction']
    if r['llm_direction']!=side:
        result.update(decision='VETO_AI',reason='CURRENT_QWEN_DIRECTION_DISAGREES')
    else:
        result['reason']='NO_NEGATIVE_EVIDENCE_QWEN_AGREED'
    return result
