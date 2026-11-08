# ABUTRON — Production milestones verified 8 November 2026

Source status is not production acceptance. Never infer a broker order from CI, connected MT5 or green services.

## Verified completed

- GitHub main commit 1776a1dabfc538a69ced9cea9f53443cbb46b2bb contains audited APEX 1.1.0 source, 0.10% DEMO risk library, transactional activation contracts, shadow M5 publisher, native receipt-consistency guard and FP time normalization helper. Offline source/integration CI passed. Prior main preserved as backup/main-before-apex11-source-20261108. No live production writer integration demonstrated.
- Fresh encrypted offsite backup completed 2026-11-08 04:57:59 UTC: FULL_BACKUP_END_SUCCESS, RESTIC_REPO_METADATA_CHECK_PASS, V7_DATABASE_REMOTE_DUMP_READBACK_PASS. Evidence: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42448631845. Isolated full restoration not certified.
- FP native collector's server-time/UTC comparison patched atomically at 2026-11-08 04:59:42 UTC. New SHA256 2e093fd1cd8d6a33419f805ab4337735097685109ee06d9578b4c3d765ce3f8f; local rollback /var/backups/abutron-fp-native-history-clock-prechange-20261108T045942Z/fp_native_history_collect.py. No broker order, account flags or service restart. Evidence: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42448973032. Weekend quotes remain genuinely stale and must block new execution.
- Deriv DEMO 6207 isolated read-only sidecar recovered after guarded one-time restart. At 2026-11-08 05:06:39 UTC it was active/running, with fresh authenticated read-only broker proof (identity and native history verified; 601 native tick rows, 152 deal exports, 0 current errors). Evidence: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42449456426. This is not an APEX broker execution receipt.
- Runner wildcard root permission removed 2026-11-08 05:11:30 UTC; fixed root-owned staging-only verifier sudo preserved; visudo full parse passed, rollback copy retained. Evidence: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42449781376. Privileged temporary workflows removed.

## Last verified account and code state

- 2026-11-08 04:48:58 UTC production read-only audit: Deriv DEMO 3 accounts, requested ON 3, effective ON 0. FP DEMO 6 accounts, requested ON 1, effective ON 0. Deriv LIVE 1 account, desired/effective OFF. Portal, signup, V7 API services running only (functional acceptance not proven). Evidence: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42448305328.
- Root native order dispatcher still uses old apex_signal_native_router_v1 importing apex_fast_scanner and abutron_selective_tradingagents_v1. It writes risk_governor_approved=True as a literal, and nominal $52 per-position / 20% current equity check is not a 20% durable peak drawdown. New APEX 1.1.0 dual-layer risk and publisher NOT wired to native writer.
- APEX order timer disabled in 05:06:39 UTC read-only audit; old quant dispatch timer still active in 04:48 audit. Do not enable competing writers, touch stale legacy promotion timestamp or reset consumed 6207 pilot.
- Original APEX source staging exists in nested /opt/abutron-apex11-staging directories. This does not prove current GitHub merged modules were installed there or activated. Source inventory: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42449637920.

## Acceptance still outstanding

### Milestone A — Deriv DEMO 6207 (BLOCKED)

Verify source hashes and new broker-authenticated closed M5 publisher, exclusive existing native MT5 writer lease, real CRM owner/entitlements and desired/effective switch revision, full 0.10%-per-trade / 2%-portfolio / 3%-daily / 20%-cashflow-adjusted-peak drawdown guard, OrderCalcProfit/OrderCheck, stop/TP and unknown-order locking. Then observe a genuinely qualified fresh APEX signal; execute only permitted DEMO; reconcile actual broker order/deal/position IDs, stops and ledger, and test account OFF / restart. No forced trade or simulated broker proof.

### Milestone B — Deriv and FP Markets DEMO (PARTIAL, BLOCKED)

