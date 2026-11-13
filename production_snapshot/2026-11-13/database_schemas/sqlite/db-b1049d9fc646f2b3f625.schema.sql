-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-native-quote-cost/authenticated-mt5-evidence.sqlite3
-- Database copy: db-b1049d9fc646f2b3f625.sqlite3
-- Customer records not included.

CREATE INDEX quote_symbol_received
        ON native_sampled_quotes(symbol,received_utc);

CREATE TABLE file_cursor (
        source_name TEXT PRIMARY KEY,
        inode INTEGER NOT NULL,
        offset_bytes INTEGER NOT NULL,
        last_received_utc INTEGER,
        observed_lines INTEGER NOT NULL DEFAULT 0,
        updated_utc TEXT NOT NULL
    );

CREATE TABLE native_sampled_quotes (
        source_name TEXT NOT NULL,
        source_offset INTEGER NOT NULL,
        received_utc INTEGER NOT NULL,
        monotonic_ms INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        quote_time_msc INTEGER NOT NULL,
        bid REAL NOT NULL,
        ask REAL NOT NULL,
        spread_bps REAL NOT NULL,
        quote_age_ms INTEGER NOT NULL,
        line_sha256 TEXT NOT NULL,
        PRIMARY KEY(source_name,source_offset)
    );

CREATE TABLE verified_entry_fills (
        signal_key TEXT PRIMARY KEY,
        broker_order INTEGER NOT NULL,
        broker_deal INTEGER NOT NULL UNIQUE,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        native_quote_msc INTEGER NOT NULL,
        native_requested_price REAL NOT NULL,
        request_bid REAL NOT NULL,
        request_ask REAL NOT NULL,
        broker_fill_price REAL NOT NULL,
        adverse_slippage_bps REAL NOT NULL,
        entry_commission_usd REAL NOT NULL,
        entry_fee_usd REAL NOT NULL,
        entry_swap_usd REAL NOT NULL,
        order_send_duration_ms INTEGER NOT NULL,
        native_event_proof_sha256 TEXT NOT NULL,
        evidence_verified_utc TEXT NOT NULL,
        entry_protection_verified INTEGER NOT NULL
    );
