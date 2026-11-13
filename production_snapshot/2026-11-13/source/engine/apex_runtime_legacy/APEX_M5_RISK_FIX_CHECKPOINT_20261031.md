# APEX M5 Primary & Legacy Budget Removal — Verified
**Date:** 2026-10-31 17:11:55 UTC / 19:11:55 SAST
**Host:** abutron-ai (144.126.232.85)
**Environment:** Deriv USD DEMO, no broker orders enabled

## User-identified defects corrected
1. Scanner UI omitted M5 trend while listing M15/H1/H4. Added M1, **M5**, **M5 Signal**, M15, H1, H4, D1, RSI M5. M5 is first-class; explicit research signal separated from HTF entry filter.
2. Misleading generic HOLD reason replaced with exact M5 RSI-range, alignment, conflict, mixed-momentum or Crash/Boom model rationale. Scanner backup `apex_fast_scanner.py.backup-20261031-before-M5-diagnostics`.
3. Original TradingAgents shadow technical direction previously computed from M15/H1/H4 alone. Now uses M5 EMA9/21 plus RSI direction as the primary technical signal, with higher-TF context and AI agreement separate. No execution authorization. Backup `apex_broker_agent.py.backup-20261031-before-M5-primary`.
4. Removed legacy arbitrary $10 aggregate/$3 single-dollar thresholds from root policy, risk governor, MT5 order_check precheck, contract-risk probe, TradingAgents reporting, and HTML/JS risk display. Backups `*.backup-risk-settings-20261031T...`. Root policy `/etc/apex/trading-policy.json` now has `risk_per_trade_pct:null` and `max_daily_loss_pct:null` pending explicit user settings; LIVE and DEMO execution false.
5. Broker USD stop-loss estimates retained for transparency, no hardcoded 10/3 selection. 26/26 protected-order MT5 order_check calls accepted after removal; ZERO orders sent. Broker order prechecks are not actual fill/stop certification.

## Live validation evidence
- `http://127.0.0.1:8888/apex/` (via Bitvise `http://127.0.0.1:18888/apex/`) HTTP200; original Lab `/app` still HTTP200.
- HTML shows all six timeframe columns, including M5 Signal. No $10/$3 literals in served HTML.
- Scanner real data at 17:11:55 UTC: 13 symbols; 10 BUY directional M5 signals, 3 SELL, 0 HOLD. This distribution changes as market candles change and is **not** evidence of profitability/real orders.
- Independent risk governor output: `risk_parameters_configured:false`, `risk_budget_reference_usd:null`, `max_single_order_reference_usd:null`, `kill_switch:LOCKED`.
- Real MT5 order prechecks: 26/26 accepted for inspection, ZERO orders.
- Root risk policy LIVE and DEMO false.
- Dynamic percentage-policy regression: 12/12 categories passed (null settings, simulated percent sizing, LIVE/DEMO locks, stale account and scanner, open unprotected position, balance loss reference, incomplete broker history, commission-data uncertainty). Demonstration 0.5%/2% values were **NOT saved**.
- Original TradingAgents M5 integration passed 13x78 candle preflight; isolated model-disabled test for Volatility 50 M5 BUY, HTF BUY, final shadow HOLD due model disabled, no execution.
- All checked timers active: fast scanner, broker agents, market feed, MT5 risk, MT5 precheck, risk governor, remote management. All checked once-pass unit results success.

## Pending critical blockers
- User must explicitly choose account-specific risk-per-trade and max-daily-loss percentages; DO NOT silently choose default.
- Broker deal fees/loss accounting remains commission-incomplete. Risk governor correctly flags `COST_COMPLETE_ACCOUNTING_UNCERTIFIED`.
- M5 research signals are experimental and not proven net profitable; MTF entry filter still rejects unconfirmed signals.
- No APEX orders submitted, no protected DEMO order->fill->close/reconcile lifecycle certified; LIVE remains locked. Do not mistake 26/26 order_check for fills.
- Crash/Boom spike-specific model still needs validation.
- Remote management systemd uses root; security hardening pending.

**Next impact:** commission-complete deal ledger; broker-native verified protected DEMO execution lifecycle and walk-forward proof; then user-approved percent risk configuration, supervised DEMO release. No added paid API keys or VPS.
