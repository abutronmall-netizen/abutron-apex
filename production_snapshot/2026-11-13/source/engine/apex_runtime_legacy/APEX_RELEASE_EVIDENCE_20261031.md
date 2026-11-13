# APEX FX — Verified Engineering Release Checkpoint
**Date:** 2026-10-31, 16:58 UTC (18:58 SAST)
**Server:** `abutron-ai` (144.126.232.85), Ubuntu
**Owner directive:** Build from supplied original GitHub projects. No QuantDinger revival, paid LLM API keys or added VPS.
**Scope:** Automated broker-data processing, research proposals, AI review, risk supervision and protected-order validation. **Orders remain DISABLED** pending independent certification.

## Confirmed running (verified systemctl)
- Original Open-Finance-Lab AgenticTrading Lab retained; served together with new APEX operator dashboard, loopback 127.0.0.1:8888, Bitvise tunnel localhost:18888.
- `apex-mt5-market.timer`: authenticated Deriv USD DEMO OHLCV collection, 13 symbols × M1/M5/M15/H1/H4/D1, five-minute snapshots; market file /var/lib/apex/mt5-market/deriv_demo_bars.json.
- `apex-mt5-account.timer`: account, equity, margin, open positions and last 30 days' broker deals from official MT5 Python, no account login/password exported.
- `apex-mt5-risk.timer`: official `order_calc_profit` minimum-lot USD loss estimates; 13 results, existing 2× H1 ATR assumption.
- `apex-fast-scanner.timer`: deterministic 13-symbol MTF completed-candle scanner, no external feeds, experimental EMA/RSI model. Crash/Boom trend proposals fail closed awaiting dedicated spike model.
- `apex-risk-governor.timer`: separate account-wide hypothetical USD reference limits (cumulative $10, single $3), fail-closed, root policy DEMO orders=false and LIVE=false, current kill=LOCKED.
- `apex-mt5-precheck.timer`: 26 official MT5 order_check() calls (BUY/SELL per 13 instruments) with protective SL/TP, NO `order_send`. At audit, 22/26 broker prechecks returned retcode 0, 4 blocked by simulated $3 buffered single-order test reference; this does not certify actual fills or stop execution.
- `apex-execution-preview.timer`: durable SQLite signal-intent ledger with unique keys, transaction isolation and retry/restart tests. No order-send implementation in current running service. An uncertain state freezes further attempts.
- `apex-broker-warehouse.timer`: durable SQLite archive of original completed candles across all 13 instruments and six timeframes, initial 31,200 broker bars, duplicate-ingest idempotence, conflicting historical revisions flagged.
- `apex-broker-agents.timer`: original tauricresearch/tradingagents v0.7.1 multiagent graph, connected to local Qwen2.5 via native Ollama, broker-only tool adapter and output-rejection gate. Multi-minute latency; not time-critical entry engine.
- `apex-remote-commander.service`: persistent remote operation (ROOT privileges, security-reduction task pending).

## Verified dashboard URLs
- **APEX operator:** http://127.0.0.1:18888/apex/ via user's Bitvise SSH tunnel.
- **Original Lab:** http://127.0.0.1:18888/app
- Routes tested: /apex/api/overview, /apex/api/broker, /apex/api/scanner, /apex/api/risk-governor, /apex/api/order-prechecks, /apex/api/execution-preview, /apex/api/chart, /health; HTTP 200 on tests. Server binds only to 127.0.0.1:8888.
- UI screens: Overview, Markets, AI Decisions, Strategy Scanner, Account & Trades, Execution Checks, System & Risk.
- Broker account at checkpoint: Deriv USD DEMO; balance/equity each USD 9,777.82, zero open positions. This is the account's history, NOT a profit statement for APEX.

