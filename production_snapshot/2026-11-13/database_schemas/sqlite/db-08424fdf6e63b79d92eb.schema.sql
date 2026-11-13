-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /opt/apex/migration-staging-20261101/runtime/recovery/agentictrading-seed-before-restore-20261031.db
-- Database copy: db-08424fdf6e63b79d92eb.sqlite3
-- Customer records not included.

CREATE INDEX idx_admin_analytics_access_admin_time
    ON admin_analytics_access_log(admin_user_id, accessed_at DESC, sequence DESC);

CREATE INDEX idx_admin_analytics_access_subject_time
    ON admin_analytics_access_log(subject_user_id, accessed_at DESC, sequence DESC);

CREATE INDEX idx_agent_runs_session ON agent_runs(session_id);

CREATE INDEX idx_agent_runs_session_mode ON agent_runs(session_id, mode);

CREATE INDEX idx_agent_trace_events_trace_sequence
                    ON agent_trace_events(trace_id, sequence_no);

CREATE INDEX idx_agent_traces_agent_created
                    ON agent_traces(agent_id, created_at DESC);

CREATE INDEX idx_agent_versions_agent
            ON agent_versions(agent_id, created_at)
            ;

CREATE INDEX idx_analytics_events_error_time
    ON analytics_events(error_category, occurred_at DESC)
    WHERE error_category IS NOT NULL;

CREATE INDEX idx_analytics_events_name_time
    ON analytics_events(event_name, occurred_at DESC);

CREATE INDEX idx_analytics_events_outcome_time
    ON analytics_events(outcome, occurred_at DESC)
    WHERE outcome IS NOT NULL;

