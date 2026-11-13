#!/usr/bin/env python3
"""Retire the six failed ABUTRON 6207 legacy factor families from NEW intent publication.
No deletion of historical research evidence; no change to existing open positions.
Research discovery and human-reviewed promoted model routes are separate.
"""
from __future__ import annotations

RETIRED_LEGACY_MODELS=frozenset({
    'trend_pullback','failed_breakout','ema_reversion',
    'range_sweep','trend_breakout','streak_fade',
})
VALID_SYMBOLS=frozenset({
    'Volatility 10 Index.0','Volatility 25 Index.0','Volatility 50 Index.0',
    'Volatility 75 Index.0','Volatility 100 Index.0',
})
def eligibility(symbol: str, model: str, side: str) -> tuple[bool,str]:
    if not all(isinstance(z,str) for z in (symbol,model,side)):
        return False,'INVALID_SIGNAL_IDENTITY'
    if symbol not in VALID_SYMBOLS or side not in ('BUY','SELL'):
        return False,'UNKNOWN_SYMBOL_OR_DIRECTION'
    if model in RETIRED_LEGACY_MODELS:
        return False,'RETIRED_LEGACY_SIX_NO_VALIDATED_PROFIT_EDGE'
    # This 6207 legacy intent route does not accept unregistered new models.
    # New quant models require independently reviewed promotion plus a new audited route.
    return False,'NO_INDEPENDENTLY_PROMOTED_MODEL_FOR_LEGACY_ROUTE'