## Test evidence observed in console
- Fast scanner: 8/8 categories passed, 13 symbols × six timeframes, nonbroker/stale/NaN/duplicate rejected.
- Risk governor: 9/9 categories passed, LIVE account, stale account, unexpected unlock, unprotected position, exhausted loss reference all blocked.
- Execution intent ledger: 7/7 categories passed, duplicate intent prevention, restart persistence, unknown-order state freeze.
- Broker warehouse: 6/6 categories passed, 31,200 completed candles ingested, duplicate replay idempotent, changes flagged.
- Broker order prechecks: 22 accepted / 26 evaluated; 4 blocked by own buffered USD reference, zero orders sent.
- All newly enabled timer units returned active on latest service check.
- APEX dashboard and original Lab HTTP endpoints verified 200.
- Transient root-owned test JSON debug copies were removed from /var/tmp after tests.

## Critical unresolved blockers — do NOT count as complete
1. **No certified broker execution:** zero actual APEX orders submitted. No tested open->protected stop->fill->close->broker reconciliation. Compiler/source candidate EA31337 staged but no .ex5 compiled or attached to MT5; x-particle not deployed (license not established).
2. **Loss enforcement not certified:** $10 and $3 figures are risk-estimate references, not guaranteed broker-execution caps. Stop-fill slippage may exceed models. Daily accounting presently excludes some opening-side commissions and does not conservatively accumulate gross negative deal cashflows; proposed accounting repair DID NOT DEPLOY due blocked write. Governor remains LOCKED and execution must not be enabled.
3. **Strategy edge unproven:** EMA/RSI proposals experimental, no valid out-of-sample net expectancy / drawdown certification. Warehouse initial 400 completed bars per timeframe (~33 hours M5) and must accumulate or backfill more history before robust tests.
4. **AI domain mismatch:** upstream graph still calls `asset_type='stock'`; some model reports hallucinate equity fundamentals. Output blacklist rejects obvious cases, but not a complete semantic control.
5. **Security:** persistent Remote Desktop Commander runs as root via unpinned npx latest, and upstream Lab's development auth settings are not production-hardened. Keep dashboard SSH-loopback only. No public deployment.
6. **No independently verified offsite restore, incident response, reproducible release promotion or autonomous LIVE approval. LIVE stays LOCKED.**

## Next exact engineering action
- Fix broker cashflow ledger to include entry-side commission and sum gross negative deal cashflows for true conservative test budget accounting; retest on official Deriv DEMO and preserve rollback.
- Build and independently review protective DEMO order sender with broker-native stop acceptance, atomic attempt lock, aggregate account loss, fill/close reconciliation and crash recovery before enabling any `order_send`. No LIVE.
- Accumulate/backfill real broker history and validate a profitable out-of-sample strategy, independent from LLM market commentary.

## Paths / rollback
- Fast scanner `/opt/apex/runtime/apex_fast_scanner.py`, output `/var/lib/apex/scanner/latest.json`.
- Broker account `/opt/apex/runtime/apex_mt5_account_export.py`, `apex_mt5_account_store.py`, output `/var/lib/apex/mt5-market/deriv_demo_account.json`.
- Independent governor `/opt/apex/runtime/apex_risk_governor.py`, root-owned policy `/etc/apex/trading-policy.json` (DEMO false, LIVE false).
- MT5 precheck `/opt/apex/runtime/apex_mt5_order_precheck.py`, output `/var/lib/apex/mt5-market/order_precheck_latest.json`.
- Execution preview `/opt/apex/runtime/apex_execution_preview.py`, SQLite `/var/lib/apex/execution/intent_ledger.sqlite`, current `latest.json`.
- Warehouse `/opt/apex/runtime/apex_broker_warehouse.py`, SQLite `/var/lib/apex/warehouse/deriv_broker_candles.sqlite`.
- UI `/opt/apex/runtime/apex_ui/` with timestamped .backup files; upstream original apps unmodified.
- Stop new non-trading features if rollback necessary: `systemctl disable --now apex-fast-scanner.timer apex-mt5-account.timer apex-mt5-risk.timer apex-mt5-precheck.timer apex-risk-governor.timer apex-execution-preview.timer apex-broker-warehouse.timer`. This leaves the original broker-data and original research timers alone.
- Original market exporter preserved backup: `/opt/apex/runtime/apex_mt5_snapshot.sh.backup-20261031-before-shared-lock`.
- Do not delete broker history, SQLite journals, account files, EA source or original projects without verified backups.
