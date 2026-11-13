"""Offline read-only replay of account-bound Deriv/FP native M5 snapshots.

No sockets, order submission, MT5 dependencies, config mutation or auto-trading.
Manifest must contain *measured* and independently reviewed instrument metadata.
Any output is research evidence, never an execution authorization.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
from .bridge import AbutronApex11SignalBridge
from .production_contracts import (
    read_deriv_native_m5,read_fp_published_m5,FeedRefused,
)


def evaluate_bars(sources, manifest):
    by_symbol = {m['symbol']:m for m in manifest}
    if not by_symbol or len(by_symbol) != len(manifest):
        raise FeedRefused('MANIFEST_SYMBOLS_EMPTY_OR_DUPLICATE')
    if set(sources) != set(by_symbol):
        # Do not quietly omit disconnected or unapproved symbols.
        raise FeedRefused('SOURCE_AND_MANIFEST_SYMBOLS_DIFFER')
    brokers = {s.broker for s in sources.values()}
    cids = {s.connection_id for s in sources.values()}
    if len(cids) != 1 or len(brokers) != 1:
        raise FeedRefused('CROSS_ACCOUNT_OR_CROSS_BROKER_SOURCE_DENIED')
    if any(by_symbol[s]['broker'] != obj.broker for s,obj in sources.items()):
        raise FeedRefused('MANIFEST_BROKER_MISMATCH')
    bridge = AbutronApex11SignalBridge(manifest)
    outcome = {}
    for symbol, src in sorted(sources.items()):
        states = Counter()
        recent = []
        previous = None
        for bar in src.bars:
            previous = bar['ts']
            p = bridge.on_closed_candle(bar)
            states[p['status']] += 1
            if p['status'] in {'BUY','SELL','HOLD'}:
                recent.append({'bar_closed_ts':int(bar['ts']),
                               'status':p['status'],
                               'decision_id':p['decision_id']})
            if p['order'] is not None:
                raise FeedRefused('UNAUTHORIZED_ORDER_IN_REPLAY')
        outcome[symbol] = {
            'total_closed_m5_bars':len(src.bars),
            'state_counts':dict(sorted(states.items())),
            'latest_research_decisions':recent[-8:],
            'source_sha256':src.source_sha256,
            'source_kind':src.source_kind,
            'warmup_complete':len(src.bars)>bridge.warmup_bars,
            'broker_authentication_independent':src.broker_authenticated_by_this_code,
        }
    return {'schema':'abutron.apex11.offline.replay.v1',
            'broker':next(iter(brokers)),
            'orders_submitted':0,
            'real_broker_profitability_verified':False,
            'forward_net_cost_expectancy_verified':False,
            'results':outcome}


def main(argv=None):
    p = argparse.ArgumentParser(description='APEX 1.1 offline broker-file contract test (no orders)')
    p.add_argument('--source',required=True,choices=['deriv-native','fp-publisher'])
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--connection-id',required=True)
    p.add_argument('--historical',action='store_true')
    p.add_argument('--health',type=Path)
    p.add_argument('--bars',type=Path)
    p.add_argument('--account',type=Path)
    p.add_argument('--login')
    p.add_argument('--fp-snapshot',type=Path)
    a = p.parse_args(argv)
    if a.source=='deriv-native':
        if not (a.health and a.bars and a.account and a.login):
            p.error('Deriv requires --health --bars --account --login')
        sources=read_deriv_native_m5(
            connection_id=a.connection_id,health_path=a.health,
            bars_path=a.bars,account_path=a.account,login=a.login,
            historical=a.historical)
    else:
        if not a.fp_snapshot:
            p.error('FP requires --fp-snapshot')
        sources=read_fp_published_m5(
            path=a.fp_snapshot,connection_id=a.connection_id,historical=a.historical)
    manifest=json.loads(a.manifest.read_text())
    print(json.dumps(evaluate_bars(sources,manifest),indent=2,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
