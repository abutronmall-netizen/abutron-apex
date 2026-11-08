# ABUTRON APEX 1.1.0 — dual-layer DEMO risk guard

**Status: isolated implementation + local unit tests only. NOT installed on localhost, NOT broker-certified, DOES NOT activate trading.** No live order execution code is included.

## Approved policy
- **0.10%** maximum *loss estimate* per new entry, relative to that account's fresh broker equity.
- **2%** maximum aggregate estimated open-stop risk **for each account AND each customer's combined Deriv/FP portfolio**, including unresolved pre-order reservations.
- **3%** daily UTC equity-loss stop **per account AND customer portfolio**, relative to durable UTC-day baseline. Persistent lock after threshold breach; no automatic resumption on rebound.
- **20%** peak-to-current equity drawdown lock **per account AND customer portfolio**, relative to persistent high-water mark. Manual review and authorized reset required; no silent auto-reset.
- **Customer isolation:** no sharing equity/risk budgets among customers. LIVE remains disabled.

## Behavior
`evaluate()` requires authenticated reconciled broker positions, native stop verification, native one-lot stop-risk quote, verified FX conversion for portfolio aggregation, fresh broker timestamps, account ON/entitlement, valid stop and instrument constraints. It returns `ALLOW_DEMO_PREORDER_ONLY` with a broker-volume-step-rounded volume; it never submits an order.

All position risk must include positions opened manually or by other systems. Unknown or unprotected positions block new entries. Broker stop execution can slip beyond the estimated exposure; no guaranteed monetary cap exists.

`reservation_store.py` adds a SQLite idempotent reservation state. All account writer instances for the customer MUST share this DB file, or substitute a transactionally consistent central DB. A signal can be reserved once per account; a transport timeout stays `UNKNOWN` and reserves risk until authenticated broker reconciliation. Do not finalize a reservation merely because a local process reports success.

## Integration requirements before deployment
1. Confirm the current APEX native publisher/writer architecture and permissions on `localhost`; review/restore-test encrypted offsite backup first.
2. Map native MT5 `order_calc_profit()` for 1 lot at entry-to-stop into account-currency loss; separately obtain commissions/slippage stress, lot min/max/step, stop-level validity, margin and tradability. Broker timestamps must be fresh.
3. Read all accounts owned by the customer; reconcile *every* broker position including manual, unknown and pending orders; convert risk and equity into USD using verified contemporaneous rates. Existing open risk must include protected losses and costs; absence of SL must cause rejection.
4. Persist high-water marks, UTC day baselines, customer/account stop latches and account status revisions in durable transactional state. **The code persists risk lockouts through `reservation_store.py`, but intentionally does not implement durable baseline creation or manual reset.** Fail closed if these are missing or unverified. A high-water mark cannot be reset when processes restart or customers reconnect. Daily equity baselines and peaks must account for verified deposits, withdrawals and FX conversion effects so external cash flows are not misclassified as trade losses.
5. Bind `reserve()` immediately before native submission within a single-writer workflow; prevent duplicate submit across restarts. Immediately before sending, refresh broker/state data, entitlement and ON/OFF revision. Enforce independent MT5 ownership locks.
6. After authentic broker acknowledgement reconcile order/position IDs, native SL/TP and open risk. Only then mark intent `RECONCILED` and release the pending reservation. The `complete(account_id, signal_id, ...)` call needs a verified broker receipt reference; `RECONCILED` additionally requires a broker exposure snapshot already containing the new position. A rejection can be finalized only against verified broker response; ambiguous state must remain reserved.
7. Call `ReservationStore.observe()` on each authenticated broker equity refresh, even if no entry signal is present. The reservation store persists daily/drawdown lockouts transactionally; it has no automatic unlock. The external production state service must also persist correct UTC day baselines, peak equity, cashflow adjustments and authorized reset audits. Close or hedge existing positions only under an independently reviewed policy; switching OFF only blocks *new* entries and must not remove existing protection.
8. Test failure scenarios across process restarts, concurrent accounts, stale data, disconnected broker and client OFF; complete controlled Deriv 6207 DEMO receipt/reconciliation before FP expansion. LIVE remains disabled.

## Deployment blocker
This package is **not a production adapter**. The actual APEX publisher, MT5 writer, authentication, UTC baseline/high-water source, signed customer ON/OFF revisions, subscription entitlements, native SL/TP receipt verification, broker timestamps and restoration-tested backups have not been integrated or tested here. It is unsafe to assume these tests authorize production execution.

## Run local tests
```
cd risk_guard
python3 -m unittest discover -s tests -v
```

**Important:** These tests use invented DEMO fixtures solely for unit testing. They do not establish expected trading profitability, valid broker contract specifications, broker execution, or deployability into the unknown production codebase.
