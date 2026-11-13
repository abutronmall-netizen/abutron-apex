-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/tick-intelligence/quotes.sqlite3
-- Database copy: db-29598886385e75d7c837.sqlite3
-- Customer records not included.

CREATE INDEX tick_source_lookup ON ticks(origin_sha256);

CREATE TABLE sources(
  sha256 TEXT PRIMARY KEY,schema TEXT NOT NULL,collected_utc TEXT NOT NULL,
  source_session_hash TEXT NOT NULL,source_account_hash TEXT NOT NULL,
  native_export_errors INTEGER NOT NULL,source_rows INTEGER NOT NULL,ingested_utc TEXT NOT NULL);

CREATE TABLE ticks(
  symbol TEXT NOT NULL,time_msc INTEGER NOT NULL,bid REAL NOT NULL,ask REAL NOT NULL,
  origin_sha256 TEXT NOT NULL,PRIMARY KEY(symbol,time_msc));
