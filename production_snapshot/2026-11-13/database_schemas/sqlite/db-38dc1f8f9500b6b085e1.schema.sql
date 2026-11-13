-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /var/lib/apex-signup/accounts.sqlite3
-- Database copy: db-38dc1f8f9500b6b085e1.sqlite3
-- Customer records not included.

CREATE INDEX apex_admin_mfa_account ON apex_admin_challenges(account_id,created_at);

CREATE INDEX apex_admin_session_account ON apex_admin_sessions(account_id);

CREATE INDEX apex_crm_account_licenses_owner ON apex_crm_account_licenses(account_id,state);

CREATE INDEX apex_crm_audit_recent ON apex_crm_audit(happened_at);

CREATE INDEX apex_crm_license_decision_recent ON apex_crm_license_decision_audit(evaluated_at);

CREATE INDEX apex_crm_tickets_status ON apex_crm_tickets(status,created_at);

CREATE INDEX apex_customer_worker_nonces_date ON apex_customer_worker_nonces(checked_at);

CREATE INDEX apex_mt5_connections_owner ON apex_mt5_connections(account_id,status);

CREATE INDEX apex_mt5_direct_attempts_rate ON apex_mt5_direct_attempts(account_id,created_at);

CREATE INDEX apex_mt5_event_connection ON apex_mt5_connection_events(connection_id,occurred_at);

CREATE INDEX apex_mt5_link_attempts_account ON apex_mt5_link_attempts(account_id,created_at);

CREATE INDEX apex_mt5_mfa_account_time ON apex_mt5_mfa(account_id,created_at);

CREATE INDEX apex_mt5_mfa_queue ON apex_mt5_mfa(email_state,email_next_at);

CREATE UNIQUE INDEX apex_one_open_license_request ON apex_license_purchase_requests(account_id) WHERE status IN ('requested','contacted');

CREATE INDEX apex_purchase_requests_by_account ON apex_license_purchase_requests(account_id,created_at);

CREATE INDEX apex_sub_history_owner ON apex_crm_subscription_history(account_id,id DESC);

CREATE INDEX client_login_attempts_index ON client_login_attempts(ip_hmac,attempted_at);

CREATE INDEX client_sessions_account ON client_sessions(account_id);

CREATE INDEX email_challenges_lookup ON email_challenges(account_id,purpose,created_at);

CREATE INDEX email_outbox_queue ON email_outbox(state,next_at);

CREATE INDEX email_rate_lookup ON email_rate_events(ip_hmac,created_at);

CREATE INDEX rate_events_lookup ON rate_events(ip_hmac,event_at);

CREATE TABLE abutron_removed_connection_events_archive_20261109 (id INTEGER PRIMARY KEY,connection_id TEXT,account_id TEXT,event TEXT,occurred_at INTEGER,detail TEXT,archived_at TEXT);

CREATE TABLE abutron_v4_6207_activation_revision (
 connection_id TEXT PRIMARY KEY NOT NULL CHECK(connection_id='d6fc2524ec373b8d1bc278a8be3ec635'),
 revision INTEGER NOT NULL CHECK(revision>=1),
 desired_enabled INTEGER NOT NULL CHECK(desired_enabled IN (0,1)),
 effective_enabled INTEGER NOT NULL CHECK(effective_enabled IN (0,1)),
 connection_status TEXT NOT NULL,
 ack_revision INTEGER,
 ack_expires_utc INTEGER,
 updated_utc TEXT NOT NULL,
 last_event TEXT NOT NULL,
 CHECK(ack_revision IS NULL OR ack_revision=revision)
);

CREATE TABLE abutron_v4_6207_direct_intents(
 signal_id TEXT PRIMARY KEY CHECK(length(signal_id)=64),
 account_id TEXT NOT NULL,
 worker_nonce TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1),
 request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
 expires_utc INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('APPROVED','CLAIMED','SEND_UNKNOWN')),
 created_utc INTEGER NOT NULL,
 updated_utc INTEGER NOT NULL
);

CREATE TABLE abutron_v4_6207_send_lease (
 signal_id TEXT PRIMARY KEY, lease_id TEXT NOT NULL UNIQUE,
 revision INTEGER NOT NULL CHECK(revision>=1), request_digest TEXT NOT NULL,
 created_utc INTEGER NOT NULL, expires_utc INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('CLAIMED','SEND_UNKNOWN','RECONCILED')),
 updated_utc INTEGER NOT NULL);

