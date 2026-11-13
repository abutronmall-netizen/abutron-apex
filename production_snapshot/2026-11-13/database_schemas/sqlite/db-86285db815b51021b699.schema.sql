-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-tick-factor-shadow/readonly-public-spot-snapshot.sqlite3
-- Database copy: db-86285db815b51021b699.sqlite3
-- Customer records not included.

CREATE INDEX public_quote_source_idx ON public_quotes(batch_sha256);

CREATE TABLE public_quotes(
   symbol TEXT NOT NULL, epoch INTEGER NOT NULL,quote REAL NOT NULL,
   batch_sha256 TEXT NOT NULL,PRIMARY KEY(symbol,epoch));

CREATE TABLE sources(
   batch_sha256 TEXT PRIMARY KEY,received_utc TEXT NOT NULL,source_rows INTEGER NOT NULL,
   oldest_epoch INTEGER NOT NULL,newest_epoch INTEGER NOT NULL);
