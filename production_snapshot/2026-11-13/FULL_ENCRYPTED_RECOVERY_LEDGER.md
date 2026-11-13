# ABUTRON APEX — full private recovery snapshot ledger

**Date:** 13 November 2026 (UTC), production Ubuntu host `localhost`  
**Backup mechanism:** private encrypted Restic repository, not plaintext Git data  
**Purpose:** retain source, configuration, databases, account-bound broker evidence, MT5 homes and private runtime in recoverable form without changing trading.

## Saved encrypted snapshots (verified)

| ID | Scope | Files processed | Data processed | Verification |
|---|---|---:|---:|---|
| `156e059c` | Main server/application snapshot: `/opt`, `/etc`, selected `/usr/local`, `/root`, `/home/dcagent`, `/var/www`, `/var/log`, ABUTRON/APEX `/var/lib` and `/var/backups` directories, three native sidecar evidence paths, PostgreSQL logical dumps | 291,305 | 58.859 GiB | Restic repository check PASS; V7 PostgreSQL dump remote readback and `pg_restore --list` PASS; log `/var/log/abutron-full-backup-20261113T131431Z.log` ends `FULL_BACKUP_END_SUCCESS` |
| `9196eeca` | All 29 `/var/lib/private/abutron-*` directories, `/home/apexmt5`, `/home/abutron_mt5_ui`, 70 SQLite online-copy files and manifest at `/run/abutron-db-online-20261113` | 166,764 | 118.745 GiB | Restic check PASS; remote SQLite manifest byte-for-byte `cmp` PASS; remote SQLite sample byte-for-byte `cmp` and SQLite `quick_check` PASS |
| `34bfc32b` | `/home/apexagent` and `/home/abutronmcp` agent/control-plane home trees | 35,388 | 1.704 GiB | Restic upload PASS; remote APEX agent file readback `cmp` PASS; final repository-wide `restic check` PASS (no errors) |

**Combined workload:** 493,457 file entries, 179.308 GiB processed. This is not a unique-file count; source paths may overlap across snapshots. Restic compression and deduplication mean stored backup bytes are smaller.

## Database details

- PostgreSQL: logical dumps for `abutron_recovery_legacy_app_20261023`, `abutron_recovery_legacy_platform_20261023`, `abutron_v7_release_store`, and `postgres`; global roles dumped separately. Dumps are in the encrypted main snapshot at `/run/abutron-full-backup-20261113T131431Z/databases/`.
- SQLite: 70 valid online backup copies with SHA-256 manifest. The original database path and consistent copy mapping are in `DATABASE_RECOVERY_CATALOG.md`; full binary copies are in snapshot `9196eeca`.
- Five Docker `.db` paths were **not** valid SQLite format; they remain preserved as native binary files under `/opt/abutron-research/docker-data` in snapshot `156e059c`.
- GitHub contains **schema only** (3 PostgreSQL DDL files + 70 SQLite DDL files), not the actual database rows.

## What GitHub contains

Private repository: `abutronmall-netizen/abutron-apex`  
Isolated branch: `snapshot/production-source-2026-11-13`  
- 782 reviewed, plaintext source files with original-path and SHA-256 manifest
- Three PostgreSQL schema-only files and 70 SQLite schema-only files
- Database recovery catalog and this recovery ledger
- No broker credentials, customer records, database contents or encryption material

**No new separate repository was created:** the available GitHub connector cannot create repositories. This branch is a private staging location, not the requested new final destination.

## Recovery procedure (ISOLATED recovery environment only)

Use the server's existing protected Restic repository configuration and encryption credentials. **Do not copy keys or passwords into GitHub or a terminal transcript.**

1. Provision an isolated recovery host with adequate storage (at least the restored file sizes plus PostgreSQL/SQLite workspace) and restricted permissions.
2. Authenticate to the configured encrypted Restic repository using the existing approved credential handling.
3. List/check snapshots and restore `156e059c`, `9196eeca`, and `34bfc32b` to *separate staging targets*, not over running production.
4. Verify source hashes, file permissions/owners, systemd definitions and MT5 worker configurations. Do not restart live execution during verification.
5. In isolated PostgreSQL, inspect the restored `pg_dump` files with `pg_restore --list` then restore roles/schema/data to temporary databases and run table/row-count checks.
6. Map SQLite copies using `MANIFEST.json`; compare SHA-256, run `PRAGMA quick_check` and open application-level samples in a disposable environment.
7. Validate broker state only from fresh authenticated broker receipts; recovered state is a historical point-in-time image and must not be replayed as current orders.
8. Test the full application stack and rollback from the isolated clone before any planned production restore.

## Limits and omissions

- These are broad application recovery snapshots, **not** a bootable sector-by-sector image of the entire Ubuntu operating-system disk.
- Concurrently changing MT5 logs/cache files may not represent one simultaneous instant across all workers; SQLite and PostgreSQL have separate consistent logical copies.
- The existing Google Drive mirror under `/home/dcagent/abutron-recovery/staging/gdrive-backups` and unrelated operating-system/system-package caches are excluded from the primary snapshot as redundant or reconstructible.
- No complete isolated system restore was performed during this capture. A clean Restic check and sample readbacks do not prove the platform can fully boot or trade correctly.
- Nothing was deployed; no trading switches, risk settings, broker connections, EAs or customer records were changed by the export itself.

**Priority after handover:** complete isolated restoration and identify the exact GitHub repository destination. Do not treat the staged source branch as a full encrypted backup.
