-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-apex11-6207/v4-customer-risk-reservations.sqlite3
-- Database copy: db-49ce08d7ef5b0c0ecb30.sqlite3
-- Customer records not included.

CREATE INDEX idx_active_customer ON intents(customer_id, state);

CREATE TABLE intents (
                signal_key TEXT PRIMARY KEY, intent_sha TEXT NOT NULL,
                customer_id TEXT NOT NULL, account_id TEXT NOT NULL,
                risk_usd TEXT NOT NULL, risk_account_ccy TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('RESERVED','UNKNOWN','RECONCILED','REJECTED')),
                volume TEXT NOT NULL, created_at TEXT NOT NULL,
                completed_at TEXT, broker_proof_ref TEXT
              );

CREATE TABLE risk_locks (
                scope TEXT NOT NULL CHECK(scope IN ('CUSTOMER','ACCOUNT')),
                scope_id TEXT NOT NULL,
                lock_type TEXT NOT NULL CHECK(lock_type IN ('DAILY_LOSS','MAX_DRAWDOWN')),
                reason TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(scope, scope_id, lock_type)
              );
