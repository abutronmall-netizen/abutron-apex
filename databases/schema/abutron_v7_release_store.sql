--
-- PostgreSQL database dump
--

\restrict V73SAfirrIgdiJUsf5oAIyqrvPF7yOyED9rFbJLNLBFba9vgtRX9gNl4uMSjnMs

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
-- Name: broker_trade_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.broker_trade_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trading_account_id uuid NOT NULL,
    broker_ticket character varying(160) NOT NULL,
    broker_order_id character varying(160),
    symbol character varying(80) NOT NULL,
    direction character varying(4) NOT NULL,
    volume numeric(28,10) NOT NULL,
    lifecycle character varying(8) NOT NULL,
    open_price numeric(28,10) NOT NULL,
    close_price numeric(28,10),
    net_pnl numeric(28,8),
    commission numeric(28,8),
    swap numeric(28,8),
    pnl_currency character varying(3) NOT NULL,
    opened_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    broker_source character varying(48) NOT NULL,
    broker_reconciled_at timestamp with time zone NOT NULL,
    inserted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT broker_trade_history_direction_check CHECK (((direction)::text = ANY ((ARRAY['BUY'::character varying, 'SELL'::character varying])::text[]))),
    CONSTRAINT broker_trade_history_lifecycle_check CHECK (((lifecycle)::text = ANY ((ARRAY['OPEN'::character varying, 'CLOSED'::character varying])::text[]))),
    CONSTRAINT broker_trade_history_open_price_check CHECK ((open_price > (0)::numeric)),
    CONSTRAINT broker_trade_history_volume_check CHECK ((volume > (0)::numeric)),
    CONSTRAINT ck_broker_history_close CHECK (((((lifecycle)::text = 'OPEN'::text) AND (close_price IS NULL) AND (closed_at IS NULL) AND (net_pnl IS NULL)) OR (((lifecycle)::text = 'CLOSED'::text) AND (close_price > (0)::numeric) AND (closed_at IS NOT NULL) AND (closed_at >= opened_at) AND (net_pnl IS NOT NULL))))
);


--
-- Name: TABLE broker_trade_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.broker_trade_history IS 'Empty until genuine broker-backed trades are reconciled; never import historical QA test orders';


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
-- Name: customer_contact_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_contact_profiles (
    customer_id uuid NOT NULL,
    physical_address character varying(400) DEFAULT ''::character varying NOT NULL,
    whatsapp_number character varying(50) DEFAULT ''::character varying NOT NULL,
    whatsapp_same_as_phone boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT valid_physical_address_length CHECK ((length((physical_address)::text) <= 400)),
    CONSTRAINT valid_whatsapp_length CHECK ((length((whatsapp_number)::text) <= 50))
);


--
-- Name: customer_email_optouts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_email_optouts (
    email_hmac character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    consent_basis character varying(80) NOT NULL,
    created_by character varying(80) DEFAULT 'reviewed_root_privacy_operator'::character varying NOT NULL,
    CONSTRAINT email_digest_format CHECK (((email_hmac)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT optout_consent_basis CHECK (((consent_basis)::text = ANY ((ARRAY['user_requested_account_erasure_optout'::character varying, 'user_requested_suppression'::character varying])::text[])))
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
    role character varying(16) NOT NULL,
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
-- Name: prop_firm_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prop_firm_accounts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    customer_id uuid NOT NULL,
    external_reference character varying(160) NOT NULL,
    firm_name character varying(160) NOT NULL,
    program_name character varying(160) NOT NULL,
    phase character varying(24) NOT NULL,
    verified_source character varying(80) NOT NULL,
    source_reconciled_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT prop_firm_accounts_phase_check CHECK (((phase)::text = ANY ((ARRAY['APPLICATION'::character varying, 'EVALUATION'::character varying, 'VERIFICATION'::character varying, 'FUNDED'::character varying, 'FAILED'::character varying, 'CLOSED'::character varying])::text[])))
);


--
-- Name: TABLE prop_firm_accounts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.prop_firm_accounts IS 'External evidence reconciliation only; no payouts, funding, ledgers or legal acceptance supported';


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
-- Name: broker_trade_history broker_trade_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broker_trade_history
    ADD CONSTRAINT broker_trade_history_pkey PRIMARY KEY (id);


--
-- Name: brokers brokers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brokers
    ADD CONSTRAINT brokers_pkey PRIMARY KEY (id);


--
-- Name: customer_contact_profiles customer_contact_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_contact_profiles
    ADD CONSTRAINT customer_contact_profiles_pkey PRIMARY KEY (customer_id);


--
-- Name: customer_email_optouts customer_email_optouts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_email_optouts
    ADD CONSTRAINT customer_email_optouts_pkey PRIMARY KEY (email_hmac);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: devices devices_device_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_device_id_key UNIQUE (device_id);


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
-- Name: prop_firm_accounts prop_firm_accounts_external_reference_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prop_firm_accounts
    ADD CONSTRAINT prop_firm_accounts_external_reference_key UNIQUE (external_reference);


--
-- Name: prop_firm_accounts prop_firm_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prop_firm_accounts
    ADD CONSTRAINT prop_firm_accounts_pkey PRIMARY KEY (id);


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
-- Name: broker_trade_history uq_broker_trade_per_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broker_trade_history
    ADD CONSTRAINT uq_broker_trade_per_account UNIQUE (trading_account_id, broker_ticket);


--
-- Name: idx_broker_trade_account_opened; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_broker_trade_account_opened ON public.broker_trade_history USING btree (trading_account_id, opened_at DESC, id DESC);


--
-- Name: idx_prop_firm_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prop_firm_customer ON public.prop_firm_accounts USING btree (customer_id, created_at DESC, id DESC);


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
-- Name: ix_licenses_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_licenses_customer_id ON public.licenses USING btree (customer_id);


--
-- Name: ix_licenses_trading_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_licenses_trading_account_id ON public.licenses USING btree (trading_account_id);


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
-- Name: broker_trade_history broker_trade_history_trading_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broker_trade_history
    ADD CONSTRAINT broker_trade_history_trading_account_id_fkey FOREIGN KEY (trading_account_id) REFERENCES public.trading_accounts(id) ON DELETE RESTRICT;


--
-- Name: customer_contact_profiles customer_contact_profiles_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_contact_profiles
    ADD CONSTRAINT customer_contact_profiles_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


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
-- Name: prop_firm_accounts prop_firm_accounts_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prop_firm_accounts
    ADD CONSTRAINT prop_firm_accounts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


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

\unrestrict V73SAfirrIgdiJUsf5oAIyqrvPF7yOyED9rFbJLNLBFba9vgtRX9gNl4uMSjnMs

