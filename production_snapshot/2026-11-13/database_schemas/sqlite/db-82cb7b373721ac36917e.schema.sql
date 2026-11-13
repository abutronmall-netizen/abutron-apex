-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /opt/apex/migration-staging-20261101/source-state/demo-execution/attempts.sqlite
-- Database copy: db-82cb7b373721ac36917e.sqlite3
-- Customer records not included.

CREATE UNIQUE INDEX apex_basket_one_open_position_per_symbol_v1
                    ON attempts(symbol)
                    WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED','OPEN_BASKET');

CREATE UNIQUE INDEX apex_one_open_attempt_per_symbol_v3
                    ON attempts(symbol)
                    WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED');

CREATE TABLE attempts (
      signal_key TEXT PRIMARY KEY,
      created_utc TEXT NOT NULL,
      symbol TEXT NOT NULL,side TEXT NOT NULL,
      state TEXT NOT NULL,
      request_json TEXT NOT NULL,
      broker_order INTEGER,
      broker_deal INTEGER,
      error_code TEXT);