CREATE INDEX idx_analytics_events_session_time
    ON analytics_events(session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;

CREATE INDEX idx_analytics_events_user_time
    ON analytics_events(user_id, occurred_at DESC, sequence DESC);

CREATE INDEX idx_auth_sessions_expires_at
            ON auth_sessions(expires_at)
            ;

CREATE INDEX idx_auth_sessions_user_id
            ON auth_sessions(user_id)
            ;

CREATE INDEX idx_credit_grant_pool_ledger_pool_id
            ON credit_grant_pool_ledger_entries(pool_id, id DESC)
            ;

CREATE INDEX idx_credit_grant_user_reference
            ON credit_ledger_entries(reference_type, reference_id, user_id, id DESC)
            ;

CREATE INDEX idx_credit_ledger_payment_order
            ON credit_ledger_entries(payment_order_id, id DESC)
            ;

CREATE INDEX idx_credit_ledger_user_id
            ON credit_ledger_entries(user_id, id DESC)
            ;

CREATE INDEX idx_credit_llm_reservations_run_status
            ON credit_llm_reservations(run_id, status, call_index, attempt_index)
            ;

CREATE INDEX idx_credit_llm_reservations_user_status
            ON credit_llm_reservations(user_id, status, created_at)
            ;

CREATE INDEX idx_credit_llm_usage_user_id
            ON credit_llm_usage_entries(user_id, id DESC)
            ;

CREATE INDEX idx_credit_llm_usage_user_run
            ON credit_llm_usage_entries(user_id, run_id)
            ;

CREATE INDEX idx_credit_payment_orders_user_sequence
                ON credit_payment_orders(user_id, sequence DESC);

CREATE INDEX idx_credit_promotion_grants_campaign_user
            ON credit_promotion_grants(campaign_key, user_id)
            ;

CREATE INDEX idx_credit_promotion_grants_user_id
            ON credit_promotion_grants(user_id, id DESC)
            ;

CREATE INDEX idx_credit_refunds_order_status
                ON credit_refund_requests(payment_order_id, status);

CREATE INDEX idx_daily_facts_operational
    ON user_daily_facts(snapshot_date, operational_state, operational_reason_code);

CREATE INDEX idx_daily_facts_segment
    ON user_daily_facts(snapshot_date, lifecycle_segment);

CREATE INDEX idx_daily_facts_tier
    ON user_daily_facts(snapshot_date, tier);

CREATE INDEX idx_daily_facts_user
    ON user_daily_facts(user_id, snapshot_date DESC);

CREATE INDEX idx_daily_facts_user_group
    ON user_daily_facts(snapshot_date, user_group);

CREATE INDEX idx_decisions_run
            ON backtest_decisions(run_id, step_index)
        ;

CREATE INDEX idx_email_change_requests_user_id
            ON email_change_requests(user_id)
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

CREATE INDEX idx_lifecycle_transitions_day
    ON lifecycle_transitions(snapshot_date, to_segment);

CREATE INDEX idx_password_reset_requests_user_id
            ON password_reset_requests(user_id)
            ;

CREATE INDEX idx_protocol_runs_agent ON protocol_runs(agent_id);

CREATE INDEX idx_protocol_runs_backtest ON protocol_runs(backtest_id);

CREATE INDEX idx_research_runs_user
                ON research_runs(user_id, created_at DESC);

CREATE INDEX idx_run_timestamp 
            ON equity_timeseries(run_id, timestamp)
        ;

CREATE INDEX idx_trades_run
            ON trades(run_id, timestamp)
        ;

CREATE UNIQUE INDEX idx_user_model_credentials_active_label
                ON user_model_credentials(user_id, provider_id, label)
                WHERE status <> 'revoked';

CREATE INDEX idx_user_model_credentials_owner
                ON user_model_credentials(user_id, provider_id, updated_at DESC);

CREATE UNIQUE INDEX idx_users_discord_user_id
            ON users(discord_user_id)
            WHERE discord_user_id IS NOT NULL
            ;

CREATE UNIQUE INDEX uq_equity_timeseries_run_timestamp
                   ON equity_timeseries(run_id, timestamp);

CREATE UNIQUE INDEX uq_user_model_credentials_default
                ON user_model_credentials(user_id, provider_id)
                WHERE is_default = 1 AND status = 'verified';

CREATE TABLE admin_analytics_access_log (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL,
    subject_user_id INTEGER NOT NULL,
    section TEXT NOT NULL CHECK (
        section IN ('overview', 'timeline', 'runs', 'usage', 'sessions')
    ),
    accessed_at TEXT NOT NULL,
    FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (subject_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE agent_credentials (
                agent_id TEXT NOT NULL,
                credential_name TEXT NOT NULL,
                value_enc TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (agent_id, credential_name)
            );

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
    , baseline_djia_run_id TEXT, baseline_buyhold_run_id TEXT, llm_calls INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, est_cost_usd REAL DEFAULT 0, metadata TEXT, llm_decisions INTEGER DEFAULT 0, owner_user_id INTEGER);

CREATE TABLE agent_trace_events (
                    event_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    actor_id TEXT,
                    step_id TEXT,
                    decision_id TEXT,
                    artifact_id TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    idempotency_key TEXT,
                    schema_version INTEGER NOT NULL DEFAULT 1, parent_event_id TEXT,
                    FOREIGN KEY (trace_id) REFERENCES agent_traces(trace_id),
                    UNIQUE (trace_id, sequence_no),
                    UNIQUE (trace_id, idempotency_key)
                );

CREATE TABLE agent_traces (
                    trace_id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    agent_version_id TEXT,
                    run_id TEXT NOT NULL UNIQUE,
                    user_id INTEGER,
                    trace_kind TEXT NOT NULL DEFAULT 'trading_run',
                    status TEXT NOT NULL DEFAULT 'running',
                    initial_input_json TEXT NOT NULL DEFAULT '{}',
                    final_output_summary TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    created_at TEXT NOT NULL
                , parent_trace_id TEXT);

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

CREATE TABLE analytics_daily_rollups (
    rollup_date TEXT NOT NULL CHECK (length(rollup_date) = 10),
    metric_name TEXT NOT NULL CHECK (length(metric_name) BETWEEN 1 AND 64),
    event_name TEXT NOT NULL DEFAULT '' CHECK (length(event_name) <= 64),
    billing_mode TEXT NOT NULL DEFAULT '' CHECK (length(billing_mode) <= 32),
    provider_id TEXT NOT NULL DEFAULT '' CHECK (length(provider_id) <= 128),
    model_id TEXT NOT NULL DEFAULT '' CHECK (length(model_id) <= 256),
    outcome TEXT NOT NULL DEFAULT '' CHECK (length(outcome) <= 32),
    error_category TEXT NOT NULL DEFAULT '' CHECK (length(error_category) <= 64),
    user_state TEXT NOT NULL DEFAULT '' CHECK (length(user_state) <= 32),
    value_count INTEGER NOT NULL DEFAULT 0 CHECK (value_count >= 0),
    value_sum_micro INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (
        rollup_date, metric_name, event_name, billing_mode, provider_id,
        model_id, outcome, error_category, user_state
    )
);

CREATE TABLE analytics_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE CHECK (length(event_id) = 36),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    event_name TEXT NOT NULL CHECK (length(event_name) BETWEEN 1 AND 64),
    event_group TEXT NOT NULL
        CHECK (event_group IN ('experience', 'account', 'credential', 'agent', 'run', 'resource')),
    user_id INTEGER NOT NULL,
    session_id TEXT CHECK (session_id IS NULL OR length(session_id) = 36),
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    event_source TEXT NOT NULL
        CHECK (event_source IN ('frontend', 'server', 'backfill')),
    source_event_id TEXT UNIQUE
        CHECK (source_event_id IS NULL OR length(source_event_id) BETWEEN 1 AND 200),
    source_record_type TEXT
        CHECK (source_record_type IS NULL OR length(source_record_type) BETWEEN 1 AND 64),
    source_record_id TEXT
        CHECK (source_record_id IS NULL OR length(source_record_id) BETWEEN 1 AND 200),
    correlation_id TEXT
        CHECK (correlation_id IS NULL OR length(correlation_id) BETWEEN 1 AND 200),
    page_view TEXT CHECK (page_view IS NULL OR length(page_view) BETWEEN 1 AND 64),
    provider_id TEXT CHECK (provider_id IS NULL OR length(provider_id) BETWEEN 1 AND 128),
    model_id TEXT CHECK (model_id IS NULL OR length(model_id) BETWEEN 1 AND 256),
    billing_mode TEXT
        CHECK (billing_mode IS NULL OR billing_mode IN ('byok', 'platform_credits')),
    outcome TEXT
        CHECK (outcome IS NULL OR outcome IN ('succeeded', 'failed', 'cancelled')),
    error_category TEXT CHECK (
        error_category IS NULL OR error_category IN (
            'credential_invalid', 'credential_missing', 'provider_timeout',
            'provider_unavailable', 'provider_quota_exhausted',
            'credits_unavailable',
            'model_not_allowed', 'internal_error', 'run_timeout',
            'account_restricted', 'credits_insufficient', 'empty_response'
        )
    ),
    country_code TEXT CHECK (country_code IS NULL OR length(country_code) = 2),
    device_category TEXT CHECK (
        device_category IS NULL OR device_category IN (
            'mobile', 'tablet', 'desktop', 'unknown'
        )
    ),
    browser_family TEXT CHECK (
        browser_family IS NULL OR browser_family IN (
            'Edge', 'Chrome', 'Firefox', 'Safari', 'Other'
        )
    ),
    network_hash TEXT CHECK (network_hash IS NULL OR length(network_hash) = 64),
    properties_json TEXT NOT NULL DEFAULT '{}'
        CHECK (length(properties_json) <= 1024),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE analytics_projection_jobs (
    job_name TEXT PRIMARY KEY,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    cursor TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'complete')),
    updated_at TEXT NOT NULL
);

