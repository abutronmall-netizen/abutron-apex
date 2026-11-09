# ABUTRON portal database exports — 2026-11-09

**UNENCRYPTED** complete data snapshots for the three PostgreSQL databases and ten discovered SQLite databases associated with the Client, Admin, and APEX portals, including historical snapshots.

## Contents

- `postgresql/*.sql`: plain SQL schema **and data**, dumped consistently with PostgreSQL `pg_dump` (three DBs).
- `sqlite/*.sqlite.gz`: **unencrypted**, gzip-compressed online-consistent SQLite database backups (ten DBs). Gzip is not encryption.
- `MANIFEST.json`: source timestamps, exact SHA-256 hashes and sizes.

## Restore into a separate test environment only

For PostgreSQL, create a fresh empty database first, then:

```bash
psql -d NEW_TEST_DATABASE -v ON_ERROR_STOP=1 -f databases/postgresql/abutron_v7_release_store.sql
```

For the two large SQLite history files, reconstruct their gzip files from the numbered unencrypted parts, then decompress:

```bash
cat databases/sqlite/apex_precision_history.sqlite.gz.part* > apex_precision_history.sqlite.gz
gzip -dc apex_precision_history.sqlite.gz > restored_history.sqlite
```

For other SQLite files:

```bash
gzip -dc databases/sqlite/signup_accounts.sqlite.gz > restored_signup_accounts.sqlite
sqlite3 restored_signup_accounts.sqlite 'PRAGMA quick_check;'
```

Do not restore these files over running production databases. The dump contains real production records, potentially including account emails, password hashes, broker details and tokens. This private repository requires strict access controls; do not make it public or share clones. It does NOT include service environment files, private keys or external broker account secrets held outside these databases.

Individual database snapshots are consistent; different databases were dumped sequentially, not under one globally atomic transaction.
