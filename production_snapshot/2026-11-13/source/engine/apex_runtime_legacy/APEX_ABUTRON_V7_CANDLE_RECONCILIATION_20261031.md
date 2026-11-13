# APEX ↔ ABUTRON V7 Deriv V75 Candle Comparison — Verified Release
**Date:** 2026-10-31 approximately 17:29 UTC / 19:29 SAST.
**Systems:** APEX on `abutron-ai` (144.126.232.85); Abutron V7 separately on `localhost` recovery host.
**Owner's symptom:** Screenshot showed APEX M5 SELL/HOLD vs V7 M5 BUY on same Volatility 75. APEX had mislabeled indicator trend as the candle BUY/SELL method.

## Root cause verified
- APEX is connected to Deriv MT5 USD DEMO, symbol `Volatility 75 Index.0`, exporting official *completed* MT5 bars with candle **opening** timestamps via copy_rates_from_pos(...,1,...).
- Abutron V7 uses Deriv public Options WebSocket candles `R_75`, *not* MT5 customer account; API explicitly filters `epoch + granularity <= now-1` and outputs `candle_closed_utc=epoch+period`.
- **The V7 candle timestamps were correct**, contrary to an initial screenshot suspicion. Do not claim V7 displayed incomplete candles.
- At 2026-10-31 17:15:00 UTC M5 close: V7 public Options screenshot open 40331.9936 close 40398.3264, BUY. APEX official MT5 data for M5 17:10–17:15 open 40331.99 close 40398.33, also BUY. Prices agree to MT5 display precision. They were being compared using different method/snapshot times.
- APEX scanner `M5 Signal` had meant a **multi-bar EMA9/EMA21+RSI trend**, which can be bearish after one bullish closed candle. This is not a broker feed discrepancy. Clear naming and same-candle alignment were necessary.

## Changes on APEX, completed and verified
1. `apex-mt5-extra-frames.timer` plus read-only `apex_mt5_extra_candles.py` and `apex_mt5_extra_candle_store.py` now fetch and validate 13 symbols × M3/M30 official completed candles every five minutes; no extra API key or paid vendor. Original M1/M5/M15/H1/H4/D1 strategy and historical data unchanged.
2. `apex_ui/candle_compare.py` validates both broker snapshots and returns 8 timeframes M1/M3/M5/M15/M30/H1/H4/D1 with candle_open_utc, candle_closed_utc, open, close, exact single-bar BUY/SELL/NEUTRAL bias, and EMA9/21+RSI trend from the **same snapshot** on six existing periods. M3/M30 trend explicitly UNAVAILABLE until adequate multi-bar history exists; not fabricated.
3. `/apex/api/candle-comparison?symbol=Volatility%2075%20Index.0` read-only API: 8 rows, all confirmed complete, no order execution. Invalid/untrusted symbol rejected; stale/nonbroker source fails closed.
4. APEX Strategy Scanner now has a distinct **M5 candle** column vs **M5 EMA/RSI trend**, **M5 EMA/RSI direction** and **Strategy Gate**. 13/13 M5 candle biases are matched to the actual scanner candle timestamp even when scanner/market feed refresh at different times.
5. Added **Candle Comparison** navigation view with clear source provenance, eight timeframe rows, actual close UTC and side-by-side M5 bias/trend.
6. Added direct deep link:
   `http://127.0.0.1:18888/apex/?view=compare&symbol=Volatility%2075%20Index.0`
   via existing Bitvise SSH tunnel to server 127.0.0.1:8888.
7. Preserved original GitHub AgenticTrading Lab at `/app`; verified HTTP200 before and after.
8. Confirmed APEX UI, assets, /apex/api/overview, /apex/api/scanner, /apex/api/candle-comparison, /health, /app all HTTP 200; six checked services/timers active; browser JS syntax checked.
9. Both DEMO and LIVE broker orders remain disabled, governor kill switch LOCKED. No orders placed.
10. Timestamped rollback backups retained adjacent to modified UI modules and application entry points.

## Latest test after deployment
At broker completed M5 candle close **2026-10-31 17:20 UTC**, APEX V75 candle bias BUY, EMA/RSI trend MIXED, correctly displayed as **different metrics**. May change on next completed candle.
V7 original source unchanged, verified installed V7 backend SHA256 equals staging source. No changes to V7 production, credentials, trading or logins.

## Remaining limits
- This view computes a V7-**style** one-bar bias from MT5. It does NOT fetch authenticated V7 dashboard output live or imply that APEX source is V7's public Options source.
- M3/M30 trend unavailable by design until 60+ broker history bars per timeframe; only closed-candle bias is shown.
- No certified profitable strategy or broker order lifecycles; controlled DEMO and LIVE remain locked.
- Historical independent Abutron V7 production and APEX separate; do not conflate them in future.