CREATE TABLE abutron_v4_7593_exact_intent (signal_id TEXT PRIMARY KEY, source_decision_id TEXT NOT NULL,nonce TEXT NOT NULL, request_digest TEXT NOT NULL, native_check_digest TEXT NOT NULL,revision INTEGER NOT NULL, expires_utc INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('APPROVED','CLAIMED','SEND_UNKNOWN','BROKER_RECONCILED','REJECTED')),lease TEXT, created_utc INTEGER NOT NULL, updated_utc INTEGER NOT NULL);

CREATE TABLE abutron_v4_9244_exact_intent (signal_id TEXT PRIMARY KEY, source_decision_id TEXT NOT NULL,nonce TEXT NOT NULL, request_digest TEXT NOT NULL, native_check_digest TEXT NOT NULL,revision INTEGER NOT NULL, expires_utc INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('APPROVED','CLAIMED','SEND_UNKNOWN','BROKER_RECONCILED','REJECTED')),lease TEXT, created_utc INTEGER NOT NULL, updated_utc INTEGER NOT NULL);

CREATE TABLE account_email_delivery(
        job_id TEXT PRIMARY KEY REFERENCES email_outbox(id) ON DELETE CASCADE,
        last_event TEXT NOT NULL,updated_at INTEGER NOT NULL);

CREATE TABLE account_email_verification(
        account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        verified_at INTEGER NOT NULL);

CREATE TABLE accounts(
            id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            country TEXT NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending_review','approved','rejected','disabled')),
            demo_execution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(demo_execution_enabled=0),
            live_execution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(live_execution_enabled=0)
        );

CREATE TABLE apex_admin_audit(
            id INTEGER PRIMARY KEY,
            event TEXT NOT NULL,
            account_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            details TEXT NOT NULL);

CREATE TABLE apex_admin_challenges(
            challenge_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            delivered_at INTEGER,
            consumed_at INTEGER);

CREATE TABLE apex_admin_mail_jobs(
            challenge_id TEXT PRIMARY KEY REFERENCES apex_admin_challenges(challenge_id) ON DELETE CASCADE,
            status TEXT NOT NULL CHECK(status IN ('queued','sending','sent','failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL);

CREATE TABLE apex_admin_roles(
            account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role='SUPERADMIN'),
            granted_email TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            email_verified_at TEXT);

CREATE TABLE apex_admin_sessions(
            token_hash TEXT PRIMARY KEY,
            parent_session_hash TEXT NOT NULL,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL);

CREATE TABLE apex_crm_account_licenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
        platform TEXT NOT NULL CHECK(platform IN ('MT5','cTrader')),
        environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
        account_reference TEXT NOT NULL, broker_server TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('assigned','paused')),
        expires_on TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(account_id,broker,platform,environment,account_reference,broker_server)
    );