Requires A first. Recheck FP genuine fresh quotes after market opens, complete M5 export, session/offset, per-account exclusive writer and aggregate customer risk, broker-native costs/stops, authenticated protected DEMO receipt/reconciliation. Expand Deriv accounts independently. Never enable LIVE.

### Milestone C — portal, billing, Prop Firm, AB Markets, security (PARTIAL, BLOCKED)

Authenticate portal/account controls and audit log, CRM MFA/trials/entitlements, payments sandbox without real charges, real broker P/L, Prop Firm and AB Markets flows, isolated offsite restore and rollback, TLS/firewall/secret isolation. Retire legacy only when new owner and broker lifecycle verified.

**As of this checkpoint no Milestone A/B/C has a complete acceptance packet; all LIVE execution remains OFF.**

## Milestone A source integration update — 2026-11-08

- PR #9 merged into GitHub main: commit 12f4eee0f4150dd44a0272f4d7e358bf1800f423. This is the **source-level** exclusive APEX 1.1.0 native writer orchestrator, not a real broker cutover.
- New exclusive_native_writer.py holds the exact legacy root writer flock, uses account-bound APEX M5 publication + effective CRM revision + independently attested Deriv 6207 DEMO native facts; reserves 0.10%/2%/3%/20% risk in serialized SQLite; marks UNKNOWN before any native queue; checks owner, persisted reserved lots and fresh protected broker position before reconciliation. Duplicate key or unknown outcome cannot resend.
- New native_v4_file_port.py proposes a separate 13-field, revision-fenced V4 protocol with explicit reserved lot and SL/TP prices and a V4-only new request filename ABUTRON_APEX_V4.req; fsynced atomic link create, 0600 native-worker ownership, nonce/EA heartbeat and V3/duplicate hard refusal. It deliberately does not write old APEX_NATIVE_ORDER_V1.req.
- Both GitHub source-integrity/offline integration CI workflows passed on PR #9 head 2c80826c87b03a53ce9d8670a0356b7eefdaca2b; GitHub source tests are **not native broker receipt proof**.
- On-host read-only EA source scan: https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42450988773 identified historical V3 source /opt/apex/native-order-bridge-v3/AbutronApexNativeOrderBridgeV3.mq5 (legacy request filename present), but no verified source/installed compiled EA with *new* V4 revision-fenced parser. The current native MT5 execution EA is only confirmed for V3. Need a reviewed V4 MQL5 EA upgrade/compiled binary and broker-authenticating supervisor adapter before any source integration can be activated. Existing V3 protocol does not carry client ON/OFF revision, so using it would risk firing an already queued command after client OFF.
- Milestone A **NOT accepted**: no trusted V4 EA deployed or proven, no authenticated broker-confirmed APEX 1.1.0 DEMO trade, no effective client activation. Do not start legacy native orders timer or enable LIVE.

## Native Deriv V4 EA source recovery and fail-closed patch (2026-11-08)

- Owner's exact 681-line November 7 adaptive_bridge.mq5 backed-up source SHA256 dfc436a42d5210e93f51652e1ac95c65820a3b906cf2629808f9c93850998bc3 independently verified through non-root GitHub Ops read-only run 42452227059, after a root-owned group-limited source-only handoff.
- PR #11 source-only merged into GitHub main commit fe73a3ddb14130616cc626213af3b1223353fbf6. It adds an original-adaptive-EA-derived V4 MQL5 candidate, disables V2/V3 order consumption and legacy capability authorizations, enforces 13-field account-bound V4 explicit lot/SL/TP request parsing, broker tick/stop/margin/profit/OrderCheck and unique consume-before-send audit. Python V4 port corrected to CRLF lines matching MQL5 FILE_TXT and covered by offline regressions.
- Source integrity and integrated offline CI runs 42453018431 and 42453018412 passed. No native EX5 compile, terminal deployment, account changes or broker order.
- The EA's new V4RevisionAuthorized is hard fail-closed pending independent root-owned CRM activation revision/lease/off acknowledgment supervisor; no fake readiness marker may be written. The source requires the original AdaptiveRiskProofV2.mqh include; exact backed-up header/source provenance and isolated MetaEditor compile are not yet established. Production Deriv 6207 installed V2 EX5 SHA256 ff4f353b09c7db996852972e5ad1caa63717337a2234b0fb7259515eede968bb is untouched. LAST VERIFIED effective DEMO execution=0, LIVE OFF.
- Next action: locate the exact original AdaptiveRiskProofV2.mqh from /root/abutron_optionc_cutover, protected backups or terminal, stage and verify it without broadening runner sudo; then compile in isolated Wine MetaEditor QA environment, add the trusted guardian, validate protected actual DEMO broker order and client OFF fence, never forced trade.


