-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-apex11-fp-1622/account-bound-m5-journal.sqlite3
-- Database copy: db-21f9e8402d91de33c2be.sqlite3
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
