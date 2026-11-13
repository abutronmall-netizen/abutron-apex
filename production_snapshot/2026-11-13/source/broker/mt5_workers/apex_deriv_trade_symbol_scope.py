"""Approved ABUTRON APEX Deriv DEMO NEW-ENTRY symbols only.

The 13-symbol raw MT5 feed and historical ledger MUST remain intact.
This allowlist is a fail-closed NEW-ORDER scope, not a position-closing command.
"""
TRADE_SYMBOLS=frozenset((
    "Volatility 25 Index.0",
    "Volatility 50 Index.0",
    "Volatility 75 Index.0",
))
assert len(TRADE_SYMBOLS)==3
