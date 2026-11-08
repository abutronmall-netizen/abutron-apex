# Deriv 6207 — isolated V4 compile readiness (2026-11-08)

## Verified facts

- The owner verified three byte-identical copies of the missing header `AdaptiveRiskProofV2.mqh` with SHA256 `e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44`.
- Copies: `/root/abutron_optionc_cutover/AdaptiveRiskProofV2.mqh`; `/var/backups/abutron-five-volatility-prechange-20261107T105218Z/candidate/AdaptiveRiskProofV2.mqh`; `/var/backups/abutron-option-c-v2-release-20261105/adaptive-existing-ea-cutover-with-native-v2-proof/AdaptiveRiskProofV2.mqh`.
- Fixed non-root ops read-only run 42453738931 verified no original header is directly readable by the restricted runner. That is deliberate production least privilege, not a reason to grant sudo.
- Wine, winepath, wineboot, wineserver and xvfb-run are present, as is the root-owned non-group/world-writable `/opt/abutron/client-mt5-template-v2/MetaEditor64.exe`. Tool availability does not prove the compiler works.
- V4 candidate in APEX main `apex11/mql5/AbutronApexExistingDerivV4_6207.mq5` was derived from original hash-verified November 7 681-line `adaptive_bridge.mq5`. Both legacy order consumption and V4 authority remain disabled; the missing trusted CRM activation-revision supervisor cannot be replaced by a file or boolean.

## One-time owner-approved header handoff

Run the reviewed `deriv6207_verified_include_handoff.sh` as root, or its equivalent root-only, SHA-pinned and group-limited copy. Its *only* output file is `/var/lib/abutron-apex11-source-handoff/AdaptiveRiskProofV2.mqh` (root:abutrongha, mode 0640). Do not copy passwords, account credentials or MT5 config. The existing `adaptive_bridge.mq5` handoff stays as-is.

## Non-root QA compilation

Private ops workflow `deriv6207-v4-isolated-compile-once.yml` runs only when the owner opens exactly named issue `ABUTRON DERIV6207 V4 ISOLATED COMPILER QA V1`. It checks the header checksum and Git blob SHA `b2ba33416105e5719b740d164be8cd45561b80f9` of the V4 source staging mirror, root-owned MetaEditor, and creates a fresh `$RUNNER_TEMP` Wine prefix. It copies source + include there and requests MetaEditor compilation with `/compile`, `/include`, `/log`. QA binary/log never installs to production and no MT5 session is opened.

The workflow reports compile exit, whether the log exists, error/warning counts, and EX5 hash if generated. These are *compile-only* results. The standalone no-order MetaEditor smoke workflow is a separate prerequisite.

## Remaining engineering gate

A successful QA compilation is **NOT** permission to deploy. `V4RevisionAuthorized` is still deliberately hard-false, and the Python native V4 writer will not publish an order until the EA sends an independently authenticated current account-revision capability. The trusted root supervisor, atomic OFF-vs-in-flight fencing, end-to-end broker deal/position/SL/TP reconciliation, and monitored DEMO release are unimplemented. Maintain Deriv LIVE OFF and legacy dispatcher disabled.
