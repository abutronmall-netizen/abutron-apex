#!/usr/bin/env python3
"""ABUTRON prospective six-model FORWARD MARKET OUTCOME research.
No order dispatch, no changes to MT5/EAs, no live trading.
"""
from __future__ import annotations
import bisect,datetime as dt,hashlib,json,os,sqlite3,sys,tempfile,time,grp,math,collections
from pathlib import Path
sys.path[:0]=['/opt/apex/runtime','/opt/apex-client-mt5/quant-first']
import abutron_forward_cost_shadow_v1 as feed
import abutron_entry_model_v1 as strategy

ROOT=Path('/var/lib/abutron-quant-first')
DB=ROOT/'entry-model-forward-v1.sqlite3'
REPORT=ROOT/'entry-model-forward-latest.json'
COST=Path('/var/backups/abutron-cost-research-20261106T2235Z/BROKER_COST_REFERENCE_EQUITY_V2.json')
MODEL=Path('/opt/apex-client-mt5/quant-first/abutron_entry_model_v1.py')
SYMS=tuple(sorted(strategy.STRATEGIES))
SCHEMA='abutron.quant.entry_model.forward.market_outcome.v1'
CANDLES_NEEDED=12

def verified_inputs():
    now=dt.datetime.now(dt.timezone.utc)
    market=feed.source_data(now=now)
    cost=json.load(open(COST))
    assert cost['schema']=='abutron.deriv.authenticated.broker.cost.contract.v2'
    assert set(cost['instruments'])==set(feed.SYMS)
    if MODEL.is_symlink() or COST.is_symlink():
        raise ValueError('UNTRUSTED_STRATEGY_OR_COST_SOURCE')
    code_sha=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    cost_sha=hashlib.sha256(COST.read_bytes()).hexdigest()
    return now,market,cost,code_sha,cost_sha

def install_schema(c):
    c.execute("""CREATE TABLE IF NOT EXISTS observed(
        symbol TEXT NOT NULL,model TEXT NOT NULL,bar_time INTEGER NOT NULL,
        side TEXT NOT NULL,atr REAL NOT NULL,bar_digest TEXT NOT NULL,
        model_sha256 TEXT NOT NULL,cost_sha256 TEXT NOT NULL,
        stop_floor REAL NOT NULL,commission_per_lot REAL NOT NULL,
        usd_per_price_point_lot REAL NOT NULL,spread_bps_snapshot REAL NOT NULL,
        first_observed_utc TEXT NOT NULL,status TEXT NOT NULL,
        exit_reason TEXT,gross_bps REAL,net_5bps REAL,net_10bps REAL,net_20bps REAL,
        realized_at_utc TEXT,PRIMARY KEY(symbol,model,bar_time)
    )""")
    c.execute('CREATE INDEX IF NOT EXISTS observed_pending ON observed(status,bar_time)')

def candidate_decisions(market):
    suggestions={}
    for sym in feed.SYMS:
        frames=market[sym]
        m5=frames['M5'];h1=frames['H1']
        if len(m5)<100 or len(h1)<60:raise ValueError('NOT_ENOUGH_LIVE_COMPLETED_BARS')
        m5rows=[(int(x['time']),float(x['open']),float(x['high']),float(x['low']),float(x['close'])) for x in m5]
        h1rows=[(int(x['time']),float(x['open']),float(x['high']),float(x['low']),float(x['close'])) for x in h1]
        atr=strategy.features(m5rows)
        ends,dirs=strategy.h1_regime(h1rows)
        anchor=m5rows[-1][0]+300
        j=bisect.bisect_right(ends,anchor)-1
        if j<30:raise ValueError('NO_COMPLETED_H1_REGIME')
        picks=strategy.decide(len(m5rows)-1,m5rows,atr,dirs[j])
        if not set(picks).issubset(set(strategy.STRATEGIES)):
            raise ValueError('UNKNOWN_RESEARCH_MODEL')
        for model,side in picks.items():
            if side not in ('BUY','SELL'):raise ValueError('ILLEGAL_SIGNAL_SIDE')
        suggestions[sym]=(m5[-1],atr[-1][3],picks)
    return suggestions

