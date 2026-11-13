-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-broker-deal-evidence/verified_trades.sqlite3
-- Database copy: db-6f65b8538816c1ceee21.sqlite3
-- Customer records not included.

CREATE TABLE broker_closed_trades(
          account_suffix TEXT NOT NULL,signal_key TEXT NOT NULL,broker_position INTEGER NOT NULL,
          symbol TEXT NOT NULL,side TEXT NOT NULL,volume REAL NOT NULL,
          entry_deal INTEGER NOT NULL,exit_deals_json TEXT NOT NULL,
          entry_time_server INTEGER NOT NULL,last_exit_time_server INTEGER NOT NULL,
          gross_profit_usd REAL NOT NULL,commission_usd REAL NOT NULL,
          fee_usd REAL NOT NULL,swap_usd REAL NOT NULL,deal_component_net_usd REAL NOT NULL,
          source_export_sha256 TEXT NOT NULL,source_session_exported_at INTEGER NOT NULL,
          independent_nontrade_fee_verification INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(account_suffix,broker_position));
