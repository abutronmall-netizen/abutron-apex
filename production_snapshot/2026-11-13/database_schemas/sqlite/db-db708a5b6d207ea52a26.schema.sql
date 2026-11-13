-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/signal-outcomes/signal-outcomes.sqlite3
-- Database copy: db-db708a5b6d207ea52a26.sqlite3
-- Customer records not included.

CREATE TABLE outcomes (
  broker TEXT NOT NULL, account_fingerprint TEXT NOT NULL,
  symbol TEXT NOT NULL, decision_bar_utc INTEGER NOT NULL, side TEXT NOT NULL,
  decision_category TEXT NOT NULL, horizon_bars INTEGER NOT NULL,
  theoretical_entry_bar_utc INTEGER NOT NULL, theoretical_entry_price REAL NOT NULL,
  theoretical_exit_close_utc INTEGER NOT NULL, theoretical_exit_close REAL NOT NULL,
  gross_directional_bps REAL NOT NULL, hypothetical_cost_scenarios_json TEXT NOT NULL,
  observed_nearby_spread_bps REAL, observed_spread_sample_age_s INTEGER,
  first_evaluated_utc TEXT NOT NULL,
  PRIMARY KEY (broker,account_fingerprint,symbol,decision_bar_utc,side,decision_category,horizon_bars)
  ) WITHOUT ROWID;
