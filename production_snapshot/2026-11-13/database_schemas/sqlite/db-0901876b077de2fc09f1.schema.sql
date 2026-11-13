-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-ai-smc-evidence/demo-veto-results/first_decisions.sqlite3
-- Database copy: db-0901876b077de2fc09f1.sqlite3
-- Customer records not included.

CREATE TABLE recorded_decisions (
            account_hash TEXT NOT NULL,account_suffix TEXT NOT NULL,execution_switch_on INTEGER NOT NULL,
            symbol TEXT NOT NULL, side TEXT NOT NULL, m5_bar_time INTEGER NOT NULL,
            decision TEXT NOT NULL,reason TEXT NOT NULL,smc TEXT NOT NULL,ai TEXT NOT NULL,
            ledger_state TEXT NOT NULL,first_observed_utc TEXT NOT NULL,last_observed_utc TEXT NOT NULL, ict TEXT NOT NULL DEFAULT 'NOT_EVALUATED', ict_pattern TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(account_hash,symbol,side,m5_bar_time,decision));
