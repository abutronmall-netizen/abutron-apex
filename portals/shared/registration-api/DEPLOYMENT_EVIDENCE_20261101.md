# APEX client registration & legal centre — verified deployment
Date: 2026-11-01 around 13:53 SAST (11:53 UTC)
Target server: localhost / 172.239.115.84 (AbutronFX)
Public hostname: https://abutronfx.online

## Verified deployed routes
- Homepage `/` updated with Create Account links; HTTP 200
- Client registration `/account/`; HTTP 200
- Legal hub `/legal/`; HTTP 200
- Nine full policy pages `/legal/{terms,risk,trading-authorization,privacy,api,refund,cookies,status,methodology}/`; each HTTP 200, each detail page has acknowledgement checkbox
- `/account/api/status`: HTTP 200 with registration operational and broker status NOT independently verified
- `/account/api/register`: rejects missing consents HTTP 422, accepted complete synthetic test HTTP 201. Synthetic account removed after test.

## Architecture
- Isolated static frontend: `/var/www/apex-landing` (existing APEX landing preserved and updated)
- API: `/opt/apex-signup/registration.py`, `apex-signup.service`, localhost only `127.0.0.1:18889`, Caddy `/account/api/*` proxy.
- Separate restricted SQLite `/var/lib/apex-signup/accounts.sqlite3` owned apexsignup; all users created `pending_review` and database checks enforce demo/live execution flags are zero. No automatic broker connection, payments, or trading activation.
- Passwords hashed with unique-salt scrypt; no plaintext storage.
- Nine one-by-one UTC consent receipts per application, exact policy version `2026-11-01`, SHA256 content hash; immutable originals archived in `/var/lib/apex-signup/policy_snapshots/2026-11-01`. Backend status and registration verify current policies match archive (fail closed).
- Admission controls: Origin and JSON checks, form age + country, all-nine server-side boolean validation, IP-keyed rate limit and bounded password hashing concurrency, separate unprivileged systemd service.
- Previous landing/config snapshot: `/var/backups/apex-signup-deploy/20261101T114628Z`.
- Daily local backup: `apex-signup-backup.timer`, backup path `/var/backups/apex-signup` 0700. First backup `signup-20261101T115003Z.sqlite3` verified with `PRAGMA integrity_check=ok`. Not offsite.
- Existing `/apex/` operator dashboard continues protected by Caddy basic auth and was not modified. Trading source `abutron-ai` 144.126.232.85 was not modified. Old `api.abutronfx.online` 503 lockdown unchanged.

## Outstanding high-priority blockers
1. Confirm and publish true contracting legal entity, registration number, address and privacy Information Officer; counsel review under South African CPA, POPIA, FAIS/FSCA and jurisdictions served. Legal texts are operating drafts, not legal clearance.
2. Add customer email ownership verification, account login, secure activation/approval UX, KYC workflow, and opt-in marketing preferences where relevant. Current registration is only a DEMO access application; no automatic access email is sent.
3. Provide independent broker execution/status and measured historical uptime feed; public status currently reports registration health and correctly labels broker execution unverified.
4. Add independently restorable offsite backup with access management and test restoration; local backup alone cannot withstand host loss.
5. Before any commercial release, verify data processors, international transfers, breach response procedures, compliance obligations and payment/refund actual operations. DO NOT enable live customer trading as a side effect of signing up.

## Rollback consideration
Snapshot holds previous public landing + Caddyfile. Review current configuration before replacing; do not touch APEX trading services. If rolling back, restore existing static site and Caddyfile from snapshot, validate via `caddy validate` before reload, and disable only isolated signup service. Preserve consent DB and archived policies for legal/audit obligations.

## Evidence
- HTTP 200: homepage, account, legal hub + 9 pages
- HTTP 422: incomplete consent
- HTTP 201: complete synthetic registration
- DB test: 9 records, archived policy hashes equal, `pending_review`, flags 0/0, `PRAGMA integrity_check=ok`
- Synthetic test account removed; remaining customer applications count 0 immediately after test
- Service + backup timer active; Caddy config validated. Last checked approximately 2026-11-01 11:53 UTC.
