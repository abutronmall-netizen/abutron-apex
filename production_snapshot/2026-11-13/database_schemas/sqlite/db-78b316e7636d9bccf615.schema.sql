-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/entry-model-causal-v2.sqlite3
-- Database copy: db-78b316e7636d9bccf615.sqlite3
-- Customer records not included.

CREATE INDEX causal_pending ON observed(status,planned_entry_m5_start);

CREATE TABLE observed(
  symbol TEXT NOT NULL,model TEXT NOT NULL,signal_m5_start INTEGER NOT NULL,
  first_observed_utc TEXT NOT NULL,signal_age_sec REAL NOT NULL,
  planned_entry_m5_start INTEGER,
  side TEXT NOT NULL,atr REAL NOT NULL,signal_bar_hash TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,cost_sha256 TEXT NOT NULL,
  stop_floor REAL NOT NULL,commission_per_lot REAL NOT NULL,
  usd_per_price_point_per_lot REAL NOT NULL,
  broker_spread_p95_bps REAL NOT NULL,
  status TEXT NOT NULL,entry_price REAL,exit_price REAL,exit_reason TEXT,
  gross_return_bps REAL,net_0bps REAL,net_1bps REAL,net_5bps REAL,
  net_10bps REAL,resolved_utc TEXT,
  PRIMARY KEY(symbol,model,signal_m5_start)
 );