CREATE TABLE apex_crm_audit(
         id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL, subject_id TEXT,
         action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', happened_at TEXT NOT NULL);

CREATE TABLE apex_crm_broker_catalog(
         broker TEXT NOT NULL, platform TEXT NOT NULL, accepting_requests INTEGER NOT NULL DEFAULT 1
         CHECK(accepting_requests IN (0,1)),
         notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
         PRIMARY KEY(broker,platform));

CREATE TABLE apex_crm_license_decision_audit(
       id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, connection_id TEXT,
       action TEXT NOT NULL, decision TEXT NOT NULL,
       reason TEXT NOT NULL, evaluated_at TEXT NOT NULL
    );

CREATE TABLE apex_crm_license_revocations(
       account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
       revoked_at TEXT NOT NULL, revoked_by TEXT NOT NULL,
       reason TEXT NOT NULL, cleared_at TEXT, cleared_by TEXT
    );

CREATE TABLE apex_crm_licenses(
         account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
         license_code TEXT NOT NULL UNIQUE, plan TEXT NOT NULL CHECK(plan IN ('Starter','Professional','Enterprise')),
         status TEXT NOT NULL CHECK(status IN ('active','paused','expired')),
         seats INTEGER NOT NULL DEFAULT 1 CHECK(seats BETWEEN 1 AND 500),
         expires_on TEXT, internal_notes TEXT NOT NULL DEFAULT '',
         created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE apex_crm_profiles(
         account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
         segment TEXT NOT NULL DEFAULT 'standard' CHECK(segment IN ('standard','vip','business')),
         tags TEXT NOT NULL DEFAULT '', internal_notes TEXT NOT NULL DEFAULT '',
         previously_active INTEGER NOT NULL DEFAULT 0 CHECK(previously_active IN (0,1)),
         updated_at TEXT NOT NULL);

CREATE TABLE apex_crm_subscription_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL,action TEXT NOT NULL,
 old_record TEXT NOT NULL,new_record TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);

CREATE TABLE apex_crm_subscriptions(
         account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
         plan TEXT NOT NULL, currency TEXT NOT NULL CHECK(currency IN ('USD','ZAR','EUR','GBP')),
         amount_minor INTEGER NOT NULL CHECK(amount_minor BETWEEN 0 AND 100000000),
         billing_interval TEXT NOT NULL CHECK(billing_interval IN ('monthly','quarterly','annual','one_time')),
         status TEXT NOT NULL CHECK(status IN ('trial','active','paused','cancelled')),
         renewal_on TEXT, updated_at TEXT NOT NULL);

CREATE TABLE apex_crm_tickets(
         id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
         subject TEXT NOT NULL, priority TEXT NOT NULL CHECK(priority IN ('low','normal','high')),
         status TEXT NOT NULL CHECK(status IN ('open','in_progress','resolved')),
         internal_notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE apex_customer_worker_nonces(
        nonce TEXT PRIMARY KEY,checked_at INTEGER NOT NULL);

CREATE TABLE apex_license_purchase_requests(
        id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        requested_plan TEXT NOT NULL CHECK(requested_plan IN ('Starter','Professional','Enterprise')),
        requested_seats INTEGER NOT NULL CHECK(requested_seats BETWEEN 1 AND 500),
        client_note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL CHECK(status IN ('requested','contacted','activated','cancelled')),
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        activation_at TEXT,activated_by TEXT,external_payment_reference TEXT, quoted_amount_minor INTEGER, quoted_currency TEXT, quoted_interval TEXT);

CREATE TABLE apex_live_trading_requests(
       connection_id TEXT PRIMARY KEY REFERENCES apex_mt5_connections(id) ON DELETE CASCADE,
       requested_enabled INTEGER NOT NULL CHECK(requested_enabled IN (0,1)),
       updated_at INTEGER NOT NULL,
       status TEXT NOT NULL
    );

CREATE TABLE apex_mt5_connection_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      connection_id TEXT NOT NULL REFERENCES apex_mt5_connections(id),
      account_id TEXT NOT NULL, event TEXT NOT NULL,
      occurred_at INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT ''
    );

CREATE TABLE apex_mt5_connections(
       id TEXT PRIMARY KEY,
       account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
       broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
       environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
       account_reference TEXT NOT NULL, broker_server TEXT NOT NULL,
       status TEXT NOT NULL CHECK(status IN ('CONNECTING','CONNECTED','DISCONNECTED','ERROR')),
       broker_verified_at INTEGER, worker_binding TEXT,
       created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
       UNIQUE(account_id,broker,environment,account_reference,broker_server)
    );

CREATE TABLE apex_mt5_direct_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL,
        connection_id TEXT NOT NULL,created_at INTEGER NOT NULL);

CREATE TABLE apex_mt5_link_attempts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id TEXT NOT NULL, created_at INTEGER NOT NULL
    );

CREATE TABLE apex_mt5_mfa(
       id TEXT PRIMARY KEY,
       account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
       connection_id TEXT NOT NULL REFERENCES apex_mt5_connections(id) ON DELETE CASCADE,
       session_hash TEXT NOT NULL,
       created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
       attempts INTEGER NOT NULL DEFAULT 0,
       verified_at INTEGER, consumed_at INTEGER,
       email_state TEXT NOT NULL DEFAULT 'queued'
          CHECK(email_state IN ('queued','sending','sent','failed')),
       email_attempts INTEGER NOT NULL DEFAULT 0,
       email_next_at INTEGER NOT NULL,
       email_sent_at INTEGER
    );

CREATE TABLE apex_trade_control_audit(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       account_id TEXT NOT NULL, connection_id TEXT NOT NULL,
       requested_enabled INTEGER NOT NULL CHECK(requested_enabled IN (0,1)),
       outcome TEXT NOT NULL, occurred_at INTEGER NOT NULL
    );

CREATE TABLE apex_trade_controls(
       connection_id TEXT PRIMARY KEY REFERENCES apex_mt5_connections(id) ON DELETE CASCADE,
       desired_enabled INTEGER NOT NULL DEFAULT 0 CHECK(desired_enabled IN (0,1)),
       effective_enabled INTEGER NOT NULL DEFAULT 0 CHECK(effective_enabled IN (0,1)),
       updated_at INTEGER NOT NULL,
       last_error TEXT
    );

CREATE TABLE apex_trial_entitlements(
        account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        started_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
        CHECK(expires_at=started_at+86400));

