# ABUTRON APEX — production source snapshot

**Captured 13 November 2026 · Private staging branch · NOT a production deployment.**

## Verified GitHub import

**782 source files**: 205 broker, 214 engine, 230 operations, 133 portals. Files were imported from current Ubuntu paths into `source/` using GitHub Git Trees, not merely indexed in an export manifest. Each included file has its source path and SHA-256 in `SOURCE_MANIFEST.csv` and `SOURCE_SHA256.txt`.

## Scope

- `source/engine/`: APEX 1.1 decision, bridge, strategy and selected legacy runtime code
- `source/portals/`: client CRM, signup, V7 admin/client/APEX web and supporting portal code
- `source/broker/`: MT5 worker, native execution, Deriv/FP bridges and MQL5 source
- `source/operations/`: APEX executable scripts and systemd service/timer definitions

## Exclusions and qualifications

No personal data exports, databases with rows, active sessions, broker tokens, passwords, .env, API credentials, host private keys, TLS keys, runtime logs, Wine profiles, dependency virtual environments, cached Python, compiled EX5 and vendor/MetaQuotes library files were knowingly imported. Automatic regex checks are not a complete secrets audit. See `EXCLUSIONS.md`.

The source snapshot may include legacy or disabled code. **Presence of source does not imply the service is running.** The 6207 native dispatcher was blocked at the 13 November read-only audit by absent effective CRM ON/owner/ACK proof. Full broker and trading certification remains unverified.

## Repo status

**This is in the existing private repo `abutronmall-netizen/abutron-apex`, branch `snapshot/production-source-2026-11-13`. It is NOT the newly requested separate repository**; the connected GitHub actions cannot create repositories. Keep `main` unchanged until source review and repo creation are complete. 

## Documents

The Operator Cheat Sheet and Technical Blueprint PDF/DOCX are available as attachments in the originating ChatGPT conversation. Binary document files were not committed by the GitHub connector; do not assume the source tree includes them.
