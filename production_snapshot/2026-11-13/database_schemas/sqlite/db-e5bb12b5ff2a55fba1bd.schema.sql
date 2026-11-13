-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/abutron-quant-first/entry-model-forward-v1.sqlite3
-- Database copy: db-e5bb12b5ff2a55fba1bd.sqlite3
-- Customer records not included.

CREATE INDEX observed_pending ON observed(status,bar_time);

CREATE TABLE observed(
        symbol TEXT NOT NULL,model TEXT NOT NULL,bar_time INTEGER NOT NULL,
        side TEXT NOT NULL,atr REAL NOT NULL,bar_digest TEXT NOT NULL,
        model_sha256 TEXT NOT NULL,cost_sha256 TEXT NOT NULL,
        stop_floor REAL NOT NULL,commission_per_lot REAL NOT NULL,
        usd_per_price_point_lot REAL NOT NULL,spread_bps_snapshot REAL NOT NULL,
        first_observed_utc TEXT NOT NULL,status TEXT NOT NULL,
        exit_reason TEXT,gross_bps REAL,net_5bps REAL,net_10bps REAL,net_20bps REAL,
        realized_at_utc TEXT,PRIMARY KEY(symbol,model,bar_time)
    );