CREATE TABLE analytics_subject_settings (
    user_id INTEGER PRIMARY KEY,
    excluded INTEGER NOT NULL CHECK (excluded IN (0, 1)),
    actor_user_id INTEGER NOT NULL,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE auth_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP NOT NULL,
        last_seen_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        revoked_at TIMESTAMP,
        user_agent TEXT,
        ip_prefix TEXT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actions_trace_ref TEXT,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
            );

CREATE TABLE broker_connections (
                user_id INTEGER NOT NULL,
                broker TEXT NOT NULL DEFAULT 'robinhood',
                access_token_enc TEXT NOT NULL,
                refresh_token_enc TEXT,
                client_id TEXT,
                agentic_account_id TEXT,
                token_expires_at TEXT,
                metadata_json TEXT,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, broker),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

CREATE TABLE credit_accounts (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'restricted')),
                    restriction_reason TEXT
                        CHECK (restriction_reason IN (
                            'llm_overage', 'refund_reconciliation'
                        ) OR restriction_reason IS NULL),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

CREATE TABLE credit_grant_pool_ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id TEXT NOT NULL,
    pool_name_snapshot TEXT NOT NULL
        CHECK (length(trim(pool_name_snapshot)) > 0),
    pool_status_snapshot TEXT NOT NULL
        CHECK (pool_status_snapshot IN ('active', 'disabled')),
    entry_type TEXT NOT NULL
        CHECK (entry_type IN ('fund', 'reduce', 'assign', 'reclaim')),
    amount_micro INTEGER NOT NULL CHECK (amount_micro <> 0),
    operation_id TEXT NOT NULL UNIQUE
        CHECK (length(trim(operation_id)) > 0),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(idempotency_key)) > 0),
    request_digest TEXT NOT NULL CHECK (length(trim(request_digest)) > 0),
    actor_user_id INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    user_id INTEGER,
    user_ledger_entry_id INTEGER UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (pool_id)
        REFERENCES credit_grant_pools(pool_id) ON DELETE RESTRICT,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_ledger_entry_id)
        REFERENCES credit_ledger_entries(id) ON DELETE RESTRICT,
    CHECK (
        (entry_type = 'fund' AND amount_micro > 0
            AND user_id IS NULL AND user_ledger_entry_id IS NULL)
        OR (entry_type = 'reduce' AND amount_micro < 0
            AND user_id IS NULL AND user_ledger_entry_id IS NULL)
        OR (entry_type = 'assign' AND amount_micro < 0
            AND user_id IS NOT NULL AND user_ledger_entry_id IS NOT NULL)
        OR (entry_type = 'reclaim' AND amount_micro > 0
            AND user_id IS NOT NULL AND user_ledger_entry_id IS NOT NULL)
    )
);

