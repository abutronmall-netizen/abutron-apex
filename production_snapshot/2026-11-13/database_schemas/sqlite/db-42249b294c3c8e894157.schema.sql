-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex/execution/intent_ledger.sqlite
-- Database copy: db-42249b294c3c8e894157.sqlite3
-- Customer records not included.

CREATE TABLE intents(
      signal_key TEXT PRIMARY KEY, first_seen_utc TEXT NOT NULL,
      symbol TEXT NOT NULL, side TEXT NOT NULL, m5_bar_time INTEGER NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('BLOCKED','UNCERTAIN','BROKER_CONFIRMED')),
      reason TEXT NOT NULL, estimated_loss_usd REAL,
      order_check_retcode INTEGER, evidence_sha256 TEXT NOT NULL);

CREATE TABLE lifecycle_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      signal_key TEXT NOT NULL,
      timestamp_utc TEXT NOT NULL, state TEXT NOT NULL,
      reason TEXT NOT NULL);

CREATE TABLE sqlite_sequence(name,seq);
