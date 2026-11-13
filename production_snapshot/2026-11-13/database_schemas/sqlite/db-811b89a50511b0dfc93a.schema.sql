-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-fp-execution/order-router/order-journal.sqlite3
-- Database copy: db-811b89a50511b0dfc93a.sqlite3
-- Customer records not included.

CREATE TABLE requests(
        signal_id TEXT PRIMARY KEY, closed_bar INTEGER NOT NULL,
        canonical TEXT NOT NULL, broker_symbol TEXT NOT NULL,
        side TEXT NOT NULL, session_nonce TEXT NOT NULL,
        state TEXT NOT NULL, created_at INTEGER NOT NULL,
        broker_order_id INTEGER, broker_deal_id INTEGER,
        UNIQUE(canonical,closed_bar));
