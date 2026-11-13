-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/rdagent-qwen-discovery/verified-native-model-fills.sqlite3
-- Database copy: db-9c131df25f12bfb21eec.sqlite3
-- Customer records not included.

CREATE INDEX model_receipt_version ON verified_fills(model_version,symbol);

CREATE TABLE verified_fills(
  signal_key TEXT PRIMARY KEY, model_version TEXT NOT NULL, model_factor TEXT NOT NULL,
  source_cohort_sha256 TEXT NOT NULL, symbol TEXT NOT NULL,side TEXT NOT NULL,
  broker_order INTEGER NOT NULL, broker_deal INTEGER NOT NULL UNIQUE,
  broker_position INTEGER NOT NULL, created_at_utc TEXT NOT NULL,
  captured_at_utc TEXT NOT NULL, native_evidence_sha256 TEXT NOT NULL,
  requested_price REAL NOT NULL, broker_fill_price REAL NOT NULL,
  adverse_slippage_bps REAL NOT NULL,quote_spread_bps REAL NOT NULL,
  entry_commission_usd REAL NOT NULL,entry_fee_usd REAL NOT NULL,
  entry_swap_usd REAL NOT NULL, protected INTEGER NOT NULL CHECK(protected=1)
 ) WITHOUT ROWID;
