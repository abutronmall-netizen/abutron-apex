-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /opt/apex/migration-staging-20261101/source-state/warehouse/deriv_broker_candles.sqlite
-- Database copy: db-26fedc76bef9c0abaf25.sqlite3
-- Customer records not included.

CREATE INDEX idx_bars_symbol_frame
                 ON bars(symbol,timeframe,time);

CREATE TABLE bars (
       symbol TEXT NOT NULL, timeframe TEXT NOT NULL, time INTEGER NOT NULL,
       open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
       volume INTEGER NOT NULL, broker_source TEXT NOT NULL,
       first_seen_utc TEXT NOT NULL,
       PRIMARY KEY(symbol,timeframe,time));

CREATE TABLE snapshots(
       sha256 TEXT PRIMARY KEY, generated_at_utc TEXT NOT NULL,
       ingested_at_utc TEXT NOT NULL, inserted_bars INTEGER NOT NULL,
       corrected_or_conflicting_bars INTEGER NOT NULL, total_bars INTEGER NOT NULL);
