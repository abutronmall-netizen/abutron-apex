-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex/demo-execution/attempts.sqlite
-- Database copy: db-1b246449768d52adce1b.sqlite3
-- Customer records not included.

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
