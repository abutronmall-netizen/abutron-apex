# APEX — Verified Technical & Product Audit
**Timestamp:** 2026-10-31 16:23 UTC / 18:23 SAST
**Target:** abutron-ai, 144.126.232.85
**Status:** Inspection and recommendations; no order enablement or LIVE changes during this audit.
**Evidence:** local curl /apex/api/overview, /apex/api/chart, systemctl, git, service units, source inspection, MT5 snapshot, contract risk file.

## Verified working
- Existing SSH-loopback dashboard available at http://127.0.0.1:8888/apex/ (via user's Bitvise tunnel 127.0.0.1:18888); GET returns 200.
- Public-facing original AgenticTrading Lab retained at /app and /health, both HTTP 200.
- 13/13 Deriv DEMO synthetic symbols, six timeframes M1/M5/M15/H1/H4/D1; each snapshot contained 400 completed bars per timeframe at audit.
- MT5 broker candle snapshot refresh every ~5 minutes; <5 min age at 16:23 UTC.
- TradingAgents v0.7.1 original research graph with native Ollama Qwen2.5 1.5b instruct, fail-closed corporate reasoning gate and saved JSONL decisions.
- 3 completed recorded AI shadow decisions at checkpoint: V75 Hold, V100 Buy (rejected by display evidence gate), Crash150 REVIEW (rejected). Final action HOLD for all.
- Dashboard and API expose markets, candlestick snapshots, decision history, broker-risk estimates, service statuses; order execution false.
- Timer, dashboard, MT5 data service, local model and persistent remote management active; root-access remote management via @latest requires security review.

## Verified missing / not certified
- Zero APEX automatic broker orders, no protected trade open/manage/close lifecycle tested.
- Original EA31337 staged at 9b9bd38, x-particle at 7959c65; no compiled EA31337 .ex5 and no APEX EA attached to the Deriv terminal.
- No broker equity, margin, open positions, filled/closed trade journal or per-trade stop/fill/slippage reconciliation in APEX dashboard.
- 13 symbol research is sequential: one symbol per agent cycle. Full-symbol refresh in hours is unacceptable for M1/M5 execution.
- Market-data snapshots every 5 minutes; do not claim real-time tick, spread or fill information.
- Broker risk report is static; at 16:23 UTC ~6,100 seconds old (age ~1h42m). Its existing two-hour expiry makes fresh automated recalculation necessary.
- USD $10 is only a risk-reference value, not an enforceable account-wide realized+unrealized drawdown cap. Six minimum-lot/ATR-stop estimates already exceed $10.
- Several stock-oriented hallucinations persist in the TradingAgents research stages. The adapter calls propagate(..., asset_type='stock'); a substring blacklist on output is a temporary fail-closed gate, not a reliable evidence validator.
- No independent Deriv native tick-replay backtester, walk-forward dataset split, full cost/slippage model, calibrated confidence, or documented profitable forward results.
- Root-level Desktop Commander installed via npx @latest: pin versions, restrict management, secure credentials and audit changes before public/live operation.
- The original Lab's demo backtests/leaderboards are not Deriv forward trading performance.
- EA31337 is GPL-3.0; x-particle has no committed LICENSE file detected; do not distribute derivative x-particle code without rights verification.

## Priority P0: One actual DEMO trading engine (not another platform)
1. Build an independent pure-Python strategy module on completed Deriv broker candles/ticks; generate deterministic proposals for all 13 instruments every appropriate bar close. Separate Volatility and Crash/Boom instrument family strategy selection; reject unproven patterns.
2. Enforce per-symbol execution suitability and complete instrument specifications. Use MT5 native tick/bid/ask, correct volume_min/step/point/stops/freeze/market hours, order_calc_profit/margin and order_check. Limit aggregate USD at-risk under the existing $10 DEMO test-loss budget; account for existing open exposure and a risk buffer; no live trading.
3. Implement a fail-closed and idempotent DEMO-only order state machine: signal -> policy -> preview -> order_check -> SL/TP attached -> (controlled DEMO authorization) -> order_send -> broker retcode/deal ticket -> position updates -> closing -> history-deal reconciliation. Confirm server-side SL and explicit order and fill failure controls, duplicate prevention, restart/disconnect recovery and kill switch.
4. Keep TradingAgents as asynchronous human-readable advisor/veto. Replace stock asset semantics, factually ground synthetic-only prompts/tools, require schema-enforced structured outputs with timeframe, source timestamps, evidence IDs, buy/sell/hold, expiry, rejection reasons. Never let LLM directly bypass hard risk logic.
5. Establish test-only / shadow by default until independent DEMO lifecycle certification.

