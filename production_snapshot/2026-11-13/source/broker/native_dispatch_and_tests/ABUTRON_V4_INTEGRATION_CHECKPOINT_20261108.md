# ABUTRON V4 — Integration checkpoint (2026-11-08, localhost)

Scope: Deriv DEMO 6207, APEX 1.1.0, V4 Guardian QA, FP Markets portfolio risk. LIVE trading prohibited.

## Verified production state
- V7 API active; root-owned read-only V4 broker/CRM supervisor timer active.
- Native-order dispatch timer inactive; Deriv 6207 desired=1, effective=0.
- V7/APEX owner identity verified, V7 legacy claim PAUSED / INELIGIBLE.
- All six original V4 production admission gates remain BLOCKED.
- No trading orders, EA attachment, fabricated broker receipts, or bypass of client OFF.

## Workstream 1 — CRM revision
- Source: /var/lib/abutron-mcp/abutron-v4-crm-revision-6207.py
- Consumption guard: /var/lib/abutron-mcp/abutron-v4-crm-consume-6207.py
- Verified SQLite online prechange backup: /root/abutron-v4-crm-revision-20261108/apex-crm-prechange.sqlite3
- Five atomic SQLite triggers tested on a restored database clone.
- Clone tests PASS: OFF/ON revision increment; simulated matching ACK; stale-revision rejection; ABA rejection; concurrent OFF critical-section behavior; missing ledger fails closed; rollback when unused and refusal after mutation.
- Production migration tool call blocked before execution. Production ledger table is ABSENT. Simulated ACK is not actual broker certification.

## Workstream 2 — Native V4 release
- Source Git blob 9e3a9487f6931554f79f4a2596ebf3460004f81a matches staging.
- Candidate EX5 SHA256 458afad273cb5c2446f52d766d2617cc277bca6b1e990450bb6955c2da64973a.
- MetaEditor QA log 0 errors and 0 warnings. Eleven static QA/source checks passed.
- Source OnTimer invokes HandleV4Request, not the legacy handler.
- Production installed EA remains V2 SHA256 ff4f353b09c7db996852972e5ad1caa63717337a2234b0fb7259515eede968bb.
- V4 release remains QA_ONLY_UNAPPROVED, NOT installed, NOT chart-attached; no authenticated V4 capability.

## Workstream 3 — Portfolio risk and reconciliation
- Observer: /var/lib/abutron-mcp/abutron-v4-portfolio-risk-observer-6207.py
- One Deriv and one FP Markets DEMO account currently connected for this customer.
- Deriv native account snapshot: equity USD 9577.61, native positions 0.
- FP Markets 0512 snapshot: equity USD 99083.66, six open positions, zero pending orders.
- Six FP stops have valid entry-stop geometry, but GBPUSD.r and USDJPY.r snapshot prices cross SL. Native history window ~44.7h stale; this is a reconciliation warning, NOT a confirmed stop failure.
- Customer-wide broker OrderCalcProfit exposure, full cashflow-adjusted daily and peak equity, independently authenticated broker order/exit lifecycle, and current FP history are NOT certified.
- Risk: 0.10% per trade, 2% aggregate, 3% daily loss, 20% cashflow-adjusted peak drawdown.

## Backups / QA
- Verified complete host Restic snapshot b7915019.
- Supervisor encrypted offsite snapshots 6a9e91d8 and a40367f0.
- Staged CRM/risk sources and isolated clone backup in encrypted Restic snapshot ce849f42; remote source SHA256 readback verified.
- APEX/V4 184 isolated tests passed. Separate revision migration, rollback and consume-time clone tests passed.

## Unresolved production dependencies
1. Approved transactional CRM revision migration and authentic broker ACK plus immediate OFF fence.
2. Certified compiled V4 release, correct DEMO chart/worker identity, root guardian and protected V2-to-V4 writer handover.
3. Fresh FP + Deriv customer-wide risk, day-start/peak equity and native protective order/reconciliation evidence.

Never claim LIVE or DEMO order authorization based only on QA fixtures, historical broker snapshots, or monitoring reports.
