--
-- PostgreSQL database dump
--

\restrict K7TCm6uewNpewTPiiyzC7jQu9B0o3F6zUTW8Tdop6lG8BU9E6GkR9UuCfgnWA5Y

-- Dumped from database version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_events (
    id uuid NOT NULL,
    actor_customer_id uuid,
    action character varying(120) NOT NULL,
    entity_type character varying(80) NOT NULL,
    entity_id character varying(120),
    payload json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: billing_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.billing_plans (
    id uuid NOT NULL,
    code character varying(80) NOT NULL,
    display_name character varying(160) NOT NULL,
    product character varying(10) NOT NULL,
    currency character varying(3) NOT NULL,
    price_minor integer NOT NULL,
    broker_discount_percent integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: brokers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.brokers (
    id uuid NOT NULL,
    slug character varying(80) NOT NULL,
    display_name character varying(160) NOT NULL,
    adapter_key character varying(80) NOT NULL,
    api_base_url character varying(500),
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    id uuid NOT NULL,
    email character varying(320) NOT NULL,
    full_name character varying(200) NOT NULL,
    phone character varying(50),
    password_hash character varying(255) NOT NULL,
    role character varying(8) NOT NULL,
    is_active boolean NOT NULL,
    broker_referral_verified boolean NOT NULL,
    broker_referral_slug character varying(80),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: devices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.devices (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    platform character varying(7) NOT NULL,
    device_id character varying(255) NOT NULL,
    push_token text,
    app_version character varying(40),
    is_active boolean NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: licenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.licenses (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    trading_account_id uuid NOT NULL,
    product character varying(10) NOT NULL,
    status character varying(9) NOT NULL,
    source character varying(80) NOT NULL,
    starts_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: mt5_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mt5_credentials (
    id uuid NOT NULL,
    trading_account_id uuid NOT NULL,
    encrypted_password text NOT NULL,
    key_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: mt5_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mt5_sessions (
    id uuid NOT NULL,
    trading_account_id uuid NOT NULL,
    agent_session_id character varying(120),
    status character varying(32) NOT NULL,
    broker_login character varying(120) NOT NULL,
    server_name character varying(160) NOT NULL,
    agent_url character varying(500) NOT NULL,
    gateway_url character varying(500),
    gateway_port integer,
    terminal_instance character varying(255),
    last_error text,
    last_health_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: notification_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_attempts (
    id uuid NOT NULL,
    notification_id uuid NOT NULL,
    device_id uuid NOT NULL,
    provider character varying(80) NOT NULL,
    status character varying(7) NOT NULL,
    provider_message_id character varying(255),
    error text,
    created_at timestamp with time zone NOT NULL,
    sent_at timestamp with time zone
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    title character varying(180) NOT NULL,
    body text NOT NULL,
    data json NOT NULL,
    status character varying(6) NOT NULL,
    provider_message_id character varying(255),
    created_at timestamp with time zone NOT NULL,
    sent_at timestamp with time zone,
    read_at timestamp with time zone
);


--
-- Name: outbox_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.outbox_events (
    id uuid NOT NULL,
    event_type character varying(120) NOT NULL,
    aggregate_type character varying(80) NOT NULL,
    aggregate_id character varying(120) NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    payload json NOT NULL,
    status character varying(10) NOT NULL,
    attempts integer NOT NULL,
    next_attempt_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone NOT NULL,
    sent_at timestamp with time zone
);


--
-- Name: payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payments (
    id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    provider character varying(80) NOT NULL,
    provider_event_id character varying(255) NOT NULL,
    amount_minor integer NOT NULL,
    currency character varying(3) NOT NULL,
    status character varying(8) NOT NULL,
    raw_event json NOT NULL,
    paid_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscriptions (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    license_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    status character varying(9) NOT NULL,
    provider character varying(80) NOT NULL,
    provider_reference character varying(255),
    amount_minor integer NOT NULL,
    currency character varying(3) NOT NULL,
    discount_percent integer NOT NULL,
    starts_at timestamp with time zone,
    renews_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: trading_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trading_accounts (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    broker_id uuid NOT NULL,
    broker_login character varying(120) NOT NULL,
    server_name character varying(160),
    currency character varying(3) NOT NULL,
    equity_usd numeric(18,2) NOT NULL,
    bot_tier character varying(10) NOT NULL,
    route_reason character varying(255) NOT NULL,
    status character varying(8) NOT NULL,
    last_synced_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alembic_version (version_num) FROM stdin;
0003_mt5_fleet
\.


--
-- Data for Name: audit_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.audit_events (id, actor_customer_id, action, entity_type, entity_id, payload, created_at) FROM stdin;
4ec17bc9-c01b-439c-af78-d3fe24b6f1dd	a25c3b2c-ba99-4b2a-b88b-ae94077b146d	mt5_account_connected	trading_account	2f1938f3-e1a4-49b5-9211-2a505c663166	{"broker": "ic-markets", "login": "53054439", "server": "ICMarketsSC-Demo", "tier": "flipper", "route_reason": "EQUITY_ROUTE_FLIPPER"}	2026-09-20 11:07:12.20411+00
\.


--
-- Data for Name: billing_plans; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.billing_plans (id, code, display_name, product, currency, price_minor, broker_discount_percent, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: brokers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.brokers (id, slug, display_name, adapter_key, api_base_url, is_active, created_at) FROM stdin;
ee1f3787-e178-48f7-a955-4f42e4b884f3	ic-markets	IC Markets	mt5	\N	t	2026-09-20 04:00:58.697777+00
\.


--
-- Data for Name: customers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customers (id, email, full_name, phone, password_hash, role, is_active, broker_referral_verified, broker_referral_slug, created_at, updated_at) FROM stdin;
a25c3b2c-ba99-4b2a-b88b-ae94077b146d	fleet-cert@abutronfx.online	Abutron Fleet Certification	\N	$argon2id$v=19$m=65536,t=3,p=4$odBqoeLGJgTeIfCBpSCLrg$63QF9a3GYShN+vbqiJAaQTFVttGe+zaP3MPdDqRv3BA	CUSTOMER	t	f	\N	2026-09-20 04:16:37.31237+00	2026-09-21 20:24:34.819682+00
\.


--
-- Data for Name: devices; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.devices (id, customer_id, platform, device_id, push_token, app_version, is_active, last_seen_at, created_at) FROM stdin;
\.


--
-- Data for Name: licenses; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.licenses (id, customer_id, trading_account_id, product, status, source, starts_at, expires_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: mt5_credentials; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.mt5_credentials (id, trading_account_id, encrypted_password, key_version, created_at, updated_at) FROM stdin;
09bb225d-458d-427b-b68a-2c0c1276af2e	2f1938f3-e1a4-49b5-9211-2a505c663166	gAAAAABqr75SGgra6_2XM3-2xh68tCRbFjXmtyoh_gh5SEE9rnbIRmhP7m7z63tJlXaPfHpd5kJvOTqKaqjyEwvpLV1KLqkJ_g==	1	2026-09-20 11:06:58.311666+00	2026-09-20 11:06:58.311666+00
\.


--
-- Data for Name: mt5_sessions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.mt5_sessions (id, trading_account_id, agent_session_id, status, broker_login, server_name, agent_url, gateway_url, gateway_port, terminal_instance, last_error, last_health_at, created_at, updated_at) FROM stdin;
10370eb6-0481-4560-9d9b-7d006b468308	2f1938f3-e1a4-49b5-9211-2a505c663166	\N	DISCONNECTED	53054439	ICMarketsSC-Demo	http://127.0.0.1:8180	\N	\N	\N	\N	2026-09-21 20:24:36.704196+00	2026-09-20 11:07:12.211643+00	2026-09-21 20:24:36.706713+00
\.


--
-- Data for Name: notification_attempts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.notification_attempts (id, notification_id, device_id, provider, status, provider_message_id, error, created_at, sent_at) FROM stdin;
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.notifications (id, customer_id, title, body, data, status, provider_message_id, created_at, sent_at, read_at) FROM stdin;
\.


--
-- Data for Name: outbox_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.outbox_events (id, event_type, aggregate_type, aggregate_id, idempotency_key, payload, status, attempts, next_attempt_at, last_error, created_at, sent_at) FROM stdin;
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.payments (id, subscription_id, provider, provider_event_id, amount_minor, currency, status, raw_event, paid_at, created_at) FROM stdin;
\.


--
-- Data for Name: subscriptions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.subscriptions (id, customer_id, license_id, plan_id, status, provider, provider_reference, amount_minor, currency, discount_percent, starts_at, renews_at, cancelled_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: trading_accounts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.trading_accounts (id, customer_id, broker_id, broker_login, server_name, currency, equity_usd, bot_tier, route_reason, status, last_synced_at, created_at, updated_at) FROM stdin;
2f1938f3-e1a4-49b5-9211-2a505c663166	a25c3b2c-ba99-4b2a-b88b-ae94077b146d	ee1f3787-e178-48f7-a955-4f42e4b884f3	53054439	ICMarketsSC-Demo	USD	699.95	FLIPPER	EQUITY_ROUTE_FLIPPER	ACTIVE	2026-09-20 11:06:58.319205+00	2026-09-20 04:18:11.448913+00	2026-09-20 11:07:12.209635+00
\.


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);


--
-- Name: billing_plans billing_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_plans
    ADD CONSTRAINT billing_plans_pkey PRIMARY KEY (id);


--
-- Name: brokers brokers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brokers
    ADD CONSTRAINT brokers_pkey PRIMARY KEY (id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (id);


--
-- Name: licenses licenses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_pkey PRIMARY KEY (id);


--
-- Name: mt5_credentials mt5_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mt5_credentials
    ADD CONSTRAINT mt5_credentials_pkey PRIMARY KEY (id);


--
-- Name: mt5_sessions mt5_sessions_agent_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mt5_sessions
    ADD CONSTRAINT mt5_sessions_agent_session_id_key UNIQUE (agent_session_id);


--
-- Name: mt5_sessions mt5_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mt5_sessions
    ADD CONSTRAINT mt5_sessions_pkey PRIMARY KEY (id);


--
-- Name: notification_attempts notification_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_attempts
    ADD CONSTRAINT notification_attempts_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: outbox_events outbox_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT outbox_events_pkey PRIMARY KEY (id);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: trading_accounts trading_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_pkey PRIMARY KEY (id);


--
-- Name: ix_audit_events_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_action ON public.audit_events USING btree (action);


--
-- Name: ix_audit_events_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_entity_type ON public.audit_events USING btree (entity_type);


--
-- Name: ix_billing_plans_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_billing_plans_code ON public.billing_plans USING btree (code);


--
-- Name: ix_billing_plans_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_plans_product ON public.billing_plans USING btree (product);


--
-- Name: ix_brokers_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_brokers_slug ON public.brokers USING btree (slug);


--
-- Name: ix_customers_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_customers_email ON public.customers USING btree (email);


--
-- Name: ix_devices_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_devices_customer_id ON public.devices USING btree (customer_id);


--
-- Name: ix_devices_customer_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_devices_customer_platform ON public.devices USING btree (customer_id, platform);


--
-- Name: ix_devices_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_devices_device_id ON public.devices USING btree (device_id);


--
-- Name: ix_licenses_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_licenses_customer_id ON public.licenses USING btree (customer_id);


--
-- Name: ix_licenses_trading_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_licenses_trading_account_id ON public.licenses USING btree (trading_account_id);


--
-- Name: ix_mt5_credentials_account; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_mt5_credentials_account ON public.mt5_credentials USING btree (trading_account_id);


--
-- Name: ix_mt5_sessions_account; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_mt5_sessions_account ON public.mt5_sessions USING btree (trading_account_id);


--
-- Name: ix_mt5_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mt5_sessions_status ON public.mt5_sessions USING btree (status);


--
-- Name: ix_notification_attempts_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notification_attempts_device_id ON public.notification_attempts USING btree (device_id);


--
-- Name: ix_notification_attempts_notification_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notification_attempts_notification_id ON public.notification_attempts USING btree (notification_id);


--
-- Name: ix_notifications_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_customer_id ON public.notifications USING btree (customer_id);


--
-- Name: ix_outbox_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_events_event_type ON public.outbox_events USING btree (event_type);


--
-- Name: ix_outbox_events_idempotency_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_outbox_events_idempotency_key ON public.outbox_events USING btree (idempotency_key);


--
-- Name: ix_outbox_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_status_created ON public.outbox_events USING btree (status, created_at);


--
-- Name: ix_payments_provider_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_payments_provider_event_id ON public.payments USING btree (provider_event_id);


--
-- Name: ix_payments_subscription_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_subscription_id ON public.payments USING btree (subscription_id);


--
-- Name: ix_subscriptions_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subscriptions_customer_id ON public.subscriptions USING btree (customer_id);


--
-- Name: ix_subscriptions_customer_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subscriptions_customer_status ON public.subscriptions USING btree (customer_id, status);


--
-- Name: ix_subscriptions_license_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subscriptions_license_id ON public.subscriptions USING btree (license_id);


--
-- Name: ix_subscriptions_license_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subscriptions_license_status ON public.subscriptions USING btree (license_id, status);


--
-- Name: ix_subscriptions_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subscriptions_plan_id ON public.subscriptions USING btree (plan_id);


--
-- Name: ix_trading_accounts_broker_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trading_accounts_broker_id ON public.trading_accounts USING btree (broker_id);


--
-- Name: ix_trading_accounts_broker_login; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_trading_accounts_broker_login ON public.trading_accounts USING btree (broker_id, broker_login);


--
-- Name: ix_trading_accounts_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trading_accounts_customer_id ON public.trading_accounts USING btree (customer_id);


--
-- Name: ix_trading_accounts_customer_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trading_accounts_customer_status ON public.trading_accounts USING btree (customer_id, status);


--
-- Name: audit_events audit_events_actor_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_actor_customer_id_fkey FOREIGN KEY (actor_customer_id) REFERENCES public.customers(id) ON DELETE SET NULL;


--
-- Name: devices devices_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: licenses licenses_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: licenses licenses_trading_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_trading_account_id_fkey FOREIGN KEY (trading_account_id) REFERENCES public.trading_accounts(id) ON DELETE CASCADE;


--
-- Name: mt5_credentials mt5_credentials_trading_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mt5_credentials
    ADD CONSTRAINT mt5_credentials_trading_account_id_fkey FOREIGN KEY (trading_account_id) REFERENCES public.trading_accounts(id) ON DELETE CASCADE;


--
-- Name: mt5_sessions mt5_sessions_trading_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mt5_sessions
    ADD CONSTRAINT mt5_sessions_trading_account_id_fkey FOREIGN KEY (trading_account_id) REFERENCES public.trading_accounts(id) ON DELETE CASCADE;


--
-- Name: notification_attempts notification_attempts_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_attempts
    ADD CONSTRAINT notification_attempts_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: notification_attempts notification_attempts_notification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_attempts
    ADD CONSTRAINT notification_attempts_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: payments payments_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_license_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_license_id_fkey FOREIGN KEY (license_id) REFERENCES public.licenses(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.billing_plans(id);


--
-- Name: trading_accounts trading_accounts_broker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_broker_id_fkey FOREIGN KEY (broker_id) REFERENCES public.brokers(id);


--
-- Name: trading_accounts trading_accounts_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict K7TCm6uewNpewTPiiyzC7jQu9B0o3F6zUTW8Tdop6lG8BU9E6GkR9UuCfgnWA5Y

