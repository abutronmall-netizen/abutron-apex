"""Operator-run LOCAL offline APEX 1.1.0 replay on *copied* authenticated archive.

Strictly no production path defaults, network, broker APIs, or order submission.
The supplied CopyRates source must have been authenticated separately.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from collections import Counter
from .bridge import AbutronApex11SignalBridge
from .cost_validation import CostEvidence,replay_signals
from .long_history import read_archive_contiguous_tail,load_deriv_archive_segments,archive_warmup_readiness
from .production_contracts import FeedRefused


def run(*,database:Path,proof_file:Path,manifest:dict,cost_reference:dict,
        connection_id:str,symbol:str,rows:int=1800,horizon:int=3,slippage_bps_each_side:float=5.0)->dict:
    if manifest.get('broker')!='deriv' or manifest.get('symbol')!=symbol:
        raise FeedRefused('MANIFEST_BROKER_OR_SYMBOL_MISMATCH')
    if cost_reference.get('schema')!='abutron.deriv.microstructure_cost_deal_evidence.v1' or cost_reference.get('actual_order_slippage_distribution_verified') is not False:
        raise FeedRefused('UNRECOGNISED_COST_EVIDENCE')
    if cost_reference.get('no_full_historical_spread_distribution') is not True:
        raise FeedRefused('COST_SOURCE_NOT_BOUNDED_AS_EXPECTED')
    src=cost_reference.get('spreads',{}).get(symbol)
    if not src or src.get('quote_records_passed') is not True or src.get('historical_slippage_verified') is not False:
        raise FeedRefused('SPREAD_OR_SLIPPAGE_SOURCE_UNVERIFIED')
    metadata={**manifest,'spread_bps':src['spread_bps_p95'],
              'commission_bps':src['historical_broker_deal_roundtrip_commission_bps_at_prior_quote']}
    # A historical time-truncated sample: no fabricated contemporaneous spreads.
    bars=read_archive_contiguous_tail(database=database,proof_file=proof_file,
                                     symbol=symbol,connection_id=connection_id,
                                     rows_needed=rows)
    bridge=AbutronApex11SignalBridge([metadata])
    decisions=[bridge.on_closed_candle(b) for b in bars]
    evidence=CostEvidence(symbol=symbol,spread_p95_bps=src['spread_bps_p95'],
        historical_roundtrip_commission_bps=src['historical_broker_deal_roundtrip_commission_bps_at_prior_quote'],
        hypothetical_slippage_each_side_bps=slippage_bps_each_side,
        source_reference_sha256=cost_reference['cost_reference_source_sha256'],
        observed_quote_history_aligned=False,actual_order_slippage_verified=False,
        complete_commission_evidence=False)
    costresult=replay_signals(bars=bars,signals=decisions,costs=evidence,horizon_bars=horizon)
    counts=Counter(x['status'] for x in decisions)
    return {'schema':'abutron.apex11.real_archive_research_replay.v1',
      'source_kind':'DERIV_DEMO_MT5_READONLY_COPYRATES_VERIFIED_RESEARCH_ONLY',
      'archive_account_suffix':'6207','last_archived_bar_close':bars[-1]['ts'],
      'bars_used':len(bars),'apex_decision_counts':dict(counts),
      'cost_sensitive_nonoverlapping_research':costresult,
      'orders_submitted':0,
      'not_full_portfolio_backtest':True,'cannot_establish_live_profitability':True}


def main(argv=None):
    p=argparse.ArgumentParser(description='Offline APEX research replay; cannot trade')
    p.add_argument('--db',type=Path,required=True)
    p.add_argument('--proof',type=Path,required=True)
    p.add_argument('--cost-reference',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--symbol',required=True)
    p.add_argument('--connection-id',required=True)
    p.add_argument('--bars',type=int,default=1800)
    p.add_argument('--horizon',type=int,default=3)
    p.add_argument('--hypothetical-slip-bps-each-side',type=float,default=5.0)
    args=p.parse_args(argv)
    doc=run(database=args.db,proof_file=args.proof,manifest=json.loads(args.manifest.read_text()),
            cost_reference=json.loads(args.cost_reference.read_text()),
            connection_id=args.connection_id,symbol=args.symbol,rows=args.bars,
            horizon=args.horizon,slippage_bps_each_side=args.hypothetical_slip_bps_each_side)
    print(json.dumps(doc,indent=2,sort_keys=True))

if __name__=='__main__':main()
