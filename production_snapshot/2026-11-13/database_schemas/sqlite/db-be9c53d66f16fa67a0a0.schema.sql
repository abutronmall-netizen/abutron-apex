-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/forward-cost-shadow-v1.sqlite3
-- Database copy: db-be9c53d66f16fa67a0a0.sqlite3
-- Customer records not included.

CREATE INDEX idx_observations_pending ON observations(status,bar_time);

CREATE TABLE observations(
        symbol TEXT NOT NULL,model TEXT NOT NULL,bar_time INTEGER NOT NULL,
        recorded_utc TEXT NOT NULL,side TEXT NOT NULL,atr REAL NOT NULL,
        bar_digest TEXT NOT NULL,status TEXT NOT NULL,exit_reason TEXT,
        gross_bps REAL,settled_utc TEXT,PRIMARY KEY(symbol,model,bar_time)
    );