## Deriv 6207 original OptionC header and QA compiler evidence (2026-11-08)

- OWNER root confirmed three byte-identical recovered AdaptiveRiskProofV2.mqh files, SHA256 e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44. This locates the missing original include; it has NOT been compiled together with V4 yet.
- Restricted nonroot Ops audit 42453738931 confirmed none of the three backup header paths is readable by abutrongha; Wine9, Wine path tools, xvfb-run and root-owned MetaEditor64.exe present. Original files stay protected. A SHA-pinned, group-limited source-only handoff script was merged in PR #12, commit 91d2070f78969596661c7dd8ceb9d9d6f3bdb832, both offline CI passed; owner must run the protected copy. No sudo widened.
- A separate harmless standalone MQL5 compiler smoke in a fresh nonroot Wine prefix timed out, MetaEditor exit 124, no compiler log or EX5 (Ops 42453815714). Read-only sanitized diagnostics 42454043726 show Wine9 warning about wine32, MetaEditor64 PE32+ x86-64, and no retained temp QA output. All three template MetaEditor64 binaries identical SHA256 c7b82be1a4329817591c1ce315f97b94976fe90e7280fb643948876ac5e87e5b (Ops 42454117407). Xvfb GUI audit 42454219351 observed a single MetaEditor64.exe window, still no compiler log. **The actual Wine hang cause is NOT verified**; no packages installed or production terminal touched. Do not declare source compilation successful or prescribe wine32:i386 without dependency proof.
- Private Ops owner-triggered deriv6207-v4-isolated-compile-once.yml is staged, with exact source Git blob b2ba33416105e5719b740d164be8cd45561b80f9 and expected header SHA. Its release is pending header handoff and working isolated QA compiler; it cannot authorize trading.
- No trusted root-owned CRM activation revision/in-flight lease native supervisor exists; V4 EA remains source-only with V4RevisionAuthorized hard-false. Deriv 6207 native deployed EX5 unchanged; LIVE off. Milestone A not accepted.


## Deriv 6207 native V4 QA compilation completed, artifact preserved (2026-11-08 06:39 UTC)