CREATE TABLE credit_grant_pools (
    pool_id TEXT PRIMARY KEY CHECK (length(trim(pool_id)) > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL
);

CREATE TABLE credit_ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    bucket TEXT NOT NULL CHECK (bucket IN ('grant', 'purchased')),
    entry_type TEXT NOT NULL CHECK (entry_type IN (
        'purchase', 'refund', 'admin_grant_assign', 'admin_grant_reclaim'
    )),
    amount_micro INTEGER NOT NULL CHECK (amount_micro <> 0),
    payment_order_id TEXT,
    refund_request_id TEXT,
    stripe_event_id TEXT,
    operation_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(operation_key)) > 0),
    operation_id TEXT NOT NULL CHECK (length(trim(operation_id)) > 0),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(idempotency_key)) > 0),
    request_digest TEXT CHECK (
        request_digest IS NULL OR length(trim(request_digest)) > 0
    ),
    actor_user_id INTEGER,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    reference_type TEXT,
    reference_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (payment_order_id)
        REFERENCES credit_payment_orders(id) ON DELETE RESTRICT,
    FOREIGN KEY (refund_request_id)
        REFERENCES credit_refund_requests(id) ON DELETE RESTRICT,
    FOREIGN KEY (stripe_event_id)
        REFERENCES stripe_webhook_events(stripe_event_id) ON DELETE RESTRICT,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CHECK (
        (
            entry_type = 'purchase'
            AND bucket = 'purchased'
            AND amount_micro > 0
            AND payment_order_id IS NOT NULL
            AND refund_request_id IS NULL
            AND stripe_event_id IS NOT NULL
            AND request_digest IS NULL
            AND actor_user_id IS NULL
            AND reference_type IS NULL
            AND reference_id IS NULL
        )
        OR (
            entry_type = 'refund'
            AND bucket = 'purchased'
            AND amount_micro < 0
            AND payment_order_id IS NOT NULL
            AND refund_request_id IS NOT NULL
            AND stripe_event_id IS NOT NULL
            AND request_digest IS NULL
            AND actor_user_id IS NULL
            AND reference_type IS NULL
            AND reference_id IS NULL
        )
        OR (
            entry_type IN ('admin_grant_assign', 'admin_grant_reclaim')
            AND bucket = 'grant'
            AND payment_order_id IS NULL
            AND refund_request_id IS NULL
            AND stripe_event_id IS NULL
            AND request_digest IS NOT NULL
            AND actor_user_id IS NOT NULL
            AND reference_type = 'grant_pool'
            AND reference_id IS NOT NULL
            AND (
                (entry_type = 'admin_grant_assign' AND amount_micro > 0)
                OR (entry_type = 'admin_grant_reclaim' AND amount_micro < 0)
            )
        )
    )
);

