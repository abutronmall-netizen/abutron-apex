-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /opt/apex/upstream/Open-Finance-Lab__AgenticTrading/dashboard/storage/data/backtest.db
-- Database copy: db-57a06c14675fbcba3cab.sqlite3
-- Customer records not included.

CREATE INDEX idx_agent_runs_session ON agent_runs(session_id);

CREATE INDEX idx_agent_runs_session_mode ON agent_runs(session_id, mode);

CREATE INDEX idx_agent_versions_agent
            ON agent_versions(agent_id, created_at)
            ;

CREATE INDEX idx_auth_sessions_user_id
            ON auth_sessions(user_id)
            ;

CREATE INDEX idx_decisions_run
            ON backtest_decisions(run_id, step_index)
        ;

CREATE INDEX idx_external_agents_owner_browser
            ON external_agents(owner_browser_session)
            ;

CREATE INDEX idx_external_agents_owner_user
            ON external_agents(owner_user_id)
            ;

CREATE INDEX idx_external_agents_type
            ON external_agents(agent_type)
            ;

CREATE INDEX idx_protocol_runs_agent ON protocol_runs(agent_id);

CREATE INDEX idx_protocol_runs_backtest ON protocol_runs(backtest_id);

CREATE INDEX idx_run_timestamp 
            ON equity_timeseries(run_id, timestamp)
        ;

CREATE INDEX idx_trades_run
            ON trades(run_id, timestamp)
        ;

CREATE UNIQUE INDEX idx_users_discord_user_id
            ON users(discord_user_id)
            WHERE discord_user_id IS NOT NULL
            ;

CREATE UNIQUE INDEX uq_equity_timeseries_run_timestamp
                   ON equity_timeseries(run_id, timestamp);

CREATE TABLE agent_runs (
        run_id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        mode TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        initial_equity REAL NOT NULL,
        final_equity REAL,
        total_return REAL,
        sharpe_ratio REAL,
        max_drawdown REAL,
        num_trades INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        session_id TEXT DEFAULT 'legacy-demo-session',
        llm_model TEXT DEFAULT 'rule-based'
    , baseline_djia_run_id TEXT, baseline_buyhold_run_id TEXT, llm_calls INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, est_cost_usd REAL DEFAULT 0, metadata TEXT);

CREATE TABLE agent_versions (
                agent_version_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                version TEXT NOT NULL,
                execution_mode TEXT NOT NULL DEFAULT 'external',
                architecture TEXT,
                model_backbones TEXT NOT NULL DEFAULT '[]',
                decision_frequency TEXT NOT NULL DEFAULT '1h',
                code_commit TEXT,
                prompt_hash TEXT,
                config_hash TEXT,
                verification_level TEXT NOT NULL DEFAULT 'self_reported',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE auth_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

CREATE TABLE backtest_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                decision_source TEXT NOT NULL,
                actions_submitted TEXT,
                actions_executed INTEGER DEFAULT 0,
                context_ref TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
            );

CREATE TABLE equity_timeseries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        equity REAL NOT NULL,
        cash REAL,
        positions_value REAL,
        daily_return REAL,
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
    );

CREATE TABLE external_agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                session_id TEXT NOT NULL UNIQUE,
                api_key_hash TEXT NOT NULL UNIQUE,
                api_key_prefix TEXT NOT NULL,
                model_name TEXT NOT NULL DEFAULT 'local-model',
                scopes TEXT NOT NULL DEFAULT 'agents:register,runs:write,context:read,decisions:write,runs:read',
                owner_user_id INTEGER,
                owner_browser_session TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP, agent_type TEXT NOT NULL DEFAULT 'external', description TEXT, pipeline_config TEXT, cash_allocation REAL,
                FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
            );

CREATE TABLE idempotency_keys (
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                idem_key TEXT NOT NULL,
                ack_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (run_id, idem_key)
            );

CREATE TABLE protocol_runs (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT,
                agent_version_id TEXT,
                session_id TEXT NOT NULL,
                environment_id TEXT,
                environment_type TEXT,
                config TEXT NOT NULL DEFAULT '{}',
                backtest_id TEXT,
                result_run_id TEXT,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            , owner_instance TEXT, heartbeat_at TEXT, step_index INTEGER, total_steps INTEGER);

CREATE TABLE protocol_steps (
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT,
                deadline_at TEXT,
                status TEXT NOT NULL DEFAULT 'awaiting_decision',
                idempotency_key TEXT,
                result_json TEXT,
                PRIMARY KEY (run_id, step_id),
                UNIQUE (run_id, sequence)
            );

CREATE TABLE run_manifest (
                run_id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE strategies (
                code TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                description TEXT,
                source TEXT,
                owner TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run_id TEXT,
                last_run_at TIMESTAMP
            );

CREATE TABLE trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        shares INTEGER,
        price REAL,
        total_value REAL, quantity INTEGER, side TEXT, value REAL, reason TEXT,
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
    );

CREATE TABLE user_portfolios (
                owner_user_id INTEGER PRIMARY KEY,
                equity REAL NOT NULL,
                cash_available REAL NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );

CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            , discord_user_id TEXT, avatar TEXT);
