-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /home/dcagent/abutron-recovery/staging/mt5-fleet-control-20261025/simulation_runs/de82f535-61cc-46c2-aee9-164f17aadd57/mt5-fleet-simulation/simulated_registry.sqlite3
-- Database copy: db-36331fff72bda0b97ced.sqlite3
-- Customer records not included.

CREATE TABLE delivered(
  terminal_id TEXT NOT NULL, signal_id TEXT NOT NULL, decision TEXT NOT NULL,
  PRIMARY KEY(terminal_id,signal_id));

CREATE TABLE simulated_accounts(
  account_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, broker TEXT NOT NULL,
  server TEXT NOT NULL, fixture_login TEXT NOT NULL UNIQUE, bot_tier TEXT NOT NULL,
  terminal_id TEXT NOT NULL UNIQUE, terminal_state TEXT NOT NULL,
  execution_authorized INTEGER NOT NULL DEFAULT 0 CHECK(execution_authorized=0)
);