CREATE TABLE credit_llm_reservations (
    reservation_id TEXT PRIMARY KEY CHECK (length(trim(reservation_id)) > 0),
    user_id INTEGER NOT NULL,
    run_id TEXT NOT NULL CHECK (length(trim(run_id)) > 0),
    call_index INTEGER NOT NULL CHECK (call_index >= 0),
    provider_id TEXT,
    attempt_index INTEGER NOT NULL DEFAULT 0 CHECK (attempt_index >= 0),
    reserved_micro INTEGER NOT NULL CHECK (reserved_micro > 0),
    reserved_grant_micro INTEGER NOT NULL CHECK (reserved_grant_micro >= 0),
    reserved_purchased_micro INTEGER NOT NULL CHECK (reserved_purchased_micro >= 0),
    settled_micro INTEGER NOT NULL DEFAULT 0 CHECK (settled_micro >= 0),
    actual_micro INTEGER NOT NULL DEFAULT 0 CHECK (actual_micro >= 0),
    outstanding_micro INTEGER NOT NULL DEFAULT 0 CHECK (outstanding_micro >= 0),
    outstanding_recovered_micro INTEGER NOT NULL DEFAULT 0
        CHECK (outstanding_recovered_micro >= 0),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'settled', 'released')),
    operation_key TEXT NOT NULL UNIQUE CHECK (length(trim(operation_key)) > 0),
    request_digest TEXT NOT NULL CHECK (length(trim(request_digest)) > 0),
    evidence_json TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (reserved_micro = reserved_grant_micro + reserved_purchased_micro),
    UNIQUE (user_id, run_id, call_index, attempt_index)
);

CREATE TABLE credit_llm_usage_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reservation_id TEXT NOT NULL,
    run_id TEXT NOT NULL CHECK (length(trim(run_id)) > 0),
    call_index INTEGER NOT NULL CHECK (call_index >= 0),
    bucket TEXT NOT NULL CHECK (bucket IN ('grant', 'purchased')),
    amount_micro INTEGER NOT NULL CHECK (amount_micro < 0),
    operation_key TEXT NOT NULL UNIQUE CHECK (length(trim(operation_key)) > 0),
    evidence_json TEXT NOT NULL CHECK (length(trim(evidence_json)) > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (reservation_id)
        REFERENCES credit_llm_reservations(reservation_id) ON DELETE RESTRICT
);

CREATE TABLE credit_payment_orders (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    client_request_id TEXT NOT NULL,
                    stripe_mode TEXT NOT NULL DEFAULT 'test'
                        CHECK (stripe_mode IN ('test', 'live')),
                    currency TEXT NOT NULL DEFAULT 'usd',
                    amount_usd_cents INTEGER NOT NULL
                        CHECK (amount_usd_cents > 0),
                    credits_micro INTEGER NOT NULL CHECK (credits_micro > 0),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending', 'paid', 'expired', 'failed',
                            'partially_refunded', 'refunded'
                        )),
                    stripe_checkout_session_id TEXT UNIQUE,
                    stripe_payment_intent_id TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    paid_at TEXT,
                    UNIQUE (user_id, client_request_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES credit_accounts(user_id)
                        ON DELETE CASCADE
                );

CREATE TABLE credit_promotion_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_key TEXT NOT NULL CHECK (length(trim(campaign_key)) > 0),
    amount_micro INTEGER NOT NULL CHECK (amount_micro > 0),
    operation_id TEXT NOT NULL UNIQUE CHECK (length(trim(operation_id)) > 0),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(idempotency_key)) > 0),
    request_digest TEXT NOT NULL CHECK (length(trim(request_digest)) > 0),
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at TEXT NOT NULL,
    UNIQUE (campaign_key, user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE credit_refund_requests (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    payment_order_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    requested_by_user_id INTEGER,
                    amount_usd_cents INTEGER NOT NULL
                        CHECK (amount_usd_cents > 0),
                    credits_micro INTEGER NOT NULL CHECK (credits_micro > 0),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending', 'submitted', 'succeeded', 'failed', 'cancelled'
                        )),
                    stripe_refund_id TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    succeeded_at TEXT,
                    FOREIGN KEY (payment_order_id)
                        REFERENCES credit_payment_orders(id) ON DELETE RESTRICT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (requested_by_user_id) REFERENCES users(id)
                        ON DELETE RESTRICT
                );

