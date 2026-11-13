"""APEX 1.1.0 -> ABUTRON broker candidate contract (NO ORDER SENDING).

Purpose: replace the old scanner/TradingAgents candidate eligibility logic,
while preserving tenant control, account binding, native EA, single-writer,
per-trade nominal risk, portfolio exposure and receipt identity invariants.
The production old router cannot consume these candidates unchanged.
Neither this code nor its outputs may authorize or submit an MT5 order.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import math
import re
from typing import Mapping, Any
from .production_contracts import FeedRefused, DERIV_ALLOWED, HEX32

FP_SUPPORTED=frozenset({'XAUUSD','BTCUSD','EURUSD','GBPUSD','USDJPY','AUDUSD',
 'US100','US30','SP500','GER40','USOIL','USDCHF','NZDUSD'})


@dataclass(frozen=True)
class BrokerNativeRisk:
    tick_size:float
    tick_value_per_lot_usd:float
    min_lot:float
    max_lot:float
    lot_step:float
    min_stop_ticks:int
    broker_verified:bool
    price:float
    stop_price:float
    take_price:float
    slippage_budget_ticks:int
    broker_calc_profit_verified:bool=False
    broker_order_check_verified:bool=False


@dataclass(frozen=True)
class AccountGate:
    broker:str
    environment:str
    server:str
    owner:str
    connection_id:str
    account_bound:bool
    worker_nonce_bound:bool
    fresh_broker_session:bool
    native_ea_account_match:bool
    broker_trade_allowed:bool
    terminal_trade_allowed:bool
    customer_switch_desired:bool
    customer_switch_effective:bool
    crm_entitlement_approved:bool
    single_writer_exclusive:bool
    existing_pending_orders:int
    broker_positions_protected:bool
    broker_exposure_reconciled:bool
    account_equity_usd:float
    current_verified_stop_risk_usd:float
    order_history_uncertain:bool=False
    kill_switch_halted:bool=False
    live_utc:int=0


def make_canonical_id(*,gate:AccountGate,signal:Mapping[str,Any])->str:
    side=signal.get('status');symbol=signal.get('symbol');close=signal.get('bar_closed_ts')
    if side not in ('BUY','SELL') or not isinstance(close,(int,float)) or close!=int(close) or int(close)%300:
        raise FeedRefused('NO_DIRECTIONAL_CLOSED_M5_SIGNAL')
    if gate.broker=='deriv':
        if symbol not in DERIV_ALLOWED:raise FeedRefused('DERIV_SYMBOL_NOT_APPROVED')
        # Old Deriv ledger expected_key uses M5 opening time.
        return sha256(f'{gate.owner}|{gate.connection_id}|{symbol}|M5|{int(close)-300}|{side}'.encode()).hexdigest()
    if gate.broker=='fp_markets':
        if symbol not in FP_SUPPORTED:raise FeedRefused('FP_SYMBOL_NOT_APPROVED')
        # Separate namespace because Deriv ledger enforces broker='Deriv'.
        return sha256(f'APEX11|FP_MARKETS|{gate.owner}|{gate.connection_id}|{symbol}|M5|{int(close)}|{side}'.encode()).hexdigest()
    raise FeedRefused('UNSUPPORTED_BROKER')


def review_candidate(*,signal:Mapping[str,Any],gate:AccountGate,
                     native:BrokerNativeRisk, now:int,
                     per_trade_risk_pct:float=.001,
                     portfolio_ceiling_pct:float=.20)->dict[str,Any]:
    """Explicit fail-closed *review*, not an executable order contract.

    No legacy research or LLM veto dependencies. Full broker native OrderCheck,
    OrderCalcProfit and receipt/reconciliation remain external mandatory gates.
    """
    blocks=[]
    def block(value):
        if value not in blocks: blocks.append(value)
    if not isinstance(signal,Mapping) or signal.get('engine')!='APEX_1_1_0' or signal.get('order') is not None:
        block('CANDIDATE_NOT_ATTESTED_APEX_SIGNAL_ONLY')
    if signal.get('broker')!=gate.broker or signal.get('timeframe')!='M5':
        block('CANDIDATE_BROKER_OR_TIMEFRAME_MISMATCH')
    if not isinstance(signal.get('decision_id'),str) or not re.fullmatch('[0-9a-f]{64}',signal['decision_id']):
        block('CANDIDATE_DECISION_ID_INVALID')
    if gate.environment!='DEMO' or (gate.broker=='deriv' and gate.server!='Deriv-Demo') or (
            gate.broker=='fp_markets' and gate.server!='FPMarketsSC-Demo'):
        block('DEMO_ONLY_ACCOUNT_BOUNDARY')
    if not HEX32.fullmatch(gate.owner) or not HEX32.fullmatch(gate.connection_id):
        block('CUSTOMER_OR_CONNECTION_ID_INVALID')
    if not all((gate.account_bound,gate.worker_nonce_bound,gate.fresh_broker_session,
                gate.native_ea_account_match,gate.broker_trade_allowed,gate.terminal_trade_allowed)):
        block('BROKER_OR_EA_ATTESTATION_MISSING')
    if not (gate.customer_switch_desired and gate.customer_switch_effective):
        block('CLIENT_AUTOMATIC_SWITCH_OFF')
    if not gate.crm_entitlement_approved: block('CRM_ENTITLEMENT_DENIED')
    if not gate.single_writer_exclusive: block('EXCLUSIVE_ORDER_WRITER_UNVERIFIED')
    if gate.existing_pending_orders!=0: block('NATIVE_PENDING_ORDER_EXPOSURE')
    if not gate.broker_positions_protected or not gate.broker_exposure_reconciled:
        block('BROKER_OPEN_POSITIONS_NOT_RECONCILED')
    if gate.order_history_uncertain: block('UNKNOWN_NATIVE_ORDER_OUTCOME_NO_RETRY')
    if gate.kill_switch_halted:block('KILL_SWITCH_ACTIVE')
    if not (math.isfinite(gate.account_equity_usd) and gate.account_equity_usd>0 and
            math.isfinite(gate.current_verified_stop_risk_usd) and gate.current_verified_stop_risk_usd>=0):
        block('BROKER_EQUITY_OR_OPEN_RISK_UNVERIFIED')
    if (portfolio_ceiling_pct!=0.2 or per_trade_risk_pct not in (0.001,0.0015,0.002) or
        (per_trade_risk_pct in (0.0015,0.002) and not (gate.broker=="deriv" and gate.environment=="DEMO" and
         gate.connection_id=="d6fc2524ec373b8d1bc278a8be3ec635"))):
        block('RISK_POLICY_MUST_MATCH_ABUTRON_ACCOUNT_AND_20')
    signal_close=signal.get('bar_closed_ts')
    if not isinstance(signal_close,(int,float)) or not math.isfinite(float(signal_close)) or signal_close!=int(signal_close) or int(signal_close)%300:
        block('SIGNAL_CLOSED_BAR_TIME_INVALID')
    elif int(signal_close)>now:
        block('SIGNAL_BAR_IN_FUTURE')
    key=None
    try:
        key=make_canonical_id(gate=gate,signal=signal)
    except (FeedRefused,ValueError,TypeError) as ex:
        block(str(ex))
    side=signal.get('status')
    if side not in {'BUY','SELL'}: block('APEX_HOLD_OR_WARMUP')
    vals=[native.tick_size,native.tick_value_per_lot_usd,native.min_lot,native.max_lot,
          native.lot_step,native.price,native.stop_price,native.take_price]
    if not native.broker_verified or not all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in vals):
        block('CONTRACT_VALUE_OR_NATIVE_PRICE_UNVERIFIED')
    if not isinstance(native.min_stop_ticks,int) or native.min_stop_ticks<1 or not isinstance(native.slippage_budget_ticks,int) or native.slippage_budget_ticks<0:
        block('NATIVE_STOP_OR_SLIPPAGE_BOUND_UNVERIFIED')
    if side=='BUY' and not(native.stop_price<native.price<native.take_price): block('INVALID_BUY_STOPS')
    if side=='SELL' and not(native.take_price<native.price<native.stop_price): block('INVALID_SELL_STOPS')
    if not (native.broker_calc_profit_verified and native.broker_order_check_verified):
        block('BROKER_ORDER_CALC_PROFIT_AND_CHECK_MISSING')
    budget=gate.account_equity_usd*per_trade_risk_pct
    volume=None;stress_loss=None
    if not any(x in blocks for x in ('CONTRACT_VALUE_OR_NATIVE_PRICE_UNVERIFIED','NATIVE_STOP_OR_SLIPPAGE_BOUND_UNVERIFIED')):
        stop_ticks=abs(native.price-native.stop_price)/native.tick_size
        if stop_ticks<native.min_stop_ticks:
            block('BROKER_MINIMUM_STOP_DISTANCE_UNSATISFIED')
        loss_per_lot=(stop_ticks+native.slippage_budget_ticks)*native.tick_value_per_lot_usd
        if loss_per_lot<=0 or not math.isfinite(loss_per_lot):
            block('INVALID_POTENTIAL_LOSS_PER_LOT')
        else:
            steps=math.floor((budget/loss_per_lot-native.min_lot)/native.lot_step+1e-10)
            if steps<0: block('MINIMUM_LOT_EXCEEDS_010_PERCENT_RISK')
            else:
                volume=round(min(native.max_lot,native.min_lot+steps*native.lot_step),8)
                stress_loss=volume*loss_per_lot
                if volume<native.min_lot or stress_loss>budget+1e-8:
                    block('LOT_RISK_ROUNDING_UNSAFE')
                if gate.current_verified_stop_risk_usd+stress_loss>gate.account_equity_usd*portfolio_ceiling_pct:
                    block('PORTFOLIO_20_PERCENT_CEILING_EXCEEDED')
    ready = not blocks
    return {'schema':'abutron.apex11.broker.candidate.review.v1',
            'broker':gate.broker,'environment':gate.environment,'symbol':signal.get('symbol'),
            'side':side,'source_decision_id':signal.get('decision_id'),
            'signal_id_for_separate_ledger':key,'nominal_stop_risk_usd':round(stress_loss,4) if stress_loss is not None else None,
            'proposed_lots_research_only':volume,'risk_budget_usd':round(budget,4),
            'blockers':blocks,'engineering_gates_passed':ready,
            'order_candidate': ({'signal_id':key,'broker':gate.broker,
                'connection_id':gate.connection_id,'symbol':signal.get('symbol'),
                'side':side,'volume_lots':volume,'stop_price':native.stop_price,
                'take_price':native.take_price} if ready else None),
            'orders_submitted':0,
            'needs_existing_broker_native_dispatcher_rewrite':True,
            'broker_native_final_risk_proof_required':True,
            'no_retry_of_unknown_orders':True}
