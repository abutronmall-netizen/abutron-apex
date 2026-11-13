-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-apex11-7593/account-bound-m5-journal.sqlite3
-- Database copy: db-c29dfc9e7b458a902a77.sqlite3
-- Customer records not included.

CREATE TABLE decisions (
                publication_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL, account_id TEXT NOT NULL,
                broker TEXT NOT NULL, symbol TEXT NOT NULL,
                closed_ts INTEGER NOT NULL, bar_sha256 TEXT NOT NULL,
                manifest_sha256 TEXT NOT NULL, proposal_sha256 TEXT NOT NULL,
                payload TEXT NOT NULL, published_at TEXT NOT NULL,
                UNIQUE(customer_id,account_id,broker,symbol,closed_ts)
            );
