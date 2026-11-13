-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/signal-attribution/decision-events.sqlite3
-- Database copy: db-f41badf60e22f3c44a2d.sqlite3
-- Customer records not included.

CREATE TABLE decisions(
          broker TEXT NOT NULL,
          symbol TEXT NOT NULL,
          closed_m5_utc INTEGER NOT NULL,
          side TEXT NOT NULL,
          category TEXT NOT NULL,
          first_observed_utc TEXT NOT NULL,
          PRIMARY KEY(broker,symbol,closed_m5_utc,side,category)
        ) WITHOUT ROWID;