## Priority P1: Institutional-quality evidence and operations
- Build real Deriv backtests using broker-native historical candles/ticks and trading specifications. Prevent look-ahead, include spread, commissions/swaps, variable fills, slippage, stop gap scenarios, costs, execution rejection.
- Out-of-sample walk-forward, Monte Carlo trade order, drawdown and parameter perturbation, multiple trials correction; compare strategy to hold/naive baseline and benchmark per symbol.
- Performance view: equity curve, realized and unrealized P&L, profit factor, expectancy in USD and R, max drawdown, Sharpe with multiple-testing caveat, win/loss, fees, adverse excursion, per-symbol/strategy cohorts.
- Unified dashboard: account status (DEMO clearly), balance/equity/margin; positions and order lifecycle; fill reconciliation; strategy health, age per symbol/timeframe, reason codes, risk budgets and alerts. Currently not present.
- Data reliability and recovery: stale feed guard, durable broker tick/cache storage, snapshot hashes, backups with tested restore, alerts, watchdog, signed releases/rollback, resource limits and CPU latency metrics.
- Pin GitHub source commits, Python dependencies, Node/remote management versions; review root privileges and auth before any public deployment.

## Priority P2: Only after independent DEMO strategy evidence
- Per-symbol regime classifier, ATR/spike distribution with dedicated Crash/Boom and Volatility bots; SMC/ICT structure or ensemble only if its out-of-sample gains are demonstrated.
- Faster local inference or distillation only after comparing real execution-quality/decision results against baseline; avoid more paid APIs and infrastructure.
- Broker adapter abstraction for IC Markets / FP Markets; each broker's contract, execution and live features independently reviewed. No premature expansion.
- Alerts and companion command center; controlled human approvals, policy versioning, replayable evidence for every trade.

## Objective DEMO release gates
- Feed: all 13 supported symbols/timeframes reliable and recent, with reproducible source provenance; short TF needs bar/tick scheduling rather than one LLM decision per multi-minute cycle.
- AI: zero accepted corporate fundamental references on synthetic symbols, structured outputs validated, decisions stale-safe.
- Strategy: statistically defensible positive out-of-sample net expectancy and drawdown under realistic broker costs (currently UNKNOWN).
- Risk: actual cumulative USD DEMO budget enforced, broker-confirmed protective SL, per-symbol risk cannot exceed budget at minimum lot and worst-case stress; disconnected and retried orders fail closed.
- Execution: supervised protected DEMO order -> reconciliation -> close with no unexpected duplicates, restart recovery tested, independent approval before autonomous DEMO.
- LIVE: locked until separate authorization, certification and recovery evidence.

## Suggested source mapping
- tauricresearch/tradingagents: local multi-agent contextual research only.
- EA31337/EA31337: MQL5 native strategy/execution candidate, GPL obligations, must compile and pass broker-specific tests.
- marketcalls/Agentic-Trader: reference deterministic indicators, scheduling, per-instrument position controls; original NSE/OpenAlgo source not a direct Deriv bridge.
- kweinmeister/agentic-trading: reference independent AlphaBot -> RiskGuard approval pattern; do not require Google Cloud.
- hozaifa4you/x-particle: review native MT5 order request patterns; risk and licensing not approved for direct deployment.
- Open-Finance-Lab/AgenticTrading: preserved Lab/backtesting/UI concepts, avoid its US-stock demo leaderboard as broker proof.
- OpenByteInc/QuantDinger: previously rejected/decommissioned, no reintroduction.
- ctubio/Krypto-trading-bot: market-making for crypto exchanges, not appropriate as Deriv MT5 executor.

**Decision:** On this budget-limited VPS, priority is one provably safe, testable broker-native DEMO execution engine and a fast deterministic scanner, not more LLM subscriptions, servers, or visual features.