CREATE TABLE apex_trial_seats(
        account_id TEXT PRIMARY KEY REFERENCES apex_trial_entitlements(account_id) ON DELETE CASCADE,
        broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
        platform TEXT NOT NULL CHECK(platform IN ('MT5','cTrader')),
        environment TEXT NOT NULL CHECK(environment='DEMO'),
        account_reference TEXT NOT NULL,broker_server TEXT NOT NULL,
        allocated_at INTEGER NOT NULL);

CREATE TABLE broker_link_requests(
          id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
          platform TEXT NOT NULL CHECK(platform IN ('MT5','cTrader')),
          environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
          account_reference TEXT NOT NULL, broker_server TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('verification_pending','oauth_pending')),
          created_at TEXT NOT NULL,
          execution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(execution_enabled=0),
          owner_verified INTEGER NOT NULL DEFAULT 0 CHECK(owner_verified=0),
          UNIQUE(account_id,broker,platform,environment,account_reference,broker_server));

CREATE TABLE client_login_attempts(
          id INTEGER PRIMARY KEY,ip_hmac TEXT NOT NULL, attempted_at INTEGER NOT NULL);

CREATE TABLE client_sessions(
          token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL);

CREATE TABLE consent_receipts(
            receipt_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
            document TEXT NOT NULL, document_sha256 TEXT NOT NULL,
            version TEXT NOT NULL, accepted_at TEXT NOT NULL,
            ip_hmac TEXT NOT NULL, user_agent TEXT NOT NULL,
            acknowledgement INTEGER NOT NULL CHECK(acknowledgement=1),
            UNIQUE(account_id,document)
        );

CREATE TABLE email_challenges(
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset')),
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        consumed_at INTEGER);

CREATE TABLE email_outbox(
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        challenge_id TEXT REFERENCES email_challenges(id),
        purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset','welcome','broker_notice','security')),
        state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','sending','sent','failed')),
        attempts INTEGER NOT NULL DEFAULT 0, next_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL, sent_at INTEGER, provider_message_id TEXT);

CREATE TABLE email_rate_events(
            id INTEGER PRIMARY KEY,ip_hmac TEXT NOT NULL,created_at INTEGER NOT NULL);

CREATE TABLE rate_events(
            id INTEGER PRIMARY KEY, ip_hmac TEXT NOT NULL, event_at INTEGER NOT NULL
        );

CREATE TABLE resend_webhook_events(
        svix_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,
        provider_message_id TEXT,received_at INTEGER NOT NULL);

CREATE TABLE sqlite_sequence(name,seq);

CREATE TRIGGER abutron_v4_6207_connection_delete AFTER DELETE ON apex_mt5_connections
WHEN OLD.id='d6fc2524ec373b8d1bc278a8be3ec635' BEGIN
 UPDATE abutron_v4_6207_activation_revision SET revision=revision+1,connection_status='DELETED',
 desired_enabled=0,effective_enabled=0,ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONNECTION_DELETE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=OLD.id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;

CREATE TRIGGER abutron_v4_6207_connection_update AFTER UPDATE ON apex_mt5_connections
WHEN NEW.id='d6fc2524ec373b8d1bc278a8be3ec635' AND (NEW.status IS NOT OLD.status OR NEW.worker_binding IS NOT OLD.worker_binding OR (NEW.broker_verified_at IS NULL) IS NOT (OLD.broker_verified_at IS NULL) OR NEW.account_id IS NOT OLD.account_id OR NEW.broker IS NOT OLD.broker OR NEW.environment IS NOT OLD.environment OR NEW.account_reference IS NOT OLD.account_reference OR NEW.broker_server IS NOT OLD.broker_server) BEGIN
 UPDATE abutron_v4_6207_activation_revision SET revision=revision+1,
 connection_status=NEW.status,ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONNECTION_UPDATE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=NEW.id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;

CREATE TRIGGER abutron_v4_6207_ctrl_delete AFTER DELETE ON apex_trade_controls
WHEN OLD.connection_id='d6fc2524ec373b8d1bc278a8be3ec635' BEGIN
 UPDATE abutron_v4_6207_activation_revision SET revision=revision+1,desired_enabled=0,
 effective_enabled=0, ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONTROL_DELETE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=OLD.connection_id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;

CREATE TRIGGER abutron_v4_6207_ctrl_insert AFTER INSERT ON apex_trade_controls
WHEN NEW.connection_id='d6fc2524ec373b8d1bc278a8be3ec635' BEGIN
 UPDATE abutron_v4_6207_activation_revision SET revision=revision+1,
 desired_enabled=NEW.desired_enabled, effective_enabled=NEW.effective_enabled,
 ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONTROL_INSERT',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=NEW.connection_id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;