- Owner independently provided exact original MQL5 include SHA256 e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44, now restricted-group readable; exact V4 source Git blob 319c68d825b235ffaaa1eb2b7bdf5b82d35aa838.
- Initial isolated Wine 9 MetaEditor build timed out (Ops run 42454517471). Windows hosted QA with signed official MetaQuotes installer succeeded in actually compiling source. First native compiler log had 0 errors, 2 operator-precedence warnings. PR #13 patched explicit BUY/SELL validation, source+integrated CI green; merged main d497f449d9d69399996cfe9ae1f564dbb8f333c0.
- Final Windows hosted MetaEditor QA run 42455355502 produced **0 errors, 0 warnings** in 1440 ms and a real 54,342-byte EX5, SHA256 **5092b1b395ff91539f4d9952f89bc6976211ff43d4c7794caf7a76526a1d2ec9**. Both jobs succeeded. No customer broker credentials or production terminal accessed.
- Built EX5 and native compiler log were separately copied after independent hash and log validation into runner-only 0700 evidence folder **/var/lib/abutron-gh-runner/abutron-unapproved-qa-evidence/deriv6207-v4-20261108**; binary has .UNAPPROVED suffix to prevent accidental MT5 detection. Ops run **42455632012 SUCCESS**. Original private QA artifacts expire 2026-11-09 06:35 UTC, but source, build proof and protected host QA copy persist.
- Durable proof in apex11/mql5/DERIV6207_NATIVE_V4_QA_COMPILE_PROOF_20261108.md. Temporary GitHub issues-triggered build/preservation workflows and duplicate source mirror removed from Ops main; only original approved staging/health workflows should remain.
- **No compiled EX5 was installed into a running MT5 6207 terminal; no DEMO/LIVE order execution was enabled.** Native V4RevisionAuthorized still intentionally hard-false pending independently authenticated root-owned CRM activation/in-flight lease guardian, effective account switch/kill switch fencing, supervised release and actual broker-verified protected DEMO lifecycle. This remains the high-impact Milestone A blocker.

## Milestone A client ON/OFF native guardian source merged (2026-11-08 07:43 UTC)

- **PR #14 merged APEX main commit `7639dc16b788ab7a843942936dba2cbb97603651`**, after both APEX offline source integrity and combined integration CI passed at PR head `bd80b5b061e2a4ad8b6a83e26d9baa0642cd4f35` (runs 42459995333 and 42459995347).
- New source modules `native_v4_off_fence.py` (shared-ActivationStore atomic CLAIM/SEND/STOPPING/verified-settlement ledger), `native_v4_guardian_http.py` (authenticated local worker token; strict localhost; no default server), `native_v4_broker_authority.py` (uses independent VerifiedNativeSupervisor broker+CRM contracts), and revised MQL5 V4 native EA for synchronized two-phase CLAIM and SEND authorizations and root-attested 10-field readiness marker. Original `risk_guard/reservation_store.py` now requires same authenticated broker proof in finalized risk ledger before declaring OFF settled. Tests cover concurrent race, duplicate/replay, account OFF before and after claim/send, stale revision, wrong account, no order timeout, broker proof and capability status.
- **Final actual MetaEditor Windows compiler QA run 42459796202** with exact source Git blob `9e3a9487f6931554f79f4a2596ebf3460004f81a` + original MQH `e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44`, report 0 native errors/0 warnings, 4.033s. QA binary **87,218 bytes**, SHA256 **458afad273cb5c2446f52d766d2617cc277bca6b1e990450bb6955c2da64973a**. Binary independently reverified and stored with `.UNAPPROVED` suffix OUTSIDE MT5 EA directories: `/var/lib/abutron-gh-runner/abutron-unapproved-qa-evidence/deriv6207-v4-guardian-20261108/AbutronApexExistingDerivV4_6207.ex5.UNAPPROVED`. QA preservation run 42459935557 SUCCESS. One-shot GH Actions QA workflows and source mirror removed.
- **CRITICAL, NOT DONE IN PRODUCTION:** No concrete, authenticated `VerifiedNativeSupervisor` implementation for production V7 CRM/account entitlement and broker MT5 6207 has been connected/verified to the new source; there is no deployed local root/least-privilege authorization service, no provisioned per-worker secret or terminal localhost WebRequest permission, no verified active V4 chart binary and no independent DEMO order/deal/position/SL/TP receipt. The current portal must use the *same actual activation ledger/revisions* and show `STOPPING_BROKER_RECONCILIATION_REQUIRED` until authentic broker reconciliation after OFF; merely displaying `effective_on=0` is not a settled OFF assertion. Existing writer timer must not be started.
- **No active production MT5 EA was replaced. All LIVE remains OFF, no broker orders were submitted by this work, and Milestone A remains awaiting authenticated production integration and broker DEMO acceptance.**

