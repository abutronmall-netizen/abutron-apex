# Deriv 6207 native V4 EA upgrade: source handoff and acceptance

Verified 2026-11-08:
- Deriv 6207 worker installed V2 EX5 SHA256 ff4f353b09c7db996852972e5ad1caa63717337a2234b0fb7259515eede968bb, mtime 2026-11-07 11:19; **not verified chart-attached**.
- V213 source 542 lines SHA256 3113f190868ab27e309f57b7d7a35d136604fb7b0c01116a89696edb5ec209d7.
- Latest adaptive_bridge.mq5 source 681 lines in protected backup SHA256 dfc436a42d5210e93f51652e1ac95c65820a3b906cf2629808f9c93850998bc3.
- Self-hosted GitHub runner cannot read the protected source after root wildcard sudo was deliberately removed; owner-approved read-only run 42451758482 failed with PermissionError. **Never restore wildcard sudo to bypass this boundary.**

The root-authorized verified_source_handoff.sh script copies ONLY the exact hash-pinned native EA source into /var/lib/abutron-apex11-source-handoff/adaptive_bridge.mq5 (root-owned and group-readable only by abutrongha). It neither compiles nor modifies a running EA, service, account setting or trade.

V4 upgrade acceptance sequence:
1. Review source safely for embedded credentials before any private GitHub transfer.
2. Patch **the original adaptive EA** for a distinct 13-field ABUTRON_APEX_V4.req message containing explicit reserved lot, SL, TP, client activation revision, nonce, login, server, one signal key and expiry. No V3 rename or AUTO/STRUCTURE_M5 fallback.
3. Preserve all native broker protections: symbol, tick, stop geometry, risk cap, margin, OrderCalcProfit, OrderCheck, single OrderSend, UNKNOWN-on-ambiguous status, receipt+position reconciliation and crash-safe consumption.
4. Require an independently authenticated current CRM revision/kill-switch check **when the EA consumes the request and immediately before order submission**; mere writable local ON files are insufficient. OFF must fence outstanding requests before acknowledging completed OFF.
5. Compile in isolated MT5, validate compiler diagnostics and compiled EX5 hash. Back up installed original EA and chart configurations; do not touch production EA before successful source+binary/worker rollback preparation.
6. Verify attached EA identity, authenticated Deriv DEMO 6207 native session, production APEX M5 signal, independent 0.10%/2%/3%/20% policy, one broker-confirmed DEMO receipt with real SL/TP and position reconciliation, and client OFF fencing. No forced trade.
7. Leave LIVE OFF and old native dispatcher disabled until all gates pass.

**Milestone A production acceptance is NOT complete.** Source import and Python V4 writer tests alone are not native broker execution evidence.
