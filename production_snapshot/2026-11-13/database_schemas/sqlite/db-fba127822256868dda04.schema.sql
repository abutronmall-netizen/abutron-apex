-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/dual-broker/fp-immutable-native-candles.sqlite3
-- Database copy: db-fba127822256868dda04.sqlite3
-- Customer records not included.

CREATE TABLE fp_candles(
    account_fingerprint TEXT NOT NULL, symbol TEXT NOT NULL, actual TEXT NOT NULL,
    timeframe TEXT NOT NULL, start_time_utc INTEGER NOT NULL,
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    broker_time_raw INTEGER NOT NULL,
    PRIMARY KEY(account_fingerprint,symbol,timeframe,start_time_utc)
 ) WITHOUT ROWID;

CREATE TABLE fp_imports(
    account_fingerprint TEXT NOT NULL, sha256 TEXT NOT NULL,
    imported_utc TEXT NOT NULL, candles_added INTEGER NOT NULL,
    quote_samples_added INTEGER NOT NULL,
    PRIMARY KEY(account_fingerprint,sha256)
 ) WITHOUT ROWID;

CREATE TABLE fp_quotes(
    account_fingerprint TEXT NOT NULL, symbol TEXT NOT NULL, actual TEXT NOT NULL,
    observed_utc INTEGER NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL,
    spread_price REAL NOT NULL,
    PRIMARY KEY(account_fingerprint,symbol,observed_utc)
 ) WITHOUT ROWID;
