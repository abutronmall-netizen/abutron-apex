# Deriv 6207 native client ON/OFF authority — two-phase lease

**Status: source implementation + isolated native compilation and offline contract tests. NOT production-enabled.**

## Verified source and build

- MQL5 original adaptive execution source (November 7 recovered) remains the base; original `AdaptiveRiskProofV2.mqh` SHA256 `e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44`.
- New V4 EA compiles against that header under official signed MetaQuotes Windows MetaEditor. [QA run 42459146695](https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42459146695): **0 errors, 0 warnings, 2,232ms**, 84,414-byte compiled QA EX5 SHA256 `b5facc58d772f57d7ea95b027b71927bcd23e59de1432974d0c80712f4108491`. **Not installed**.
- GitHub APEX 1.1.0 source/offline integration test suites cover claim/send, concurrent claims, stale or wrong identities, unknown broker outcomes, client OFF before and after SEND, loopback authentication, broker-receipt consistency and reserved risk ledger finalization.

## Correct state semantics

1. **CLAIM**: EA consumes the unique 13-field V4 order request, verifies broker/account/login/nonce/DEMO, calls local guardian on `http://127.0.0.1:19743/v4/guard`, using a **per-worker 256-bit token provisioned outside GitHub**. The guardian cross-checks the exact owner-bound `UNKNOWN` risk reservation and independently authenticated MT5 + CRM evidence under `ActivationStore`'s SQLite `BEGIN IMMEDIATE` transaction. It persists `CLAIMED`. This is NOT order-send authority.
2. EA recomputes native lot step, tick, margin, OrderCalcProfit, OrderCheck, stop/freeze, risk policy, stores native pre-send intent/audit and again calls the guardian for **SEND**, binding the same signal, login, worker nonce, account revision, lot, SL, TP and expiry.
3. The guardian serializes `SEND` against the client OFF transaction and persists `SENDING` before it responds. Missing backend, URL not allowed, no token, expired request, revised CRM, stale broker authentication or duplicate/unknown pending outcome = **DENY; no OrderSend**.
4. If client requests OFF before the SEND transaction, it invalidates authorization and blocks OrderSend. If OFF occurs **after** SEND is committed, a broker send may still occur; **OFF must remain `STOPPING_BROKER_RECONCILIATION_REQUIRED`** until the original risk reservation and independent broker position/SL/TP are reconciled. Portal must never interpret just `effective_on=0` as broker-safe `OFF_SETTLED`.
5. The lease is never cleared automatically on timeout/crash/restart. Independent broker history/position evidence and matching original risk-ledger proof are required for `RESOLVED`. No duplicate automatic retry.

## Components

- `apex11/abutron_replacement/native_v4_off_fence.py`: serializable durable claim/send/off/reconcile transactions on the **same activation database file** as client switches.
- `native_v4_guardian_http.py`: strict loopback-only two-stage request parser and constant-time hash of per-worker secret; **no default runnable daemon or broker credentials**. This is NOT an internet API.
- `native_v4_broker_authority.py`: connects native guardian claims to the existing `VerifiedNativeSupervisor` broker/CRM/risk checks, source identity and independently authenticated protected broker receipt. Unverified 'no order' assertions are rejected.
- `risk_guard/reservation_store.py`: requires independently finalized original owner-bound broker proof before OFF settlement.
- `apex11/mql5/AbutronApexExistingDerivV4_6207.mq5`: two synchronous MQL5 `WebRequest` authorization calls. Native V4 input remains **OFF**. V2/V3 writer remains hard-disabled in candidate.

## Production gate — mandatory before any DEMO activation

- Deploy an authenticated **real** `VerifiedNativeSupervisor` bound to the existing Deriv 6207 native broker/session and CRM entitlement store (not fake booleans). Instantiate `Verified6207NativeAuthority` in a least-privileged, supervisor-owned local service with protected DB and per-worker secret. The source currently declares the interfaces only; no executable production process/CRM adapter has been verified.
- The portal must call the **same** `ActivationStore` account revision transactions, and display `off_state`: `STOPPING` until all native leases are independently reconciled, `OFF_SETTLED` only thereafter. Otherwise historical portal OFF behavior is still unsafe. Need actual V7/CRM API integration tests.
- MetaTrader's Expert Advisors settings must explicitly allow the trusted local URL. MetaQuotes documents that `WebRequest` is unavailable to Strategy Tester; verify in a separate **DEMO chart**, not with fabricated simulator broker receipts. The root guardian token must be generated at deploy time, never stored in source or GitHub logs. Isolate workers against localhost impersonation and token exposure.
- The native V4 EA **does not yet publish the 10-line native capability status** expected by `NativeV4FilePort._capability`. Do not bypass that check. Add an independently verified signed/native status mechanism before hooking the production exclusive writer.
- Verify the exact *running* 6207 chart EA, versioned fresh offsite backup and rollback of terminal EA/profile, independent broker reconciliation, no unknown orders, and then **one fresh qualified Deriv 6207 DEMO** order with real broker order/deal/position IDs and protective SL/TP. Test OFF immediately before and during SEND. LIVE always OFF.

## Safety guarantees and limitations

These components are a robust **code-level** fix for the stale-ON race, **not** a claim of end-to-end live operating correctness. Root/local service and native broker supervisor must be authenticated and independently verified. A loopback worker token is not protection from an already-compromised worker; production threat modeling and service confinement are required. There is no LIVE route, no unlimited sudo access, no root production deployment or broker orders in these GitHub source changes.

[MetaQuotes WebRequest documentation](https://www.mql5.com/en/docs/network/webrequest)
