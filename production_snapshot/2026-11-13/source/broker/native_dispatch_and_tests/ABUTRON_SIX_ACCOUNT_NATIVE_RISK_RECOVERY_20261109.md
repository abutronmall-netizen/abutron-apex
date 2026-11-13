# ABUTRON FX APEX six linked account native risk/reconciliation recovery
Verified production 2026-11-09 20:46+00:00 / 22:46 SAST, Ubuntu localhost.
Scope: 6 CRM-linked, CRM CONNECTED broker accounts. No live orders or client ON/OFF modified.

## Accounts
- Deriv DEMO 32456207 (owner abutroncloud), 0 open/0 pending, equity 9577.61 USD
- FP Markets DEMO 7410512 (same owner), 0 open/0 pending, equity 99023.85 USD
- Deriv LIVE 10380178 (same owner), 0 open/0 pending, equity 0 USD, broker trade_allowed false, LIVE OFF
- Deriv DEMO 6357593 (Daylon), 0 open/0 pending, equity 9712.11 USD
- Deriv DEMO 202699244 (Jean-Carter), 0 open/0 pending, equity 9879.23 USD
- FP Markets DEMO 7411636 (Jean-Carter), 0 open/0 pending, equity 100000.00 USD

## Verified current exposure reconciliation
Patched root-owned read-only collector /usr/local/sbin/abutron-customer-wide-risk-readonly.
- Now consumes independent FP dual-account broker receipt/equity/position report for both DEMO FP accounts; rejects stale source, unmatched owner/connection, mismatched balance, unknown receipts.
- Uses three independent Deriv DEMO dual-native broker sources and signed Deriv LIVE no-order source.
- Distinguishes zero CURRENT open-position stop-risk from unverified historical drawdown, new execution broker ACK, and executable new-entry quote costs.
- 6/6 independently verified flat, 0 pending, $0 USD open stop-risk, 0 unknown position sets.
- True daily equity day-start and intraday peak NOT certified. Full customer-wide risk NOT certified.

## Verified 90-day/native selected export window
Installed /usr/local/sbin/abutron-six-broker-native-history-reconcile
Timer abutron-six-broker-native-history-reconcile.timer enabled / active, every 2 minutes.
Report /var/lib/abutron-v4-broker-crm-supervisor-6207/six-broker-native-history-reconciliation.json.
- Deriv 6207: 152 native trade deals, 76 closed position IDs paired, net trade cashflow -422.39 USD.
- Deriv 7593: 112 deals, 56 paired positions, net -287.89 USD.
- Deriv 9244: 96 deals, 48 paired positions, net -120.77 USD.
- FP 0512: 100 native deals (98 trades/2 funding), 49 paired positions, funding cashflow 100050.00 USD, net trading cashflow -1026.15 USD, current balance exactly 99023.85 USD. 46 historical broker ACKs, zero unknown receipts.
- FP 1636: 1 native funding deal 100000 USD, 0 trade deals, exact current balance 100000 USD.
- Total 229 historically matched position IDs across DEMO accounts. All five DEMO selected-window proofs PASS.
- Deriv LIVE 0178 history is unverified, no historical broker deposit/exit ledger; LIVE permission OFF.
- This does NOT attest all-time account history, unobserved past equity high-water, or any new execution broker ACK.

## FP periodic source race fixed
Patched read-only /usr/local/sbin/abutron-fp-dual-native-reconcile-ro to retry complete independent broker proofs at most 3 times, delays 2+5 seconds, without using stale saved ACKs.
Exposes allowlisted uppercase error code after persistent failure; remains BLOCKED if no fresh native evidence.
Positive and negative retry tests PASS. Separate native fp trade order router unchanged.

## Forward equity observations
Installed /usr/local/sbin/abutron-six-account-native-equity-observer, timer enabled / active each minute.
DB /var/lib/abutron-v4-broker-crm-supervisor-6207/six-account-observed-equity.sqlite3
Report /var/lib/abutron-v4-broker-crm-supervisor-6207/six-account-observed-equity.json
Stores time-bucketed six-account signed broker equity/balance snapshots by owner and account, with observed sample high-water and missing-gap markers; 6/6 flat proof required before logging. Does not falsely mark true daily daystart/intraminute peak as certified. DB integrity PASS.

## Final tests / production state
Risk tests 5 PASS; 90d ledger tests 8 PASS; bounded FP retry tests 2 PASS; equity observer tests 5 PASS; total 20 new regression tests PASS.
Services abutron-deriv-three-native-reconcile-ro, abutron-fp-dual-native-reconcile-ro, abutron-customer-wide-risk-readonly, abutron-six-broker-native-history-reconcile, abutron-six-account-native-equity-observer all Result=success, ExecMainStatus=0.
Five related timers ACTIVE; CRM DB quick_check ok; equity observation DB quick_check ok (at verification 24 account samples / 4 minute buckets).
All six accounts effective_enabled=0. No orders sent, no trading control enabled by this work.

## Outstanding production blockers
1. True broker-native day-start and intraday peak equity, full prior-day/peak drawdown, cashflow-adjusted across all accounts cannot be recovered from unrecorded observations.
2. Deriv 90d selected-window trade deals reconciled, but full account-lifetime (all-time) broker exit/deposit ledger is NOT verified.
3. Deriv LIVE 0178 is $0 balance and broker trading permission false; keep LIVE OFF.
4. No new revision-matched CRM EXECUTION ACK or independent new broker order ACK. Historical FP broker receipts are historical, NOT a new order ACK.
5. Exact executable instrument OrderCheck + commission/slippage costs for a fresh new order and fresh APEX trading signal remain unverified. Do not bypass.

## Backups
Prior rollback code:
  /var/backups/abutron-six-account-risk-reconcile-before-20261109T2023Z/
CRM backup from prior deletion:
  /var/backups/abutron-fp-five-links-removal-20261109T2011Z/accounts-after.sqlite3
Original read-only customer-wide collector / FP dual reconciliation wrapper and original unit saved. Other native broker/EA programs unchanged.
Rollback: replace read-only collector and FP wrapper from backup using root-owned/0750 atomic copy; systemctl restart oneshot timers only if appropriate; disable/remove new six-broker history and equity-observer timers if necessary. Do not alter CRM activation or broker configuration.

No credentials, tokens, or private account secrets included in this checkpoint.
