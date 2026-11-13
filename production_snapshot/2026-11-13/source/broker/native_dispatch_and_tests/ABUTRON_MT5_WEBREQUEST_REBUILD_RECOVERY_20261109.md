# ABUTRON Deriv DEMO 6207 MT5 WebRequest / risk evidence checkpoint
Verification date: 2026-11-09 (UTC). Host: localhost. Scope: one account, DEMO only.

## Verified repairs
1. Backed up worker and WebRequest recovery helper before any runtime changes.
2. Restarted only the 6207 transient worker, causing full old terminal retirement and fresh profile creation.
3. New and previous independent portable profiles had DISTINCT nonces, identical SHA-256 V4 executable
   0581985fdd90b14349468889880cd3b7b4cba83405be8fc874dc6947e37162fe,
   account 32456207, Deriv-Demo, DEMO, and native MT5 HTTP 200-derived V4 STATUS capability.
4. Installed /usr/local/sbin/abutron-mt5-webrequest-rebuild-attest-6207 and
   abutron-6207-webrequest-rebuild-attest.service/timer (every two minutes, read only).
   Generated /var/lib/abutron-v4-broker-crm-supervisor-6207/mt5-webrequest-rebuild-attestation.json.
   State: PASS_REBUILT_PROFILE_NATIVE_HTTP200, zero blockers.
5. Replaced V4 read-only supervisor hard-coded chart/WebRequest false gate with independent evidence
   checks. Verified webrequest_rebuild=True, v4_chart_attached=True, V4 capability=True.
6. Added read-only CRM STATUS ACK comparison: 6207 session V4 native revision 69 equals
   current CRM monotonic revision. This is NOT a CRM execution ACK or broker order ACK.
7. Repaired quote archive's stale assumption that a V4 chart must have order input OFF.
   Read-only execution controls still deny all orders. Self-test passed.
   Archive resumed; observed 333475 authenticated MT5 sampled quotes and 610 new rows,
   four historical native entry-only fills, zero new orders.

## Verified safety / outstanding blockers
- No trading orders dispatched by repair. DEMO worker connected, native quotation active.
- Client requested ON but effective execution OFF; activation revision ACK remains unapproved.
- Independent BROKER SESSION evidence true; independent BROKER EXECUTION ACK still false.
- Customer-wide risk certification BLOCKED: 11 linked accounts, 6 connected, 3 owner groups.
  Missing complete account/day-start/peak equity and full exit ledger; disconnected exposure unknown;
  FP quote freshness, LIVE USD stop-risk and per-position OrderCalcProfit not certified.
- Five Deriv synthetic instruments have native OrderCalcProfit, OrderCalcMargin and bid/ask snapshots.
  Exact-order OrderCheck, historical commission and realized slippage remain uncertified.
- Quant M5 signal and V2/V4 exclusive writer/unknown orders still unverified.
- Never replace missing actual broker ACK, historical costs or risk reconciliation with local flags.

## Tests
- Controlled MT5 worker-profile rebuild and broker-native HTTP STATUS succeeded.
- Attestation two profiles, SHA and nonce constraints: PASS.
- Legacy supervisor six negative/positive tests: PASS.
- Broker-native quote archive self-test: PASS.
- V4 broker/CRM inspector run: PASS; execution authorization false.

## Backups (root-only)
- /var/backups/abutron-6207-webrequest-rebuild-attest-20261109T1948Z
- /var/backups/abutron-v4-inspector-webrequest-chart-20261109T1955Z
- /var/backups/abutron-v4-crm-status-readonly-ack-20261109T2000Z
- /var/backups/abutron-native-quote-cost-chart-gate-20261109T1958Z

## Rollback
- Restore corresponding backed-up supervisor script and quote collector script using sudo install
  preserving executable mode and root ownership.
- systemctl stop/disable abutron-6207-webrequest-rebuild-attest.timer to remove only the new monitor;
  remove its unit files and daemon-reload if rollback is required.
- No change to the compiled V4 EX5, live-trading controls, broker credentials, guardian claims,
  real order router, or other customers' worker configurations.
