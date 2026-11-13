-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/rdagent-qwen-discovery/prospective.sqlite3
-- Database copy: db-c6c82c70043c723eb926.sqlite3
-- Customer records not included.

CREATE INDEX signals_maturity ON signals(status,future_exit_m5);

CREATE TABLE signals(
       symbol TEXT NOT NULL, factor TEXT NOT NULL, model_version TEXT NOT NULL,
       signal_m5 INTEGER NOT NULL, first_observed_utc TEXT NOT NULL,
       future_entry_m5 INTEGER NOT NULL, future_exit_m5 INTEGER NOT NULL,
       side TEXT NOT NULL, signal_bar_sha TEXT NOT NULL,
       status TEXT NOT NULL, entry_price REAL, exit_price REAL,
       net5_bps REAL, net10_bps REAL, resolved_utc TEXT,
       PRIMARY KEY(symbol,factor,model_version,signal_m5));
