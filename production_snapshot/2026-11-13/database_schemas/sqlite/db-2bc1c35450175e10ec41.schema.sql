-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-fp-execution/1622/reconciliation/broker-audit.sqlite3
-- Database copy: db-2bc1c35450175e10ec41.sqlite3
-- Customer records not included.

CREATE TABLE broker_snapshots (
            history_sha256 TEXT PRIMARY KEY, observed_at_utc TEXT NOT NULL,
            broker_equity_usd REAL NOT NULL, open_positions INTEGER NOT NULL,
            pending_orders INTEGER NOT NULL, trade_deals_90d INTEGER NOT NULL,
            bridge_proof_sha256 TEXT NOT NULL);