def record(c,now,suggestions,cost,codehash,costhash):
    added=0;signals=0
    for sym,(bar,atr,picks) in suggestions.items():
        costrow=cost['instruments'][sym]
        reference=float(costrow['bid'])
        spread_bps=float(costrow['displayed_spread'])/reference*10000
        floor=float(costrow['minimum_broker_stop_price_distance'])
        commission=float(costrow['commission_usd_roundtrip_per_lot_median'])
        contract=float(costrow['ordercalcprofit_usd_per_price_point_per_lot'])
        if not all(math.isfinite(y) and y>=0 for y in (spread_bps,floor,commission)) or contract<=0 or atr<=0:
            raise ValueError('BROKER_COST_OR_INDICATOR_UNTRUSTED')
        for model,side in picks.items():
            signals+=1
            c.execute("""INSERT OR IGNORE INTO observed
            (symbol,model,bar_time,side,atr,bar_digest,model_sha256,cost_sha256,
             stop_floor,commission_per_lot,usd_per_price_point_lot,spread_bps_snapshot,
             first_observed_utc,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sym,model,bar['time'],side,atr,feed.digest(bar),codehash,costhash,
             floor,commission,contract,spread_bps,now.isoformat(),'PENDING'))
            added+=c.execute('SELECT changes()').fetchone()[0]
    return signals,added

def settle(c,now,market,codehash,costhash):
    done=blocked=0
    pending=c.execute("""SELECT symbol,model,bar_time,side,atr,bar_digest,model_sha256,
       cost_sha256,stop_floor,commission_per_lot,usd_per_price_point_lot,spread_bps_snapshot
       FROM observed WHERE status='PENDING'""").fetchall()
    for sym,model,clock,side,atr,barsha,modelsha,costsha,stopfloor,commission,contract,spread in pending:
        m5=market[sym]['M5']
        j=next((i for i,b in enumerate(m5) if b['time']==clock),None)
        if j is None:
            if m5[-1]['time']-clock>100*300:
                c.execute("UPDATE observed SET status='UNVERIFIABLE_GAP',realized_at_utc=? WHERE symbol=? AND model=? AND bar_time=?",
                          (now.isoformat(),sym,model,clock));blocked+=1
            continue
        if feed.digest(m5[j])!=barsha or codehash!=modelsha or costhash!=costsha:
            c.execute("UPDATE observed SET status='EVIDENCE_REVISED',realized_at_utc=? WHERE symbol=? AND model=? AND bar_time=?",
                      (now.isoformat(),sym,model,clock));blocked+=1
            continue
        if j+CANDLES_NEEDED>=len(m5):continue
        seq=[(int(x['time']),float(x['open']),float(x['high']),float(x['low']),float(x['close'])) for x in m5]
        result=strategy.price_outcome(seq,j,side,atr,stopfloor,hold=CANDLES_NEEDED)
        if result is None:
            c.execute("UPDATE observed SET status='UNVERIFIABLE_GAP',realized_at_utc=? WHERE symbol=? AND model=? AND bar_time=?",
                      (now.isoformat(),sym,model,clock));blocked+=1
            continue
        comm_bps=commission/(result['entry']*contract)*10000
        net=[result['gross_bps']-comm_bps-spread-b for b in (5.,10.,20.)]
        c.execute("""UPDATE observed SET status='MARKET_OUTCOME_MEASURED',
          exit_reason=?,gross_bps=?,net_5bps=?,net_10bps=?,net_20bps=?,realized_at_utc=?
          WHERE symbol=? AND model=? AND bar_time=?""",
          (result['reason'],result['gross_bps'],*net,now.isoformat(),sym,model,clock))
        done+=1
    return done,blocked

def build_report(c,now,newsignals,inserted,measured,excluded,hashmodel,hashcost):
    out={}
    for sym in feed.SYMS:
        out[sym]={}
        for model in strategy.STRATEGIES:
            rows=c.execute("SELECT status,net_10bps FROM observed WHERE symbol=? AND model=? ORDER BY bar_time",(sym,model)).fetchall()
            net=[float(r[1]) for r in rows if r[0]=='MARKET_OUTCOME_MEASURED' and r[1] is not None]
            out[sym][model]={'prospective_signals_recorded':len(rows),
             'outcomes_measured_from_future_market_candles':len(net),
             'pending':sum(r[0]=='PENDING' for r in rows),
             'unverifiable':sum(r[0] in ('UNVERIFIABLE_GAP','EVIDENCE_REVISED') for r in rows),
             'assumed_net_10bps_mean':round(sum(net)/len(net),4) if net else None,
             'broker_acknowledged_order_trades_from_model':0}
    return {'schema':SCHEMA,'evaluated_at_utc':now.isoformat(),
            'mode':'PROSPECTIVE_NATIVE_MARKET_SHADOW_RESEARCH',
            'is_genuine_forward_observation':True,
            'is_real_broker_fill_or_pnl':False,
            'new_signal_decisions':newsignals,'new_unique_signals_recorded':inserted,
            'new_forward_market_outcomes':measured,'new_invalidated':excluded,
            'model_sha256':hashmodel,'cost_snapshot_sha256':hashcost,
            'forward_min_outcomes_per_instrument_model_for_review':30,
            'broker_costs':'REAL_DEAL_COMMISSIONS_PLUS_SINGLE_ZERO_SPREAD_SNAPSHOT',
            'slippage':'HYPOTHETICAL_5_10_20_BASIS_POINTS_NOT_MEASURED',
            'exit':'NEXT_M5_OPEN_ATR_SL_TP_BROKER_STOP_MIN_TIME_LIMIT_STOP_FIRST',
            'order_execution_authorized':False,'orders_submitted':0,
            'real_account_positions_changed':False,
            'promotion_permitted':False,'models':out}

def main():
    now,market,cost,hashmodel,hashcost=verified_inputs()
    suggestions=candidate_decisions(market)
    if DB.is_symlink() or REPORT.is_symlink():
        raise ValueError('UNSAFE_FORWARD_OUTPUT')
    with sqlite3.connect(str(DB),timeout=12) as c:
        c.execute('pragma busy_timeout=12000')
        c.execute('BEGIN IMMEDIATE')
        install_schema(c)
        signals,inserted=record(c,now,suggestions,cost,hashmodel,hashcost)
        measured,bad=settle(c,now,market,hashmodel,hashcost)
        report=build_report(c,now,signals,inserted,measured,bad,hashmodel,hashcost)
        c.commit()
        assert c.execute('pragma quick_check').fetchone()[0]=='ok'
    DB.chmod(0o640)
    os.chown(DB,0,grp.getgrnam('apexagent').gr_gid)
    fd,tmp=tempfile.mkstemp(prefix='.entry-forward-',dir=REPORT.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(report,f,indent=2,allow_nan=False)
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640);os.chown(tmp,0,grp.getgrnam('apexagent').gr_gid)
        os.replace(tmp,REPORT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('FORWARD_RESEARCH',now.isoformat(),'CANDIDATES',signals,
          'NEW_RECORDS',inserted,'NEW_FORWARD_MARKET_OUTCOMES',measured,
          'INVALIDATED',bad,'BROKER_ORDERS',0)

if __name__=='__main__':main()
