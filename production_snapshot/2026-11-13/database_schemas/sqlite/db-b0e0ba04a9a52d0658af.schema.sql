-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-ai-smc-evidence/confirmation.sqlite3
-- Database copy: db-b0e0ba04a9a52d0658af.sqlite3
-- Customer records not included.

CREATE TABLE directional_outcomes(
            account_hash TEXT NOT NULL,symbol TEXT NOT NULL,m5_open INTEGER NOT NULL,
            side TEXT NOT NULL,horizon_m5_bars INTEGER NOT NULL,
            directional_bps REAL NOT NULL,direction_correct INTEGER NOT NULL,
            price_direction_only INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(account_hash,symbol,m5_open,side,horizon_m5_bars));

CREATE TABLE signals(
            account_hash TEXT NOT NULL,symbol TEXT NOT NULL,m5_open INTEGER NOT NULL,
            side TEXT NOT NULL,signal_key TEXT NOT NULL,first_seen_utc TEXT NOT NULL,
            last_seen_utc TEXT NOT NULL,source_flags TEXT NOT NULL,
            smc_status TEXT NOT NULL,smc_score INTEGER,smc_reasons TEXT NOT NULL,
            ai_status TEXT NOT NULL,ai_direction TEXT,ai_reviewed_utc TEXT,ai_model TEXT,
            shadow_decision TEXT NOT NULL,ledger_state TEXT NOT NULL,ledger_reason TEXT,
            broker_position INTEGER,realized_broker_net_pnl_usd REAL,
            broker_costs_verified INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(account_hash,symbol,m5_open,side));
