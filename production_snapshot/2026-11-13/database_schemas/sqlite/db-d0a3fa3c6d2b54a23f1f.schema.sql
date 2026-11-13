-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-smc-shadow/forward_outcomes.sqlite3
-- Database copy: db-d0a3fa3c6d2b54a23f1f.sqlite3
-- Customer records not included.

CREATE TABLE outcomes(
          symbol TEXT NOT NULL,signal_m5_open INTEGER NOT NULL,side TEXT NOT NULL,
          smc_status TEXT NOT NULL,horizon_m5_bars INTEGER NOT NULL,
          observed_account_count INTEGER NOT NULL,
          hypothetical_entry_open REAL NOT NULL,hypothetical_exit_close REAL NOT NULL,
          directional_bps REAL NOT NULL,direction_correct INTEGER NOT NULL,
          market_snapshot_utc TEXT NOT NULL,recorded_utc TEXT NOT NULL,
          PRIMARY KEY(symbol,signal_m5_open,side,horizon_m5_bars)
        );
