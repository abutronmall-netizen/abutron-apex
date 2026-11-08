# ABUTRON APEX — Milestone A integration boundary

**Status:** source-only, isolated offline integration. **Not deployed**, not approved for broker order execution.

## Implemented in this branch
- Imported APEX 1.1.0 codebase from draft source PR #2.
- Included unchanged risk policy/evaluator/reservation store/tests from draft risk PR #1.
- New `abutron_replacement/native_risk_preflight.py`: binds an APEX directional candidate to tenant, DEMO broker account, verified native instrument risk quote and a transactionally reserved order intent; emits **no MT5 order**.
- New `abutron_replacement/transactional_activation.py`: isolated DEMO-only owner-bound ON/OFF state with optimistic revisions, effective-state ACK fencing, worker ACK expiration (15 seconds), explicit entitlement/connection/writer/kill-switch status, durable SQLite state and account separation.
- Tests exercise activation, duplicate reservations, risk limits and candidate binding. These are **simulated fixtures**, not real broker receipts.

## Known integration blockers
1. **Actual APEX publisher:** connect to authenticated closed M5 bar snapshots from each production native worker. Current APEX accepts a data contract but is not connected to live worker APIs or app service ownership.
2. **Broker-native writer:** replace old scanner-dependent exclusive MT5 order runtime with APEX-specific native order writer. Source/runtime of production MT5 workers, privileged order transport and broker credentials are **not in this repository**. Do not construct unauthenticated transport or assume existing service permissions.
3. **Broker receipt and ledger:** trace broker transaction IDs, native SL/TP, account balances, positions, closes and unknown orders; persist/reconcile before releasing reservations.
4. **Account activation adapter:** connect isolated revision DB to authenticated CRM owner/entitlement, portal switches and worker attestation. Booleans in the library are claims supplied by trusted adapters and **must not be accepted as proof without worker signature and writer lease**.
5. **Live risk baselines:** the risk module currently lacks the production cashflow-adjusted account/customer high-water mark and UTC day baseline service. Admission MUST fail closed without those verifications.
6. **Market data FP:** FP Markets clock-offset and incomplete native exports have not been resolved. No FP order activation.
7. **Legacy retirement:** scanner/TradingAgents/Qlib/Qwen/other production services still require actual service ownership tracing. Do not disable without audited replacement ownership.
8. **Platform C:** CRM, billing, Prop Firm, AB Markets, backups/restoration and security cannot be accepted from the standalone trading-engine repo.

## Safety policy
- DEMO only. LIVE never enabled.
- 0.10% maximum new-entry risk, 2% account+customer aggregate protected open-stop risk, 3% daily equity-loss stop, 20% persistent peak drawdown lock.
- Client account OFF overrides all automation. Kill switch retains protective stops.
- No forced trades; no new performance gates beyond user-directed APEX architecture and native correctness/risk constraints.
- No migration, service restart, broker order, change in effective customer ON, payment or server modification is performed by this branch.

## First production acceptance test
After verified encrypted offsite backup, isolated restore and rollback plan: acquire authenticated 6207 DEMO feed, verify client ON, publish a fresh APEX M5 signal, obtain exclusive native writer lease, reserve risk, submit **only an appropriately qualified** DEMO order, capture broker receipt, verify native protective stops and reconcile authenticated broker ledger. Without this evidence Milestone A is **BLOCKED**.

## Run locally
From repository root:

```bash
cd apex11
PYTHONPATH="..:../risk_guard:tests" python -m pytest -q -p no:cacheprovider tests ../risk_guard/tests
```
