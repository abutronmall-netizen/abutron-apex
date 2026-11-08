# ABUTRON APEX 1.1.0 — Source import audit (8 November 2026)

## Provenance
- Original user-provided ZIP SHA-256: `98f1074c28786bc7f982a9a1a175b492718824449dd301c8e8c2b7b3e016c056`.
- ZIP CRC verification passed, SHA-256 matched the server record.
- **97 UTF-8 source, configuration, tests and documentation files imported unchanged** under `apex11/`.
- Full per-file SHA-256 manifest: `apex11/SOURCE_IMPORT_AUDIT.json`.
- Two PNG documentation screenshots deliberately excluded from Git; the top-level cutover checkpoint outside the app tree also excluded.
- The original `CHECKSUMS_SHA256.txt` references two runtime `state/` artifacts **not present in the user-supplied ZIP**. They are not part of this import. It also includes checksums for the two excluded PNGs. This manifest must not be treated as a fully verified archive-wide checksum report.

## Validation
- Pristine ZIP extracted and tested with `python -m pytest -q -p no:cacheprovider`: **108 tests passed locally**.
- GitHub Actions runs the same offline suite plus per-file source-hash verification.
- The isolated risk guard is a **separate draft PR #1**; that suite passed 47/47 tests independently on GitHub Actions.
- No authenticated broker-feed integration, actual MT5 order receipt, native stop/TP confirmation or ledger reconciliation is demonstrated by these tests.

## Integration/production boundary
- This PR is a **source import**. It intentionally does not install or run services on `localhost`, change customer ON/OFF controls, activate trading, modify invoices, or import secrets.
- Keep LIVE execution disabled.
- Subsequent separate integration must bind APEX BUY/SELL/HOLD to fresh authenticated closed M5 candles, verified native instrument specs, customer entitlements and effective ON/OFF states, centralized risk reservations, the exclusive native order writer, broker receipts, stop protections, and reconciliation.
- Before any production cutover, confirm current running code and service entrypoints, offsite backup/restore, rollback plan and exclusive order authority. First accept Deriv 6207 DEMO with real broker evidence; expand to other DEMO accounts only after it passes.
