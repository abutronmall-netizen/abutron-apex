# ABUTRON APEX 1.1.0 — source import audit (2026-11-08)

## Source identity
- Source: user-supplied `ABUTRON_APEX11_CLEAN_STAGING_20261108(1).zip` (server original name `ABUTRON_APEX11_CLEAN_STAGING_20261108.zip`).
- Verified SHA-256: `98f1074c28786bc7f982a9a1a175b492718824449dd301c8e8c2b7b3e016c056`.
- ZIP integrity test: passed; 100 original ZIP entries.
- Source imported: **97 text files**, under `apex11/`. The two PNG documentation images are excluded; no runtime databases, broker credentials, or generated state have been committed.
- Local isolated test result for this exact archive: **108 tests passed** on 2026-11-08 (48 APEX, 12 bridge, 26 hardening, 13 production contracts, 9 requested gate removals).
- The original `apex11/CHECKSUMS_SHA256.txt` verifies **98 included files**, but it also references **two absent generated runtime files**: `state/abutron_apex11_memory.json` and `state/decisions.jsonl`. These were intentionally not recreated or imported; thus the complete original manifest has two unsatisfied entries. All 98 source-file digest checks matched locally.
- Security review: reviewed paths and scanned text for common private key, API-token, password, GitHub credential, AWS and Google key patterns; **no matching actual credential strings were found**. This is not a guarantee that every sensitive reference was detected. No `.env`, private key, SQLite database, or live account config appears in this ZIP.

## Important non-deployment facts
This import is an **offline, non-executing snapshot**, not the production MT5 code:
- No native MT5 order submission or order receipt is present in the imported replacement package.
- Production's existing Deriv router still uses old scanner/TradingAgents candidate requirements; FP currently has stale/unverified native data.
- Broker-native currency conversion, stop geometry, costs, account ON/OFF revision fencing, single-writer ownership and ledger proofs still require production integration.
- The separate `risk_guard/` layer defines **0.10%** entry risk, **2%** aggregate open-stop risk (account and each customer's Deriv/FP portfolio), **3%** daily loss stop, and **20%** drawdown lockout.
- The imported `apex11/config/abutron_signal_only.yaml` STILL has older paper-simulation settings (`max_daily_loss_pct: 0.02`, `max_drawdown_pct: 0.08`) and its existing candidate-review helper still accepts a 20% nominal open-risk ceiling. These are **not equivalent to the approved production risk policy**. They have NOT been silently changed, and an integration test must confirm the *external* native guard is the sole admission authority and effective policy values are aligned. Do not publish an executable order candidate from this code alone.
- The user removed additional 200-outcome, 14-day, statistical-confidence, forced-300-bar, fixed 100-second signal-age and handover approval requirements from the offline engine. Do not reintroduce these as strategy-vetoes. Broker/session freshness, identity, risk and actual order reconciliation remain mandatory technical safety checks.

## Release/permission boundary
This review branch is not production-installed. No user switch, risk configuration, LIVE trading, network route, service or runtime database has been changed. Before deployment: production backup + restore test, full source/hash comparison, current service inventory, isolated dependency checks, broker-native risk validation and controlled DEMO 6207 order/position/ledger proof. Independent account ON/OFF must remain authoritative.

## After review
1. Prove replacement APEX M5 decision publication with independently authenticated broker feeds.
2. Implement a checked candidate-to-risk-guard-to-native MT5 writer adapter with durable reservation reconciliation; do not grant order authority just from a successful offline test.
3. Fix FP broker clock and worker matching at source; do not guess offset.
4. Verify actual Deriv DEMO 6207 receipt, native stops and close-deal reconciliation before expanding to customer DEMO accounts.
5. Only after that, retire obsolete decision services without disturbing backups, customer controls or reconciler services.

## Post-import review changes (not in the original archive)

- `apex11/apex/risk/limits.py`: numerically tolerant comparison in correlation clustering to avoid NumPy-version-dependent rounding at the exact 0.85 shrinkage boundary. This file intentionally differs from the uploaded source archive and its historical manifest SHA. The archive's original contents and verified archive SHA remain documented above.
- `apex11/abutron_replacement/native_risk_preflight.py`: NEW **offline-only** joint APEX candidate identity + per-account/per-customer 0.10/2/3/20 risk reservation preflight, with no MT5 transport, no switch modifications and no broker order authorization.
- `apex11/tests/test_native_risk_preflight.py`: 11 additional offline cross-component tests (119 APEX tests total if CI passes); `risk_guard/` retains 47 isolated tests.
- The compatibility adapter deliberately keeps existing native account, entitlement, broker-order-check, single-writer and stop/reconciliation checks. It rejects old 20% nominal open-risk allowance when the newer 2% aggregate risk limit is reached; 20% remains a distinct peak-equity drawdown lock.
- The production risk authority, authentic broker OrderCalcProfit/OrderCheck provenance, durable equity baseline, order writer integration and LIVE/DEMO switch are NOT implemented by this source import.
