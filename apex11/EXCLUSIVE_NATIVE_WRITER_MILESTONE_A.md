# Milestone A — exclusive APEX 1.1.0 native writer transaction

Status: **source integration implemented; production MT5 adapter NOT installed, and broker acceptance NOT yet completed**. LIVE forbidden. No production service switched.

## Existing contracts reused

- APEX account-bound M5 decision journal, not old scanner/TradingAgents/Qlib/Qwen.
- Transactional owner-bound activation state: desired ON + effective ON + matched 15s worker ACK revision, kill switch OFF.
- Independent, freshly authenticated Deriv-Demo account ending 6207 and EA native proof, owner/nonce/CRM entitlement.
- Customer-wide risk inventory and durable account/customer baselines; ReservationStore for **0.10% trade / 2% open exposure / 3% daily stop / 20% peak drawdown** plus broker OrderCalcProfit/OrderCheck and native stop geometry.
- The **exact same root lock path** used by the legacy dispatcher: /var/lib/apex-client-feed/execution-router/execution-writer.lock.
- Durable UNKNOWN risk ledger before any native request writes, never retry on uncertain result; independent broker receipt and protected-position reconciliation before finalizing reservation.

## Critical production-native compatibility finding

Owner's 2026-11-08 05:18 UTC read-only production code inspection verifies:

- Legacy order request file: APEX_NATIVE_ORDER_V1.req in the native EA's ABUTRON file directory.
- Receipt directory: receipts
- Global flock file: /var/lib/apex-client-feed/execution-router/execution-writer.lock.
- Existing V3 adaptive request uses 12 newline fields:
  APEX_NATIVE_ADAPTIVE_ORDER_V3, nonce, canonical signal key, MT5 login,
  broker server, symbol, BUY/SELL, AUTO, 0.10, STRUCTURE_M5, expiry UTC,
  SEND_DEMO_ONLY.
- **V3 does NOT carry activation revision or a native EA acknowledgment of
  that revision.** A switch may go OFF after Python writes but before
  the MT5 EA consumes the file. Python rechecking the database is insufficient
  for atomic account OFF fencing. We therefore require a **verified, installed
  revision-fenced V4 EA/adapter**, not a fake V4 boolean or rewritten timestamp.

## Delivered in this change

- exclusive_native_writer.py: account-bound APEX publication hash validation,
  6207-only DEMO, native writer lock, fresh native identity, native EA revision
  fence capability, recheck of OFF/entitlement/native worker before submission,
  0.10/2/3/20 risk reserve, durable UNKNOWN before the broker request,
  no duplicate resend, independent broker receipt/stop verification. No
  legacy scanner imports.
- test_exclusive_native_writer.py: mock-only concurrent lock contention,
  duplicated signal, account OFF, stale worker, wrong account, V3 denial,
  native queue error, order/position reconciliation and stop requirements.

## Remaining required production steps (fail closed)

1. Obtain reviewed MQL5 source and native broker protocol for the actual
   installed Deriv DEMO execution EA (not merely the read-only sidecar).
   Upgrade/verify native input parser, EA capability heartbeat and broker receipt
   to bind account activation revision and reject old requests after OFF.
2. Wire a **root-owned supervisor** with broker-authenticated account session
   and independently fetched native position/deal information, atomic
   customer risk inventory and CRM/entitlement revisions. Do not let HTTP
   callers provide supervisor boolean fields.
3. Provision correct production activation/reservation SQLite databases and
   a real NativeEARequestPort that checks nonce, path, EA readiness,
   native request/receipt existence, and writes *exactly once*. The current
   library adapter protocol is not the production transport.
4. Run independent on-host tests from a versioned rollback staging directory,
   verify the existing lock and no active/uncertain orders, validate
   real account 6207 DEMO, full offsite backup and restore, obtain a genuinely
   qualified fresh closed M5 APEX signal, then a broker-confirmed protected
   DEMO order, with independent receipt/ledger reconciliation.
5. Keep native legacy order timer disabled and old competing signal path
   unauthorized until an actual exclusive-writer cutover is verified.
   Do not bypass broker stop/risk checks or turn on LIVE.

Mock unit tests passing cannot certify Step 1–4 or claim full Milestone A.
