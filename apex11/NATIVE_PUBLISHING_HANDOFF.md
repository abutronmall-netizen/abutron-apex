# Milestone A — native-feed publication & broker-receipt consistency (8 November 2026)

**Scope: source-only; SHADOW ONLY. Zero native orders submitted. No change to localhost.**

## Delivered

- `abutron_replacement/account_bound_publisher.py`: DEMO-only, account-bound read-only APEX BUY/SELL/HOLD/M5 decision journal. Refuses unverified supervisor binding; freshness and account/broker checks; 0600 SQLite journal; per-account per-closed-bar deduplication persistent across restarts; immutable last-candle/manifest decisions; no broker writer.
- `abutron_replacement/native_receipt_guard.py`: independent contract to validate a privileged MT5 worker's claimed **fully filled** DEMO receipt, matching order/deal/position ID, volume, side, account, symbol, broker server, native SL and TP, inclusion in reconciled exposure, snapshot chronology, and no pending or ambiguous remainder. Does not authenticate broker data itself. `trusted_native_worker_verified` defaults to false. Does not place orders.
- Mock-only regression tests, including account isolation, stale feed, unchanged candle despite unrelated native file checksum rollover, hard rejection of changed candle, duplicate publication after restart, partial/pending MT5 receipts and missing protective stops.

## Critical limitations

1. `BrokerBoundBars.broker_authenticated_by_this_code` is **false** even for a successfully parsed native snapshot. Parser and filename alone cannot independently verify the real broker; a privileged production supervisor must attest and bind user, account, worker UID, broker login, nonce, source permissions and current session before calling the publisher. Do not expose `supervisor_attested` over HTTP.
2. No native authenticated order sender was available in the supplied APEX ZIP. No code here acquires a production lease or writes `.req` order commands. `broker_order_authorized=False`, `orders_submitted=0` always.
3. `NativeOrderReceipt` and `NativePositionProof` are **contract objects only**, not actual MT5 responses. A trusted native worker must create them from independently fetched broker facts. A boolean flag is not proof by itself.
4. A broker receipt and an open protected position must be reconciled into the customer's authoritative exposure before releasing pending order risk. Verify outstanding or ambiguous orders through the broker independently; do not retry after timeout.
5. Deriv account ending 6207 has not completed a broker-confirmed APEX DEMO trade. FP native broker-clock-offset and data completeness remain unverified, and the complete platform Milestones B/C are not certified.
6. Existing old router still requires scanner/TradingAgents dependencies. Do not pass the journal output to the old router as executable authority. Do not disable legacy services until exclusive new writer is verified.
7. APEX signal agents stamp nested `ts` fields with wall clock during replay. The journal normalizes nested timestamps to the actual closed M5 bar time for deterministic audit/idempotency. This is not a change to APEX decision logic.

## Required production integration work (separate, authorized stage)

- Verify complete offsite encrypted backup and isolated restore; capture current `localhost` running service entrypoints, hashes and privileged MT5 writer ownership.
- Obtain authenticated, fresh real worker/account snapshots (Deriv 6207 first), verified instrument specs, broker `OrderCalcProfit` and `OrderCheck`, equity day/peak and protected-position exposure; do not infer from filenames alone.
- Bind actual client entitlement, license, desired/effective revision and existing native writer lease. Use the approved 0.10% per trade, 2% aggregate open stop-risk, 3% daily stop and 20% persistent drawdown lock, with the client's ON/OFF authoritative.
- Acquire exclusive native order-writer ownership, then submit only fresh qualified DEMO orders when protective stops and all transactional checks are proven. No forced signal or synthetic broker proof.
- Independently reconcile actual order, deal, positions, native stops/TP and customer ledger. Verify failover/unknown outcome and account OFF. Only then close Milestone A.
- FP Markets and remaining accounts are subsequent Milestone B. CRM/billing/Prop Firm/AB Markets, backup restoration and security are Milestone C. LIVE remains disabled.

## Run isolated tests

From repo root:

```bash
cd apex11
PYTHONPATH="..:../risk_guard:tests" python -m pytest -q -p no:cacheprovider tests ../risk_guard/tests
```

## Production evidence update: 2026-11-08 04:48:58 UTC

Owner-authorized read-only localhost audit executed via the separate ABUTRON Ops
fixed self-hosted GitHub workflow run:
https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42448305328

- Deriv DEMO: 3 connected accounts; requested ON=3, effective ON=0.
  Deriv 6207 client worker connected, while isolated broker read-only sidecar
  remains BROKER_PROOF_STALE and failed. This is not a certified MT5 receipt.
- FP Markets DEMO: 6 accounts, requested ON=1, effective ON=0. FP target
  worker connected but the read-only native history collector is failed;
  source metadata is fresh but native quote time stale during weekend.
- One Deriv LIVE account row exists with desired ON=0, effective ON=0;
  **LIVE must remain OFF**.
- Existing APEX native order timer remains inactive. Legacy TradingAgents /
  quant dispatcher timer is still active, so exclusive order-writer handoff
  has not been demonstrated.
- Platform portal, signup and V7 API services are running, not certified
  customer/billing functionality. Most recent backup-log mtime does NOT
  prove a verified offsite restore or rollback.
- Security: GitHub runner principal still has unrestricted NOPASSWD sudo;
  restrict to audited staging/deploy commands before unattended production use.
- The FP broker-server-time correction and fail-closed weekend history checks
  were delivered and CI-tested in PR #8, merged into this feature branch.
  See FP_NATIVE_HISTORY_CLOCK_RECOVERY.md. They were not deployed.

These facts supersede older claims of account requested switches being OFF.
Passing source CI is not an MT5 deployment or Milestone A/B/C acceptance.
