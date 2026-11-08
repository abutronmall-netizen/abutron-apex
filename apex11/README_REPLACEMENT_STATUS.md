# ABUTRON / APEX 1.1.0 — User-directed removal of eight extra gates

Updated 8 November 2026. This package is an **offline revision** of the supplied APEX 1.1.0 replacement. No production deployment, service shutdown, broker order, or trading permission change was performed.

## User-requested removals implemented

| Removed | Actual code change |
|---|---|
| Minimum 200 matured observations | `cost_validation.py` no longer requires any minimum trade-observation count |
| Minimum 14 UTC days | `cost_validation.py` no longer requires a minimum number of days |
| Positive statistical-confidence promotion rule | No bootstrap lower-bound or statistical approval requirement; cost results are descriptive only |
| Mandatory 300-bar warm-up | `bridge.py` defaults to no extra warm-up (`warmup_bars=0`); the native APEX agents use their own indicator lookbacks |
| Arbitrary 100-second signal expiry | Removed from `candidate_contract.py`; closed-bar signals are no longer expired after 100 seconds |
| Entire-feed refusal on M5 candle gaps | Bridge resets the affected symbol's indicator window; history/replay retains observed gaps without fabricating candles |
| Separate handover approval in candidate eligibility | `AccountGate.handover_approved` and its denial are removed |
| Hard-coded `execution_authorized=false` in the replacement outputs | Removed. Eligible, account-bound, broker-checked candidates now emit an `order_candidate` containing identity, side, lot and stops; a noneligible signal does not |

The FP clock module is a diagnostic; it no longer issues permanent permission flags. The local replay does not impose a promotion or trade-authorization gate.

## Kept because already requested / necessary for broker correctness

- Your original **0.10% of account equity per trade** and **20% portfolio-risk ceiling**.
- Client ON/OFF switches, licensed-account binding, broker-account identity, correct protective SL/TP, native minimum lot/stop geometry, single order writer and broker reconciliation.
- Original APEX 1.1.0 trend / mean-reversion / breakout / regime / portfolio / risk engine; no Qlib, Qwen, TradingAgents or legacy strategy dependency in the new signal path.
- Input-data correctness (no fabricated candles, incorrect account association, duplicate bars, or false broker ACKs).

## Current boundary

The candidate output is **not an MT5 order**: this offline package has no authenticated MT5 order sender attached. Production's **older routers** still contain legacy-signal and handover requirements and remain unchanged. This package does not activate trading, prove profitability or remove any production services. Removing a hard-coded `execution_authorized=false` is a code change, not proof of a successful trade.

## Verify locally

```bash
python3 -m pytest -q
```

The tests cover the eight removals, as well as inherited APEX execution behavior and original broker/account risk controls. See `USER_REQUESTED_REMOVALS.md` for an audit checklist.
