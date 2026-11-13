# ABUTRON FX 6207 exact signal-to-order checkpoint — 2026-11-10 00:03 SAST
Scope: Deriv DEMO 6207 ONLY. No live orders or LIVE authorization.
Operator authorized completion of APEX signal-to-order and enablement, conditional on safety controls already agreed.

## New verified engineering
- Added root-owned installed read-only helper /usr/local/sbin/abutron-apex11-6207-exact-draft-ro
- SHA256 d4ae3ba7545c9e24ba72727afe610bffb4470141efb63ca60cfb92eff376b1ee
- Source QA in /var/lib/abutron-mcp/abutron-apex11-6207-exact-draft-ro.py
- 13 regression tests PASS: /var/lib/abutron-mcp/test_apex11_6207_exact_draft_ro.py
- New systemd oneshot and 30s timer abutron-apex11-6207-exact-draft-ro.* enabled; latest status Result=success, ExecMainStatus=0.
- Output /var/lib/abutron-apex11-6207/exact-order-draft-latest.json
- Consumes account-bound APEX 1.1 M5 SQLite journal plus authenticated broker worker bars and native per-symbol cost report; no manual MT5 deal becomes an APEX signal.
- Four fresh directional drafts generated for V10,V25,V50,V75; V100 HOLD emitted no order. Every draft has separate deterministic signal ID; MqlTradeRequest-shaped order fields (price reference, lot size, SL, TP, magic, side), conservative *estimated* risk not exceeding 0.085% account equity inclusive of 0.10 USD reserve.
- Quotes are ephemeral; proposals expire in 10s, never auto-dispatch; NO OrderSend, no CRM mutation, no native request file, no execution authority.
- No existing EA or native router replaced. No request queues changed.

## Verified persistent blockers, do not infer success
1. The original APEX shadow journal STILL has order=null. Derived order drafts are a separate enrichment, NOT a broker-native exact preflight. Broker-native OrderCalcProfit for that actual lot/stops, OrderCheck, fee/slippage and submission proof are pending.
2. CRM connection d6fc2524ec373b8d1bc278a8be3ec635 desired_enabled=1, effective_enabled=0, last_error=EXCLUSIVE_DEMO_CUTOVER_NOT_APPROVED; revision-matched active execution ACK absent.
3. Customer-wide native current exposure: six broker accounts independently flat, zero positions and pending orders, but certified true peak/daystart equity, full historical exit risk, daily-loss and 20% drawdown gates are INCOMPLETE. Do not bypass.
4. No new broker-acknowledged APEX 6207 trade or protected position receipt; two-broker native ACK audit confirms false.
5. Legacy native orders timer disabled. All LIVE account effective switches OFF.

## Required real completion
- Revalidate actual broker quote and lot with authenticated native Deriv MT5 OrderCalcProfit/OrderCalcMargin, real final entry/SL/TP, commission/slippage reserve and exact MqlTradeRequest OrderCheck. Never claim native verification from the research draft.
- Prove customer/owner daystart, peak and realized-loss drawdown with complete broker-native deal history and risk policy: 0.10% per trade, 2% aggregate, 3% daily, 20% peak drawdown.
- Authenticate CRM transaction/revision, customer entitlement, unique exclusive writer, independent OFF race and no retries.
- Only after all guards pass, DEMO-only root-approved intent through existing V4 contract, single OrderSend attempt, immutable broker ACK + native entry/SL/TP receipt and reconcile; manual deals distinguished by broker deal magic/provenance but included in aggregate risk.

## Rollback of this isolated read-only enhancement
sudo systemctl disable --now abutron-apex11-6207-exact-draft-ro.timer
sudo rm -f /etc/systemd/system/abutron-apex11-6207-exact-draft-ro.{timer,service}
sudo rm -f /usr/local/sbin/abutron-apex11-6207-exact-draft-ro
sudo systemctl daemon-reload
Optional stale report can be retained for evidence or deleted separately.
No passwords, private keys or broker credentials recorded.
