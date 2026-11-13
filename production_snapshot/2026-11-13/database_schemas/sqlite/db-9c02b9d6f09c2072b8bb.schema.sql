-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /home/dcagent/abutron-recovery/monitoring/v9365_native_research_signals.sqlite
-- Database copy: db-9c02b9d6f09c2072b8bb.sqlite3
-- Customer records not included.

CREATE INDEX idx_v9365_broker_symbol ON
 research_signal_observations(broker,account,symbol,mt5_logged_timestamp);

CREATE TABLE research_signal_observations(
 idempotency_key TEXT PRIMARY KEY,
 broker TEXT NOT NULL CHECK(broker = 'Deriv-Demo'),
 account TEXT NOT NULL CHECK(account = '32456207'),
 symbol TEXT NOT NULL,
 side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
 mt5_logged_timestamp TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,
 strategy_sha256 TEXT NOT NULL,
 first_observed_utc TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'RESEARCH_HOLD_NO_ORDERS',
 broker_order_ticket TEXT CHECK(broker_order_ticket IS NULL)
);
