-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-smc-shadow/observations.sqlite3
-- Database copy: db-877634a3deef27119bd0.sqlite3
-- Customer records not included.

CREATE INDEX idx_observed_at ON observations(observed_at_utc);

CREATE TABLE observations (
            account_hash TEXT NOT NULL, symbol TEXT NOT NULL, m5_close INTEGER NOT NULL,
            baseline TEXT NOT NULL, smc_status TEXT NOT NULL, score INTEGER NOT NULL,
            reasons TEXT NOT NULL, observed_at_utc TEXT NOT NULL,
            PRIMARY KEY(account_hash, symbol, m5_close)
        );
