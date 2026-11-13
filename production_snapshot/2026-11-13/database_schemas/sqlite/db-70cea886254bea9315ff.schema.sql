-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-tick-factor-shadow/prospective-tick-aligned.sqlite3
-- Database copy: db-70cea886254bea9315ff.sqlite3
-- Customer records not included.

CREATE INDEX outcomes_model ON outcomes(symbol,factor,version,hypothesis);

CREATE TABLE outcomes (
      symbol TEXT NOT NULL, factor TEXT NOT NULL, version TEXT NOT NULL,
      signal_m5 INTEGER NOT NULL, hypothesis TEXT NOT NULL,
      decision_epoch INTEGER NOT NULL, entry_epoch INTEGER NOT NULL, exit_epoch INTEGER NOT NULL,
      net5_bps REAL NOT NULL, net10_bps REAL NOT NULL,
      PRIMARY KEY (symbol,factor,version,signal_m5,hypothesis));
