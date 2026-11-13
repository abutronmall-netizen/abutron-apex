# APEX Multi-Symbol DEMO v3 — Verified checkpoint (2026-10-31 21:50 UTC)

## Production-like DEMO controller
- Host: abutron-ai, 144.126.232.85
- Primary controller: /opt/apex/runtime/apex_demo_auto_v3.py
- Gate: /opt/apex/runtime/apex_multi_gate_v3.py
- Ledger reconciliation and independent reservation: /opt/apex/runtime/apex_multi_core_v3.py
- Per-symbol broker USD planner: /opt/apex/runtime/apex_multi_usd_planner_v3.py
- Root staging: /opt/apex/runtime/apex_demo_feed_stage.py
- Policy: /etc/apex/trading-policy.json
- Profile: /opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json
- Service/timer: apex-demo-auto-v3.service / apex-demo-auto-v3.timer enabled and active
- Old v2 timer: disabled and inactive
- Live trading: disabled; Deriv USD DEMO only
- Capacity: max 13 concurrent positions, one position per symbol, no account-wide USD loss cap
- Broker-native per-symbol gross USD SL/TP; one-attempt ledger; broker margin check
- Existing V75 position 8815685138 was preserved by migration
- Crash/Boom strategy signals remain HOLD until spike-model certification. No forced orders.
- Legacy research governor is separate, not the v3 execution controller.

## Verified tests
- 21 isolated unit/failure/restart/permission tests PASS, 0 broker submissions.
- 26/26 real Deriv MT5 official order_check requests accepted for 13 symbols (BUY+SELL); NO order_send during tests.
- systemd --preflight start/restart twice with existing position, ledger reconciliation PASS and 0 orders sent.
- SQLite unique partial index apex_one_open_attempt_per_symbol_v3 installed and verified.
- After v3 timer enable, repeated completed cycles status SCANNING, no new qualified entry.
- Dashboard HTTP 200, API controller_version=multi_v3, timer_active=true, stale=false, risk_cap_usd=null, max_concurrent_positions=13, open_apex_positions=1, confirmed historical APEX entries=4, unreconciled_attempts=0.
- Ledger: 3 CLOSED, 1 OPEN_PROTECTED; no multi-position simultaneous LIVE/DEMO fill proof yet.
- Existing APEX v2 code preserved.
- Rollback checkpoint directory: /var/lib/apex/demo-execution/v3-checkpoints/20261031T214712Z (includes consistent SQLite backup).
- The v3 service should be disabled before rollback, and the v2 owner policy and code restored from checkpoint in a controlled procedure.

## Still to certify
- Two or more simultaneous independently broker-filled symbols.
- Multi-symbol close reconciliation under real concurrent stop/target events.
- Crash/Boom spike-model entries and safe exit proofs.
- Slippage, swap and commissions may change net realized USD versus gross SL/TP.

Do not claim independent LIVE trading certification.
