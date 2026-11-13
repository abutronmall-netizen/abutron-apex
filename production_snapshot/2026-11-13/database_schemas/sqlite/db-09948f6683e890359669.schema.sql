-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-client-feed/execution-ledger.sqlite3
-- Database copy: db-09948f6683e890359669.sqlite3
-- Customer records not included.

CREATE INDEX attempts_customer_active ON attempts(connection_id,state);

CREATE INDEX attempts_customer_position ON attempts(connection_id,broker_position);

CREATE TABLE attempts(
  signal_key TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  connection_id TEXT NOT NULL,
  broker TEXT NOT NULL CHECK(broker='Deriv'),
  environment TEXT NOT NULL CHECK(environment='DEMO'),
  broker_server TEXT NOT NULL CHECK(broker_server='Deriv-Demo'),
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  m5_bar_time INTEGER NOT NULL,
  state TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  volume REAL,entry_price REAL,stop_loss REAL,take_profit REAL,
  buffered_loss_usd REAL,
  broker_order INTEGER,broker_deal INTEGER,broker_position INTEGER,
  reason TEXT,
  UNIQUE(connection_id,symbol,m5_bar_time)
 );
