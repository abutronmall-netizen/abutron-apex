-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-v4-broker-crm-supervisor-6207/six-account-observed-equity.sqlite3
-- Database copy: db-2d087912344e143d4450.sqlite3
-- Customer records not included.

CREATE TABLE equity_samples(
            minute_utc INTEGER NOT NULL,
            owner_hash TEXT NOT NULL, account_suffix TEXT NOT NULL,
            broker TEXT NOT NULL, environment TEXT NOT NULL,
            balance_usd TEXT NOT NULL, equity_usd TEXT NOT NULL,
            risk_report_sha256 TEXT NOT NULL,
            PRIMARY KEY(minute_utc,owner_hash,account_suffix,broker));