CREATE TRIGGER abutron_v4_6207_ctrl_update AFTER UPDATE ON apex_trade_controls
WHEN NEW.connection_id='d6fc2524ec373b8d1bc278a8be3ec635' AND (NEW.desired_enabled IS NOT OLD.desired_enabled OR NEW.effective_enabled IS NOT OLD.effective_enabled) BEGIN
 UPDATE abutron_v4_6207_activation_revision SET revision=revision+1,
 desired_enabled=NEW.desired_enabled, effective_enabled=NEW.effective_enabled,
 ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONTROL_UPDATE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=NEW.connection_id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;

CREATE TRIGGER apex_trial_mt5_verified_insert
              AFTER INSERT ON apex_mt5_connections
              WHEN NEW.status='CONNECTED' AND NEW.environment='DEMO'
                 AND NEW.broker_verified_at IS NOT NULL
                 AND length(trim(COALESCE(NEW.worker_binding,'')))>0
                 AND EXISTS (
                   SELECT 1 FROM accounts a JOIN account_email_verification v
                   ON v.account_id=a.id WHERE a.id=NEW.account_id AND a.status='approved')
              BEGIN
                INSERT OR IGNORE INTO apex_trial_entitlements(account_id,started_at,expires_at)
                SELECT NEW.account_id,CAST(strftime('%s','now') AS INTEGER),
                       CAST(strftime('%s','now') AS INTEGER)+86400
                WHERE NOT EXISTS (
                  SELECT 1 FROM apex_crm_licenses WHERE account_id=NEW.account_id);
                INSERT OR IGNORE INTO apex_trial_seats(
                  account_id,broker,platform,environment,account_reference,broker_server,allocated_at)
                SELECT NEW.account_id,NEW.broker,'MT5',NEW.environment,
                       NEW.account_reference,NEW.broker_server,CAST(strftime('%s','now') AS INTEGER)
                FROM apex_trial_entitlements t WHERE t.account_id=NEW.account_id
                  AND t.expires_at>CAST(strftime('%s','now') AS INTEGER)
                  AND NOT EXISTS (
                   SELECT 1 FROM apex_crm_licenses WHERE account_id=NEW.account_id);
              END;

CREATE TRIGGER apex_trial_mt5_verified_update
              AFTER UPDATE OF status,broker_verified_at,worker_binding ON apex_mt5_connections
              WHEN NEW.status='CONNECTED' AND NEW.environment='DEMO'
                 AND NEW.broker_verified_at IS NOT NULL
                 AND length(trim(COALESCE(NEW.worker_binding,'')))>0
                 AND EXISTS (
                   SELECT 1 FROM accounts a JOIN account_email_verification v
                   ON v.account_id=a.id WHERE a.id=NEW.account_id AND a.status='approved')
              BEGIN
                INSERT OR IGNORE INTO apex_trial_entitlements(account_id,started_at,expires_at)
                SELECT NEW.account_id,CAST(strftime('%s','now') AS INTEGER),
                       CAST(strftime('%s','now') AS INTEGER)+86400
                WHERE NOT EXISTS (
                  SELECT 1 FROM apex_crm_licenses WHERE account_id=NEW.account_id);
                INSERT OR IGNORE INTO apex_trial_seats(
                  account_id,broker,platform,environment,account_reference,broker_server,allocated_at)
                SELECT NEW.account_id,NEW.broker,'MT5',NEW.environment,
                       NEW.account_reference,NEW.broker_server,CAST(strftime('%s','now') AS INTEGER)
                FROM apex_trial_entitlements t WHERE t.account_id=NEW.account_id
                  AND t.expires_at>CAST(strftime('%s','now') AS INTEGER)
                  AND NOT EXISTS (
                   SELECT 1 FROM apex_crm_licenses WHERE account_id=NEW.account_id);
              END;

CREATE TRIGGER apex_trial_owner_exclusion
          BEFORE INSERT ON apex_trial_entitlements
          WHEN EXISTS (SELECT 1 FROM apex_admin_roles
                       WHERE account_id=NEW.account_id AND role='SUPERADMIN')
          BEGIN SELECT RAISE(IGNORE); END;

CREATE TRIGGER apex_trial_owner_seat_exclusion
          BEFORE INSERT ON apex_trial_seats
          WHEN EXISTS (SELECT 1 FROM apex_admin_roles
                       WHERE account_id=NEW.account_id AND role='SUPERADMIN')
          BEGIN SELECT RAISE(IGNORE); END;