CREATE TABLE email_change_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                new_email TEXT NOT NULL,
                stage TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                -- Declared but not enforced: SQLite disables FK checks per
                -- connection unless PRAGMA foreign_keys = ON is issued, and
                -- _get_connection() never issues it (turning it on would change
                -- deletion semantics for every table in this store, well beyond
                -- this task). Deleting a user therefore leaves this row orphaned
                -- rather than cascaded away -- tolerable because users.id is
                -- AUTOINCREMENT and ids are never reused, so an orphaned row can
                -- never be misattributed to a different user. The Postgres twin
                -- declares the same constraint and does enforce it.
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

CREATE TABLE equity_timeseries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        equity REAL NOT NULL,
        cash REAL,
        positions_value REAL,
        daily_return REAL, native_equity REAL, native_cash REAL, native_positions_value REAL, fx_rate REAL,
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
                last_used_at TIMESTAMP, agent_type TEXT NOT NULL DEFAULT 'external', description TEXT, pipeline_config TEXT, cash_allocation REAL, backtest_allocation REAL, live_trading_enabled INTEGER NOT NULL DEFAULT 0, runtime_type TEXT NOT NULL DEFAULT 'pipeline', runtime_config TEXT NOT NULL DEFAULT '{}', category TEXT,
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

CREATE TABLE lifecycle_transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL CHECK (length(snapshot_date) = 10),
    from_segment TEXT NOT NULL,
    to_segment TEXT NOT NULL,
    inactive_days INTEGER NOT NULL DEFAULT 0 CHECK (inactive_days >= 0),
    data_quality TEXT NOT NULL DEFAULT 'complete'
        CHECK (data_quality IN ('complete', 'partial')),
    created_at TEXT NOT NULL,
    UNIQUE (user_id, snapshot_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE model_provider_admin_operations (
                operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                source TEXT NOT NULL,
                reason TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                request_digest TEXT NOT NULL DEFAULT '',
                secret_fingerprint TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL
            );

CREATE TABLE model_provider_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

CREATE TABLE password_reset_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                code_hash TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                -- Declared but not enforced on SQLite; the Postgres twin does
                -- enforce it. Same trade-off, same reasons, as the
                -- email_change_requests FK note above.
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

CREATE TABLE platform_model_credentials (
                provider_id TEXT PRIMARY KEY,
                api_key_enc TEXT,
                key_last_four TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'verification_unavailable',
                updated_at TEXT NOT NULL,
                last_verified_at TEXT,
                FOREIGN KEY(provider_id) REFERENCES provider_registry(provider_id) ON DELETE RESTRICT,
                CHECK (status IN ('verified', 'invalid', 'verification_unavailable', 'revoked')),
                CHECK ((status = 'revoked' AND api_key_enc IS NULL) OR (status <> 'revoked' AND api_key_enc IS NOT NULL))
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

CREATE TABLE provider_registry (
                provider_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                adapter_type TEXT NOT NULL,
                approved_base_url TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                byok_enabled INTEGER NOT NULL DEFAULT 1,
                platform_enabled INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'enabled',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (adapter_type IN ('openrouter', 'openai', 'anthropic', 'gemini', 'openai_compatible')),
                CHECK (status IN ('enabled', 'disabled'))
            );

CREATE TABLE research_agent_adds (
                user_id INTEGER NOT NULL,
                template_id TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, template_id)
            );

CREATE TABLE research_artifacts (
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                filename TEXT,
                content_base64 TEXT,
                PRIMARY KEY (run_id, kind)
            );

CREATE TABLE research_runs (
                run_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                template_id TEXT NOT NULL,
                service_run_id TEXT,
                reservation_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                settings_json TEXT NOT NULL,
                email_me INTEGER NOT NULL DEFAULT 0,
                emailed INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            , estimate_micro INTEGER, email_attempts INTEGER NOT NULL DEFAULT 0, email_next_attempt_at TIMESTAMP);

CREATE TABLE run_live_progress (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE stripe_webhook_events (
                    stripe_event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    livemode INTEGER NOT NULL CHECK (livemode IN (0, 1)),
                    object_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    outcome TEXT NOT NULL
                        CHECK (outcome IN ('processed', 'ignored', 'rejected')),
                    reason TEXT,
                    created_at TEXT NOT NULL
                );

CREATE TABLE trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        shares INTEGER,
        price REAL,
        total_value REAL, quantity INTEGER, side TEXT, value REAL, reason TEXT, reference_price REAL, gross_value REAL, slippage_amount REAL, commission REAL, stamp_duty REAL, transfer_fee REAL, total_fees REAL, net_cash_impact REAL, native_price REAL, native_value REAL, native_reference_price REAL, native_gross_value REAL, native_slippage_amount REAL, native_commission REAL, native_stamp_duty REAL, native_transfer_fee REAL, native_total_fees REAL, native_net_cash_impact REAL, fx_rate REAL, market_rule_date TEXT, market_rule_suspended INTEGER, market_rule_closing_limit_state TEXT, market_rule_official_close REAL, market_rule_closing_gate_effective INTEGER,
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
    );

CREATE TABLE user_activity (
    user_id INTEGER PRIMARY KEY,
    activated_at TEXT,
    last_meaningful_activity_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_daily_facts (
    snapshot_date TEXT NOT NULL CHECK (length(snapshot_date) = 10),
    user_id INTEGER NOT NULL,
    lifecycle_segment TEXT NOT NULL,
    lifecycle_reason_code TEXT NOT NULL,
    operational_state TEXT NOT NULL
        CHECK (operational_state IN ('blocked', 'needs_attention', 'healthy')),
    operational_reason_code TEXT,
    tier TEXT NOT NULL
        CHECK (tier IN ('unpaid', 'starter', 'invested', 'high_value')),
    user_group TEXT NOT NULL DEFAULT 'unknown'
        CHECK (user_group IN (
            'internal', 'invited', 'organic', 'competition', 'partner', 'unknown'
        )),
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    runs_requested INTEGER NOT NULL DEFAULT 0 CHECK (runs_requested >= 0),
    runs_completed INTEGER NOT NULL DEFAULT 0 CHECK (runs_completed >= 0),
    runs_failed INTEGER NOT NULL DEFAULT 0 CHECK (runs_failed >= 0),
    runs_cancelled INTEGER NOT NULL DEFAULT 0 CHECK (runs_cancelled >= 0),
    operator_cost_micro INTEGER NOT NULL DEFAULT 0
        CHECK (operator_cost_micro >= 0),
    own_spend_micro INTEGER NOT NULL DEFAULT 0 CHECK (own_spend_micro >= 0),
    data_quality TEXT NOT NULL CHECK (data_quality IN ('complete', 'partial')),
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_entitlements (
                user_id INTEGER PRIMARY KEY,
                max_concurrent_backtests INTEGER NOT NULL DEFAULT 1,
                credits INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                updated_by_admin_id INTEGER,
                -- Declared but not enforced on SQLite; the Postgres twin does
                -- enforce it (set_entitlements maps its violation to
                -- user_not_found). Same trade-off, same reasons, as the
                -- email_change_requests FK note above.
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

CREATE TABLE user_model_credentials (
                credential_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                provider_id TEXT NOT NULL,
                label TEXT NOT NULL,
                api_key_enc TEXT,
                key_last_four TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'verification_unavailable',
                verification_message TEXT NOT NULL DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_verified_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(provider_id) REFERENCES provider_registry(provider_id) ON DELETE RESTRICT,
                CHECK (status IN ('verified', 'invalid', 'verification_unavailable', 'revoked')),
                CHECK ((status = 'revoked' AND api_key_enc IS NULL) OR (status <> 'revoked' AND api_key_enc IS NOT NULL))
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
            , discord_user_id TEXT, avatar TEXT, user_group TEXT NOT NULL DEFAULT 'unknown');
