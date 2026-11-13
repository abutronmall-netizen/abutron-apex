-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-native-forward-cost/shadow-native-cost.sqlite3
-- Database copy: db-7b569f539902164f8c5f.sqlite3
-- Customer records not included.

CREATE TABLE outcomes (
      symbol TEXT NOT NULL, factor TEXT NOT NULL, model_version TEXT NOT NULL,
      signal_m5 INTEGER NOT NULL, first_observed_utc TEXT NOT NULL,
      future_entry_m5 INTEGER NOT NULL, future_exit_m5 INTEGER NOT NULL,
      side TEXT NOT NULL, quote_entry_msc INTEGER NOT NULL,quote_exit_msc INTEGER NOT NULL,
      quote_entry_sha256 TEXT NOT NULL,quote_exit_sha256 TEXT NOT NULL,
      native_quote_gross_bps REAL NOT NULL, historical_broker_p95_cost_bps REAL NOT NULL,
      shadow_net5_bps REAL NOT NULL,shadow_net10_bps REAL NOT NULL,
      recorded_utc TEXT NOT NULL,
      PRIMARY KEY(symbol,factor,model_version,signal_m5));
