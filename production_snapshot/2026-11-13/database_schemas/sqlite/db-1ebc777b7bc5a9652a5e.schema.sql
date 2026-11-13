-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-fp-execution/1636/order-router/order-journal.sqlite3
-- Database copy: db-1ebc777b7bc5a9652a5e.sqlite3
-- Customer records not included.

CREATE TABLE requests(
        signal_id TEXT PRIMARY KEY, closed_bar INTEGER NOT NULL,
        canonical TEXT NOT NULL, broker_symbol TEXT NOT NULL,
        side TEXT NOT NULL, session_nonce TEXT NOT NULL,
        state TEXT NOT NULL, created_at INTEGER NOT NULL,
        broker_order_id INTEGER, broker_deal_id INTEGER,
        UNIQUE(canonical,closed_bar));
