-- ABUTRON SQLITE SCHEMA ONLY
-- Original: /home/dcagent/abutron-recovery/staging/frontend-builds/isolation/test_only.sqlite
-- Database copy: db-f178cdf6caef8081f10e.sqlite3
-- Customer records not included.

CREATE INDEX ix_audit_events_action ON audit_events (action);

CREATE INDEX ix_audit_events_entity_type ON audit_events (entity_type);

CREATE UNIQUE INDEX ix_billing_plans_code ON billing_plans (code);

CREATE INDEX ix_billing_plans_product ON billing_plans (product);

CREATE UNIQUE INDEX ix_brokers_slug ON brokers (slug);

CREATE UNIQUE INDEX ix_customers_email ON customers (email);

CREATE INDEX ix_devices_customer_id ON devices (customer_id);

CREATE INDEX ix_devices_customer_platform ON devices (customer_id, platform);

CREATE INDEX ix_licenses_customer_id ON licenses (customer_id);

CREATE UNIQUE INDEX ix_licenses_trading_account_id ON licenses (trading_account_id);

CREATE INDEX ix_notification_attempts_device_id ON notification_attempts (device_id);

CREATE INDEX ix_notification_attempts_notification_id ON notification_attempts (notification_id);

CREATE INDEX ix_notifications_customer_id ON notifications (customer_id);

CREATE INDEX ix_outbox_events_event_type ON outbox_events (event_type);

CREATE UNIQUE INDEX ix_outbox_events_idempotency_key ON outbox_events (idempotency_key);

CREATE INDEX ix_outbox_status_created ON outbox_events (status, created_at);

CREATE UNIQUE INDEX ix_payments_provider_event_id ON payments (provider_event_id);

CREATE INDEX ix_payments_subscription_id ON payments (subscription_id);

CREATE INDEX ix_subscriptions_customer_id ON subscriptions (customer_id);

CREATE INDEX ix_subscriptions_customer_status ON subscriptions (customer_id, status);

CREATE INDEX ix_subscriptions_license_id ON subscriptions (license_id);

CREATE INDEX ix_subscriptions_license_status ON subscriptions (license_id, status);

CREATE INDEX ix_subscriptions_plan_id ON subscriptions (plan_id);

CREATE INDEX ix_trading_accounts_broker_id ON trading_accounts (broker_id);

CREATE UNIQUE INDEX ix_trading_accounts_broker_login ON trading_accounts (broker_id, broker_login);

CREATE INDEX ix_trading_accounts_customer_id ON trading_accounts (customer_id);

CREATE INDEX ix_trading_accounts_customer_status ON trading_accounts (customer_id, status);

CREATE TABLE audit_events (
	id UUID NOT NULL, 
	actor_customer_id UUID, 
	action VARCHAR(120) NOT NULL, 
	entity_type VARCHAR(80) NOT NULL, 
	entity_id VARCHAR(120), 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_customer_id) REFERENCES customers (id) ON DELETE SET NULL
);

CREATE TABLE billing_plans (
	id UUID NOT NULL, 
	code VARCHAR(80) NOT NULL, 
	display_name VARCHAR(160) NOT NULL, 
	product VARCHAR(10) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	price_minor INTEGER NOT NULL, 
	broker_discount_percent INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE brokers (
	id UUID NOT NULL, 
	slug VARCHAR(80) NOT NULL, 
	display_name VARCHAR(160) NOT NULL, 
	adapter_key VARCHAR(80) NOT NULL, 
	api_base_url VARCHAR(500), 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE customers (
	id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	phone VARCHAR(50), 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(8) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	broker_referral_verified BOOLEAN NOT NULL, 
	broker_referral_slug VARCHAR(80), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE devices (
	id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	platform VARCHAR(7) NOT NULL, 
	device_id VARCHAR(255) NOT NULL, 
	push_token TEXT, 
	app_version VARCHAR(40), 
	is_active BOOLEAN NOT NULL, 
	last_seen_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	UNIQUE (device_id)
);

CREATE TABLE licenses (
	id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	trading_account_id UUID NOT NULL, 
	product VARCHAR(10) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	source VARCHAR(80) NOT NULL, 
	starts_at DATETIME, 
	expires_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	FOREIGN KEY(trading_account_id) REFERENCES trading_accounts (id) ON DELETE CASCADE
);

CREATE TABLE notification_attempts (
	id UUID NOT NULL, 
	notification_id UUID NOT NULL, 
	device_id UUID NOT NULL, 
	provider VARCHAR(80) NOT NULL, 
	status VARCHAR(7) NOT NULL, 
	provider_message_id VARCHAR(255), 
	error TEXT, 
	created_at DATETIME NOT NULL, 
	sent_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(notification_id) REFERENCES notifications (id) ON DELETE CASCADE, 
	FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
);

CREATE TABLE notifications (
	id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	title VARCHAR(180) NOT NULL, 
	body TEXT NOT NULL, 
	data JSON NOT NULL, 
	status VARCHAR(6) NOT NULL, 
	provider_message_id VARCHAR(255), 
	created_at DATETIME NOT NULL, 
	sent_at DATETIME, 
	read_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
);

CREATE TABLE outbox_events (
	id UUID NOT NULL, 
	event_type VARCHAR(120) NOT NULL, 
	aggregate_type VARCHAR(80) NOT NULL, 
	aggregate_id VARCHAR(120) NOT NULL, 
	idempotency_key VARCHAR(255) NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt_at DATETIME, 
	last_error TEXT, 
	created_at DATETIME NOT NULL, 
	sent_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE TABLE payments (
	id UUID NOT NULL, 
	subscription_id UUID NOT NULL, 
	provider VARCHAR(80) NOT NULL, 
	provider_event_id VARCHAR(255) NOT NULL, 
	amount_minor INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	raw_event JSON NOT NULL, 
	paid_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE
);

CREATE TABLE subscriptions (
	id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	license_id UUID NOT NULL, 
	plan_id UUID NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	provider VARCHAR(80) NOT NULL, 
	provider_reference VARCHAR(255), 
	amount_minor INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	discount_percent INTEGER NOT NULL, 
	starts_at DATETIME, 
	renews_at DATETIME, 
	cancelled_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	FOREIGN KEY(license_id) REFERENCES licenses (id) ON DELETE CASCADE, 
	FOREIGN KEY(plan_id) REFERENCES billing_plans (id)
);

CREATE TABLE trading_accounts (
	id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	broker_id UUID NOT NULL, 
	broker_login VARCHAR(120) NOT NULL, 
	server_name VARCHAR(160), 
	currency VARCHAR(3) NOT NULL, 
	equity_usd NUMERIC(18, 2) NOT NULL, 
	bot_tier VARCHAR(10) NOT NULL, 
	route_reason VARCHAR(255) NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	last_synced_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	FOREIGN KEY(broker_id) REFERENCES brokers (id)
);
