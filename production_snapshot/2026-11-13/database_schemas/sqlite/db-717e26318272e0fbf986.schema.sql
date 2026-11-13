-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /home/apexagent/.abutron-ai-history-snapshot-test/test.sqlite3
-- Database copy: db-717e26318272e0fbf986.sqlite3
-- Customer records not included.

CREATE TABLE candles(
             symbol TEXT NOT NULL,
             timeframe TEXT NOT NULL,
             start_time_utc INTEGER NOT NULL,
             open REAL NOT NULL, high REAL NOT NULL,
             low REAL NOT NULL, close REAL NOT NULL,
             PRIMARY KEY(symbol,timeframe,start_time_utc)
        ) WITHOUT ROWID;

CREATE TABLE imports(
             sha256 TEXT PRIMARY KEY, imported_at_utc TEXT NOT NULL,
             broker_generated_at_utc TEXT NOT NULL,
             candles_added INTEGER NOT NULL
        );
