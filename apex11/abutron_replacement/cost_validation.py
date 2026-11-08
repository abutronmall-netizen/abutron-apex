"""Descriptive APEX 1.1.0 cost-sensitive replay — not a strategy approval gate.

No 200-observation minimum, no 14-day waiting period, no positive statistical
confidence threshold and no promotion authorization. Historical broker spreads
and commissions are estimates unless truly time-aligned with individual fills.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math, statistics
from typing import Mapping, Sequence
from .production_contracts import FeedRefused


@dataclass(frozen=True)
class CostEvidence:
    symbol:str
    spread_p95_bps:float
    historical_roundtrip_commission_bps:float
    hypothetical_slippage_each_side_bps:float
    source_reference_sha256:str
    observed_quote_history_aligned:bool=False
    actual_order_slippage_verified:bool=False
    complete_commission_evidence:bool=False

    def checked(self):
        values=(self.spread_p95_bps,self.historical_roundtrip_commission_bps,
                self.hypothetical_slippage_each_side_bps)
        if not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in values):
            raise FeedRefused('COST_SOURCE_NONFINITE_OR_NEGATIVE')
        if (not isinstance(self.source_reference_sha256,str) or
                len(self.source_reference_sha256)!=64 or
                any(c not in '0123456789abcdef' for c in self.source_reference_sha256)):
            raise FeedRefused('COST_SOURCE_HASH_INVALID')
        return self


def replay_signals(*,bars:Sequence[Mapping],signals:Sequence[Mapping],costs:CostEvidence,
                   horizon_bars:int=3)->dict:
    """Next-bar hypothetical fills with a defined exit horizon.

    Gaps do not veto entire history. Trades that would cross missing candles
    are skipped; no invented price data or hidden promotion rule is introduced.
    """
    costs.checked()
    if type(horizon_bars) is not int or horizon_bars<1:
        raise FeedRefused('INVALID_REPLAY_HORIZON')
    times=[]
    for bar in bars:
        try:
            t=int(bar['ts'])
            values=[float(bar[k]) for k in ('open','high','low','close')]
        except (KeyError,ValueError,TypeError,OverflowError):
            raise FeedRefused('INVALID_REPLAY_BAR') from None
        if (t<=0 or t%300 or not all(math.isfinite(v) and v>0 for v in values)
                or values[1]<max(values[0],values[3]) or values[2]>min(values[0],values[3])):
            raise FeedRefused('INVALID_REPLAY_BAR')
        if times and t<=times[-1]:
            raise FeedRefused('DUPLICATE_OR_UNSORTED_REPLAY')
        times.append(t)
    by_timestamp={}
    for sig in signals:
        t=int(sig['bar_closed_ts'])
        direction=sig.get('status')
        if t in by_timestamp:raise FeedRefused('DUPLICATE_SIGNAL_ON_BAR')
        if direction not in ('BUY','SELL','HOLD','WARMUP'):
            raise FeedRefused('UNKNOWN_SIGNAL_SIDE')
        if sig.get('symbol')!=costs.symbol:
            raise FeedRefused('SIGNAL_SYMBOL_MISMATCH')
        by_timestamp[t]=direction

    results=[];prev_side=None;last_exit=-1;skipped_gap=0
    for i in range(len(times)-horizon_bars):
        current=by_timestamp.get(times[i]);direction=current
        if current is None:
            prev_side=None
            continue
        if direction not in ('BUY','SELL'):
            prev_side=direction
            continue
        # APEX outputs a target side each candle; repeat BUY is not a new order.
        fresh=direction!=prev_side
        prev_side=direction
        if not fresh or i<=last_exit:
            continue
        # Never pretend there was a valid next-bar price across a missing interval.
        if any(times[j+1]-times[j]!=300 for j in range(i,i+horizon_bars)):
            skipped_gap+=1
            prev_side=None
            continue
        entry_i=i+1;exit_i=i+horizon_bars
        entry=float(bars[entry_i]['open']);exit_price=float(bars[exit_i]['close'])
        gross=(1 if direction=='BUY' else -1)*(exit_price/entry-1)*10000
        cost=(costs.spread_p95_bps+costs.historical_roundtrip_commission_bps+
              2*costs.hypothetical_slippage_each_side_bps)
        results.append({'signal_ts':times[i],'entry_ts':times[entry_i],
            'exit_ts':times[exit_i],'side':direction,
            'gross_bps':round(gross,5),'cost_stress_bps':round(cost,5),
            'net_bps':round(gross-cost,5),
            'exit_day_utc':datetime.fromtimestamp(times[exit_i],timezone.utc).date().isoformat()})
        last_exit=exit_i
    sample=[r['net_bps'] for r in results]
    return {'schema':'abutron.apex11.descriptive.cost_replay.v2',
        'instrument':costs.symbol,'simulation_only':True,
        'fill_model':'next_M5_open_to_horizon_M5_close',
        'trades_nonoverlapping':len(results),
        'days_observed':len({r['exit_day_utc'] for r in results}),
        'skipped_trades_crossing_missing_candles':skipped_gap,
        'mean_stressed_net_bps':round(statistics.mean(sample),5) if sample else None,
        'median_stressed_net_bps':round(statistics.median(sample),5) if sample else None,
        'cost_source_sha256':costs.source_reference_sha256,
        'historical_quotes_aligned':costs.observed_quote_history_aligned,
        'actual_slippage_verified':costs.actual_order_slippage_verified,
        'commission_complete':costs.complete_commission_evidence,
        'broker_orders_verified':0,
        'real_broker_profitability_certified':False,
        'sample_trade_outcomes':results[:4]}
