-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex/demo-execution/v3-checkpoints/20261031T214712Z/attempts.before-v3.sqlite
-- Database copy: db-8decbde60490141997b4.sqlite3
-- Customer records not included.

CREATE TABLE attempts (
      signal_key TEXT PRIMARY KEY,
      created_utc TEXT NOT NULL,
      symbol TEXT NOT NULL,side TEXT NOT NULL,
      state TEXT NOT NULL,
      request_json TEXT NOT NULL,
      broker_order INTEGER,
      broker_deal INTEGER,
      error_code TEXT);
