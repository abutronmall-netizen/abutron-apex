# Audit record: the eight requested removals

**Scope:** Local staging source only. No production system changes are represented.

1. **200 outcomes:** deleted `minimum_observations` input, check, and approval logic from `abutron_replacement/cost_validation.py`.
2. **14 days:** deleted `minimum_days` input, check, and approval logic from the same file.
3. **Positive confidence gate:** deleted bootstrap lower-bound, multiple-comparison threshold and promotion outcome. The evaluator reports net mean/median and the limitations of historical estimated costs, without vetoing trading candidates.
4. **300-bar minimum:** `AbutronApex11SignalBridge` defaults to `warmup_bars=0`, never forces 300; config `abutron_signal_only.yaml` also uses 0. Agent-specific historical lookbacks remain what APEX 1.1.0 itself requires to compute a meaningful indicator.
5. **100-second expiry:** deleted `max_signal_age_sec` and age-based candidate denial. Time must still refer to a completed M5 candle and not lie in the future; no maximum age is added.
6. **Uninterrupted M5:** candle gaps no longer refuse the entire signal feed. Bridge resets an affected symbol's indicators on a gap. The archive reader returns actual recorded candles across gaps, and the research evaluator skips only hypothetical trades that would span unavailable prices.
7. **Extra handover approval:** deleted field and blocker from candidate review; production's old routers retain it because the server has **not** been modified.
8. **Permanent false execution authorization:** deleted that hard-coded field from bridge, candidate, archive, compatible-identity and clock-diagnostic outputs. A review that passes the user's existing account/broker/risk checks now outputs a populated `order_candidate`. Actual order transmission still needs an integrated native MT5 dispatcher; no real order path exists in the offline package.

**Not changed:** broker safety/risk/identity checks; 0.10% per-trade risk; 20% portfolio ceiling; client ON/OFF; stop/take-profit geometry; native order and position reconciliation; existing production server and services.

**Important distinctions:** Data-contract test success is not broker execution success. A model's historical average return is not proof of future profit.
