#!/usr/bin/env python3
"""APEX 1.1 Deriv DEMO 7593 broker-order draft from authentic M5 decisions.
No OrderCheck claim, CRM activation, request transport, OrderSend, or trading switches.
The native EA must reprice/recalculate/check this exact order at consumption.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR
from datetime import datetime, timezone

PKG='/opt/abutron-apex11-staging/native-v4-guarded-20261108'
if PKG not in sys.path: sys.path.insert(0,PKG)
from abutron_replacement.production_contracts import read_deriv_native_m5, DERIV_ALLOWED

CID='9568525eee306da891258ad98c654919'
LOGIN='6357593'
WORKER=Path('/var/lib/private/abutron-client-mt5-'+CID)
OUT=Path('/var/lib/abutron-apex11-7593')
COST=Path('/var/lib/abutron-deriv-v4-7593/v4-native-execution-cost-7593.json')
MAGIC=73113011

class ProposalDenied(ValueError):pass

def dec(value):
    if isinstance(value,bool): raise ProposalDenied('NON_NUMERIC_PRICE_OR_SIZE')
    try:v=D(str(value))
    except Exception: raise ProposalDenied('NON_NUMERIC_PRICE_OR_SIZE') from None
    if not v.is_finite() or v<=0:raise ProposalDenied('NON_POSITIVE_PRICE_OR_SIZE')
    return v

def align(v,step,mode):
    return (v/step).to_integral_value(rounding=mode)*step

def construct(signal,spec,bars,eq,owner,now):
    if (signal.get('engine')!='APEX_1_1_0' or signal.get('broker')!='deriv' or
        signal.get('timeframe')!='M5' or signal.get('order') is not None or
        signal.get('connection_id')!=CID or signal.get('customer_id')!=owner):
        raise ProposalDenied('NOT_ORIGINAL_APEX11_ACCOUNT_BOUND_SHADOW')
    sym,side=signal.get('symbol'),signal.get('status')
    if sym not in DERIV_ALLOWED or side not in ('BUY','SELL'):
        raise ProposalDenied('NOT_APPROVED_DIRECTIONAL_APEX_SIGNAL')
    ts=signal.get('bar_closed_ts')
    if (type(ts) not in (float,int) or int(ts)!=ts or int(ts)%300 or
        not -2<=now-int(ts)<=300):
        raise ProposalDenied('CLOSED_M5_SIGNAL_EXPIRED')
    if len(bars)<20 or int(bars[-1]['ts'])!=int(ts):
        raise ProposalDenied('UNMATCHED_NATIVE_CLOSED_BAR')
    if not all(b.get('is_closed') is True and b.get('symbol')==sym for b in bars):
        raise ProposalDenied('INVALID_NATIVE_CANDLE_IDENTITY')
    equity=dec(eq)
    bid,ask=dec(spec['bid']),dec(spec['ask'])
    if bid>ask or int(spec.get('tick_age_ms',999999))>3000:
        raise ProposalDenied('STALE_OR_INVERTED_BROKER_QUOTE')
    price=ask if side=='BUY' else bid
    tick,point=dec(spec['tick_size']),dec(spec['point'])
    minimum=dec(spec['min_lots']); maximum=dec(spec['max_lots'])
    step=dec(spec['volume_step'])
    if maximum<minimum or minimum/step!=(minimum/step).to_integral_value():
        raise ProposalDenied('INVALID_VOLUME_SPECIFICATION')
    trs=[]
    for before,cur in zip(bars[-15:-1],bars[-14:]):
        h,l,pc=(dec(cur['high']),dec(cur['low']),dec(before['close']))
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    if len(trs)!=14:raise ProposalDenied('INSUFFICIENT_ATR_INPUT')
    atr=sum(trs,D('0'))/D('14')
    floor=D(str(max(int(spec['stops_level_points']),int(spec['freeze_level_points']))))*point
    # 1.5 ATR, but always beyond the current broker min/freeze level.
    dist=align(max(atr*D('1.5'),floor+2*tick),tick,ROUND_CEILING)
    if dist<=0 or dist>price*D('0.25'):
        raise ProposalDenied('ATR_OR_BROKER_MINIMUM_STOP_UNSAFE')
    stop=align(price-dist,tick,ROUND_FLOOR) if side=='BUY' else align(price+dist,tick,ROUND_CEILING)
    take=align(price+2*dist,tick,ROUND_CEILING) if side=='BUY' else align(price-2*dist,tick,ROUND_FLOOR)
    closing=bid if side=='BUY' else ask
    if (stop<=0 or take<=0 or
        (side=='BUY' and not(stop<closing and closing+floor<take and closing-stop>floor)) or
        (side=='SELL' and not(take<closing and closing+floor<stop and closing-take>floor))):
        raise ProposalDenied('INVALID_CLOSE_SIDE_STOP_OR_TARGET')
    per_tick_spec=dec(spec['broker_tick_value_loss'])
    # Broker-native probe gives a conservative additional lower bound.
    probe_ticks=dec(spec['pnl_probe_displacement_ticks'])
    probe_minlots=dec(spec['min_lots'])
    native_probe=max(abs(D(str(spec['buy_probe_native_ordercalcprofit_usd']))),
                     abs(D(str(spec['sell_probe_native_ordercalcprofit_usd']))))
    per_tick=max(per_tick_spec,native_probe/probe_ticks/probe_minlots)
    slippage_ticks=D('15')*point/tick
    stop_ticks=abs(price-stop)/tick
    # Sizing is only provisional: historic commission is not a future fee schedule.
    risk_per_lot=(stop_ticks+slippage_ticks)*per_tick*D('1.20')
    # APEX M5/M15/H1 direction vote is already part of the native strategy.
    # Apply its conviction to the SAME existing 0.10% ceiling: signals with
    # mixed timeframes trade at no more than half the unanimous-vote budget.
    # Never increase the owner's existing risk limit or override MT5 sizing.
    conviction=D('1')
    mtf=signal.get('directional_context')
    if mtf is not None:
        if not isinstance(mtf,dict):raise ProposalDenied('INVALID_APEX_DIRECTIONAL_CONTEXT')
        try:vote=D(str(mtf['direction_score']))
        except (TypeError,ValueError,KeyError):raise ProposalDenied('INVALID_APEX_DIRECTIONAL_SCORE') from None
        if (not vote.is_finite() or abs(vote)>D('1') or
            (side=='BUY' and vote<=0) or (side=='SELL' and vote>=0)):
            raise ProposalDenied('APEX_DIRECTION_VOTE_MISMATCH')
        conviction=max(D('0.50'),abs(vote))
    risk_budget=equity*D('0.001')*D('0.85')*conviction
    # $0.10 holdback for unknown fee/rounding; MT5 must independently recheck.
    allowed=risk_budget-D('0.10')
    if allowed<=0 or risk_per_lot<=0 or minimum*risk_per_lot>allowed:
        raise ProposalDenied('MIN_LOT_EXCEEDS_CONSERVATIVE_010_RISK')
    num_steps=((allowed/risk_per_lot-minimum)/step).to_integral_value(rounding=ROUND_FLOOR)
    lots=min(maximum,minimum+num_steps*step)
    if lots<minimum or lots*risk_per_lot+D('0.10')>risk_budget:
        raise ProposalDenied('LOT_ROUNDING_EXCEEDS_RISK_CAP')
    key=hashlib.sha256(f'{owner}|{CID}|{sym}|M5|{int(ts)-300}|{side}'.encode()).hexdigest()
    if (type(signal.get('decision_id')) is not str or len(signal['decision_id'])!=64 or
        any(c not in '0123456789abcdef' for c in signal['decision_id'])):
        raise ProposalDenied('INVALID_APEX_DECISION_ID')
    order={'action':'TRADE_ACTION_DEAL','symbol':sym,'type':'ORDER_TYPE_'+side,
           'volume':str(lots),'price':str(price),'sl':str(stop),'tp':str(take),
           'magic':MAGIC,'deviation':15,'type_time':'ORDER_TIME_GTC',
           'comment':'APEX11 DERIV DEMO'}
    return {'schema':'abutron.apex11.7593.unsubmitted_exact_order_draft.v1',
            'source':'APEX11_ACCOUNT_BOUND_NATIVE_M5_JOURNAL',
            'signal_id':key,'source_decision_id':signal['decision_id'],
            'source_bar_closed_utc':int(ts),'account_suffix':'7593',
            'connection_id':CID,'broker':'Deriv','environment':'DEMO',
            'side':side,'symbol':sym,'order':order,
            'risk_budget_usd':str(risk_budget),
            'directional_risk_fraction':str(conviction),
            'original_policy_risk_ceiling_pct':'0.10',
            'conservative_estimated_loss_usd':str(lots*risk_per_lot+D('0.10')),
            'risk_estimate_only':True,'risk_model':'ATR14_1p5_STOPS_MIN_RR2_CONSERVATIVE_TICK_PROBE_MTF_ADAPTIVE_SIZE',
            'broker_exact_ordercalcprofit_verified':False,
            'broker_exact_ordercheck_verified':False,'crm_execution_ack_verified':False,
            'broker_order_ack_verified':False,'dispatch_authorized':False,
            'orders_submitted':0,'manual_trades_count_as_exposure_not_apex_signals':True,
            'expires_utc':int(ts)+300}

def retain_exact_first_quote(candidate, previous, now):
    """A native no-send check must match the unmodified originating draft.

    The M5 signal and native OrderCheck evidence stay valid only within the
    original bar. Broker quote and risk still undergo native checks on use.
    """
    if not isinstance(previous,dict):return candidate
    keys=('signal_id','source_decision_id','source_bar_closed_utc',
          'connection_id','symbol','side','broker','environment')
    if any(previous.get(k)!=candidate.get(k) for k in keys):return candidate
    if previous.get('original_policy_risk_ceiling_pct') != '0.10': return candidate
    if (previous.get('orders_submitted')!=0 or
        previous.get('dispatch_authorized') is not False or
        previous.get('broker_exact_ordercheck_verified') is not False or
        type(previous.get('expires_utc')) is not int or
        not now+4 < previous['expires_utc'] <= int(candidate['source_bar_closed_utc'])+300):
        return candidate
    order=previous.get('order')
    if (not isinstance(order,dict) or
        order.get('symbol')!=candidate['symbol'] or
        order.get('type')!='ORDER_TYPE_'+candidate['side'] or
        order.get('magic')!=MAGIC):return candidate
    return previous

def trusted_json(path,limit=100000,age=40,owner_uid=0):
    if path.is_symlink():raise ProposalDenied('SYMLINK_SOURCE')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=owner_uid or
            st.st_mode & 0o022 or not 0<st.st_size<=limit or
            not -2<=time.time()-st.st_mtime<=age):
            raise ProposalDenied('STALE_OR_UNSAFE_ROOT_BROKER_SOURCE')
        raw=os.read(fd,limit+1)
        if len(raw)!=st.st_size:raise ProposalDenied('RACED_BROKER_SOURCE')
        return json.loads(raw)
    finally:os.close(fd)

def run():
    now=int(time.time())
    h=trusted_json(WORKER/'worker-health.json',20000,20,owner_uid=WORKER.stat().st_uid)
    nonce=h.get('nonce','')
    if (h.get('id')!=CID or h.get('status')!='CONNECTED' or
        h.get('mode')!='DEMO' or h.get('server')!='Deriv-Demo' or len(nonce)!=32):
        raise ProposalDenied('NATIVE_WORKER_IDENTITY_INVALID')
    cost=trusted_json(COST,100000,60)
    if (cost.get('account_suffix')!='7593' or cost.get('environment')!='DEMO' or
        cost.get('worker_nonce')!=nonce or
        cost.get('native_bid_ask_and_ordercalcprofit_verified') is not True or
        cost.get('native_minlot_ordercalcmargin_verified') is not True):
        raise ProposalDenied('BROKER_COST_REPORT_NOT_ATTESTED')
    streams=read_deriv_native_m5(connection_id=CID,
        health_path=WORKER/'worker-health.json',
        bars_path=WORKER/'terminal/MQL5/Files'/('ABUTRON_NATIVE_BARS_V2_'+nonce+'.txt'),
        account_path=WORKER/'terminal/MQL5/Files'/('ABUTRON_NATIVE_ACCOUNT_V2_'+nonce+'.txt'),
        login=LOGIN,server='Deriv-Demo')
    db=sqlite3.connect('file:'+str(OUT/'account-bound-m5-journal.sqlite3')+'?mode=ro',
                       uri=True,timeout=4)
    db.execute('pragma query_only=on')
    row=db.execute('SELECT customer_id FROM decisions WHERE account_id=? LIMIT 1',(CID,)).fetchone()
    if not row:raise ProposalDenied('APEX_JOURNAL_MISSING')
    owner=row[0]
    drafts=[];blocks={}
    # Preserve the exact first native quote and SL/TP for an M5 signal until
    # that signal expires. Otherwise the recurring timer changes the draft
    # while the corresponding MT5 OrderCheck receipt remains immutable.
    previous={}
    try:
        old=trusted_json(OUT/'exact-order-draft-latest.json',50000,90)
        if (old.get('schema')=='abutron.apex11.7593.order_draft_inspection.ro.v1'
                and old.get('orders_submitted')==0):
            previous={x['signal_id']:x for x in old.get('drafts',[])
                      if isinstance(x,dict) and isinstance(x.get('signal_id'),str)}
    except (OSError,ValueError,ProposalDenied,TypeError,KeyError):
        pass
    apex_priority={}
    for sym in sorted(DERIV_ALLOWED):
        rr=db.execute('SELECT customer_id,payload FROM decisions WHERE account_id=? AND symbol=? ORDER BY closed_ts DESC LIMIT 1',(CID,sym)).fetchone()
        if not rr or rr[0]!=owner or sym not in streams or sym not in cost['instruments']:
            blocks[sym]='NO_AUTHENTIC_MATCHED_APEX_DECISION_OR_NATIVE_QUOTE';continue
        try:
            proposal=json.loads(rr[1])
            draft=construct(proposal,cost['instruments'][sym],
                            streams[sym].bars,cost['account_equity_usd'],owner,now)
            draft=retain_exact_first_quote(draft,previous.get(draft['signal_id']),now)
            ctx=proposal.get('directional_context') or {}
            votes=abs(float(ctx.get('direction_score',0.0)))
            direction=1 if draft['side']=='BUY' else -1
            agent_net=sum(float(a['score']) for a in proposal.get('signals',[])
                          if isinstance(a,dict) and type(a.get('score')) in (int,float))
            apex_priority[draft['signal_id']]=(votes,max(0.0,direction*agent_net))
            drafts.append(draft)
        except (ProposalDenied,KeyError,TypeError,ValueError,ArithmeticError) as e:
            blocks[sym]=str(e)[:110]
    drafts.sort(key=lambda d:(d['source_bar_closed_utc'],
                *apex_priority.get(d['signal_id'],(0.0,0.0)),d['symbol']),
                reverse=True)
    report={'schema':'abutron.apex11.7593.order_draft_inspection.ro.v1',
            'checked_utc':datetime.now(timezone.utc).isoformat(),
            'state':'DRAFT_ONLY_NO_BROKER_ORDER_CHECK_OR_EXECUTION_AUTHORITY',
            'account':'Deriv DEMO 7593','drafts':drafts,'blocked':blocks,
            'orders_submitted':0,'manual_trades_provenance':'SEPARATE_FROM_APEX',
            'broker_ordercheck_verified':False,'broker_ack_verified':False}
    dest=OUT/'exact-order-draft-latest.json'
    if OUT.is_symlink() or OUT.stat().st_uid!=0 or OUT.stat().st_mode&0o077:
        raise ProposalDenied('UNSAFE_OUTPUT_DIR')
    tmp=dest.with_suffix('.tmp-'+str(os.getpid()))
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(report,f,sort_keys=True,separators=(',',':'))
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
    finally:tmp.unlink(missing_ok=True)
    print(json.dumps({'state':report['state'],'drafts':len(drafts),
                      'blocked':blocks,'orders_submitted':0}))

if __name__=='__main__':run()
