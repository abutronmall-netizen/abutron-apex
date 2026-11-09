--
-- PostgreSQL database dump
--

\restrict gjM6mVd9EbceZqhlHbK0aHiaFcz9wPYHe4COuAVzoTX6XhjHeNwbyS3zYiaUeZj

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
-- Data for Name: audit_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.audit_events (id, actor_customer_id, action, entity_type, entity_id, payload, created_at) FROM stdin;
d519c009-4f11-48cc-b09a-7cc96bee5030	992b894c-5709-4aa1-81b1-dd7530cf9a18	owner_root_authorized_superadmin_promotion	customer	992b894c-5709-4aa1-81b1-dd7530cf9a18	{"role":"SUPERADMIN","read_only_public_release":true,"broker_order_enabled":false,"payments_enabled":false,"owner_confirmed":true}	2026-10-22 12:16:23.119148+00
9b9fdbe3-776c-42e5-b993-c439c959685f	\N	V7_OLD_QA_IDENTITIES_QUARANTINED	customer	\N	{"reason" : "user-confirmed both current V7 accounts are old QA", "qa_count" : 2, "approved_real_owner_email" : "abutroncloud@gmail.com", "owner_real_identity_bootstrapped" : false, "financial_or_trading_orders_executed" : false}	2026-10-23 14:03:03.561074+00
42deef0d-b881-42f1-a72c-69d3ffbca193	\N	OWNER_VERIFIED_SUPERADMIN_BOOTSTRAPPED	customer	\N	{"approved_email" : "abutroncloud@gmail.com", "origin" : "new user signup and email proof; explicit user authorization 2026-10-23", "privileged_mfa_required" : true, "financial_broker_trading_permissions" : "LOCKED"}	2026-10-23 14:59:14.836066+00
2355cb70-c02e-46d2-9246-7434155785b2	\N	OWNER_APPROVED_SHANAZ_CUSTOMER_REMOVAL_20261026	customer_account	owner_requested_account_removal_20261026	{"removed_customers" : 1, "user_requested_removed_account" : true, "customer_was_inactive" : true, "no_linked_billing_broker_or_license_records" : true, "predelete_encrypted_backup" : "abutron-v7-20261026T182852Z.pgdump.gpg", "offsite_checksum_readback_pass" : true}	2026-10-26 18:30:25.878208+00
5f7e53d7-0f6c-4ab8-83fe-b052522bafbb	\N	OWNER_APPROVED_PENDING_ACCOUNT_FRESH_SIGNUP_20261026	customer_account	fresh_customer_signup_authorized_20261026	{"deleted_inactive_pending_row" : 1, "customer_consents_to_new_registration_owner_reported" : true, "admin_superadmin_preserved" : true, "post_deletion_customer_total" : 5, "pre_delete_archive" : "abutron-v7-20261026T193528Z.pgdump.gpg", "offsite_backup_readback_pass" : true}	2026-10-26 19:36:42.899478+00
b2f02873-08bd-4dd1-8c03-13fb4756c289	fe7d0d57-cd0a-4747-bf86-235197993ffe	native_deriv_owner_demo_readonly_claim	trading_account	a064cb8d-822e-42b0-8014-ba1bd74f9c3b	{"server": "Deriv-Demo", "mode": "DEMO", "source": "current_root_native_broker_proof", "orders_authorized": false}	2026-10-28 22:00:09.436336+00
\.


--
-- Data for Name: billing_plans; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.billing_plans (id, code, display_name, product, currency, price_minor, broker_discount_percent, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: broker_trade_history; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.broker_trade_history (id, trading_account_id, broker_ticket, broker_order_id, symbol, direction, volume, lifecycle, open_price, close_price, net_pnl, commission, swap, pnl_currency, opened_at, closed_at, broker_source, broker_reconciled_at, inserted_at) FROM stdin;
\.


--
-- Data for Name: brokers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.brokers (id, slug, display_name, adapter_key, api_base_url, is_active, created_at) FROM stdin;
a0390e70-d987-4688-90c8-444774c5e3a5	deriv-existing-owner-mt5-demo	Deriv MT5 Existing Owner DEMO (read-only)	DISABLED_OWNER_DEMO_NO_TRADE	\N	f	2026-10-28 22:00:09.427762+00
\.


--
-- Data for Name: customer_contact_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customer_contact_profiles (customer_id, physical_address, whatsapp_number, whatsapp_same_as_phone, created_at, updated_at) FROM stdin;
427dd060-5972-4489-ae5f-4c120be78b50	18 Fuschia street\nBelglen\nMacassar\n7130	0672268272	f	2026-10-29 04:11:57.312318+00	2026-10-29 04:11:57.312318+00
\.


--
-- Data for Name: customer_email_optouts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customer_email_optouts (email_hmac, created_at, consent_basis, created_by) FROM stdin;
\.


--
-- Data for Name: customers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customers (id, email, full_name, phone, password_hash, role, is_active, broker_referral_verified, broker_referral_slug, created_at, updated_at) FROM stdin;
992b894c-5709-4aa1-81b1-dd7530cf9a18	qa-archived-992b894c57094aa181b1dd7530cf9a18@example.com	DAVID MORGAN WALKER	\N	$argon2id$v=19$m=65536,t=3,p=4$0rG1tJMX/WLzuXJU99Qq/g$cZAOQ2wQwEHnU5otj1AYwuvdgcv8LVVKL9e2gaXZzto	CUSTOMER	f	f	\N	2026-10-22 11:26:44.106799+00	2026-10-23 14:03:03.561074+00
643f472e-5053-477b-bc80-1cbc8c6495f1	qa-archived-643f472e5053477bbc801cbc8c6495f1@example.com	Abutron OG	\N	$argon2id$v=19$m=65536,t=3,p=4$EGwOaOKIenGZ5IeNeDDzIA$GrorSp2fjfRvZGMgMcAX6sk/aA3t7UiRWP1SkQIjStI	CUSTOMER	f	f	\N	2026-10-22 19:03:51.438659+00	2026-10-23 14:03:03.561074+00
e7909abd-8eb4-4378-82a2-59f28c61549c	abutroncloud@gmail.com	DAVID MORGAN WALKER	\N	$argon2id$v=19$m=65536,t=3,p=4$AYJxd/CqyWIzqKbSloBDVg$ZWd2YjnLePE5WCc9PFg0tZUfnabiLBrrURgbpTX7rS4	SUPERADMIN	t	f	\N	2026-10-23 14:53:42.828042+00	2026-10-23 14:59:14.836066+00
fe7d0d57-cd0a-4747-bf86-235197993ffe	abutronmall@gmail.com	DAVID MORGAN WALKER	\N	$argon2id$v=19$m=65536,t=3,p=4$affH4vjsJ99DM2QkY3G4Ww$k92pvT/4Yo/L+zhIbOL4nzlcGWx76UTqT5KV1e2lhUo	CUSTOMER	t	f	\N	2026-10-23 14:04:12.407959+00	2026-10-26 17:58:13.323023+00
8e99a6a9-c791-40ed-aa2e-0a84b4e5687c	shanazhartnick2015@gmail.com	Shanaz	\N	$argon2id$v=19$m=65536,t=3,p=4$JlLT/mCUdHuD+pWde3lJgw$KYMzbW0RLg1lil+K/1EWEHiGn18llXzow2C3zy3HWjM	CUSTOMER	t	f	\N	2026-10-26 19:39:02.27355+00	2026-10-26 19:41:06.951349+00
64e3c551-f060-4ffb-af86-942687172ea8	jeancarterjacobs3@gmail.com	Jean-carter Jacobs	\N	$argon2id$v=19$m=65536,t=3,p=4$Lk8lJ3rQB0bY78DopnF9zg$S10HVPkmWJsoQ8Ao3+woF7mv2S72W4J28F4NRqudeTc	CUSTOMER	t	f	\N	2026-10-26 19:57:23.073115+00	2026-10-26 20:04:39.060295+00
6cefe67e-bd62-4431-b406-66184e3e1482	daylonjacobs2@gmail.com	Daylon Jacobs	\N	$argon2id$v=19$m=65536,t=3,p=4$yRqFW//UrVv5O64e6f2a4w$gxoOXa+Y7f50ttZprQBw/IoJwTtxFccTOL6QrZWBEqo	CUSTOMER	t	f	\N	2026-10-28 02:24:15.593779+00	2026-10-28 02:25:05.500698+00
427dd060-5972-4489-ae5f-4c120be78b50	petersnyders7800@gmail.com	Jenade	0659485249	$argon2id$v=19$m=65536,t=3,p=4$pJg7oNG1+WYzQe9VRFDCgQ$tFcAVljbKbNwbmkemG4KWzIEokC+6NnCERfLuQh06bg	CUSTOMER	t	f	\N	2026-10-26 17:41:57.143949+00	2026-10-29 04:11:57.321054+00
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
-- Data for Name: notification_attempts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.notification_attempts (id, notification_id, device_id, provider, status, provider_message_id, error, created_at, sent_at) FROM stdin;
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.notifications (id, customer_id, title, body, data, status, provider_message_id, created_at, sent_at, read_at) FROM stdin;
e700bfeb-80de-4aec-afbe-0832800ffab8	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | Early breakout	Early breakout for Volatility 10 Index.0 (SELL), observed 2026-10-30T10:00:11.466000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "bff013384766cdc8472a", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T10:00:11.466000Z"}	QUEUED	\N	2026-10-30 10:00:48.282857+00	\N	\N
35b0ecf5-8fd8-403f-ac29-9ccf8a41aa76	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | Early breakout	Early breakout for Volatility 100 Index.0 (BUY), observed 2026-10-30T10:05:11.468000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "49b5a56c0d9e3673acf3", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:05:11.468000Z"}	QUEUED	\N	2026-10-30 10:05:53.956382+00	\N	\N
58034003-dd85-404f-a6c5-50abeb2bc2fe	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO EVENT | Volatility 25 Index.0 | Setup expired	Setup expired for Volatility 25 Index.0 (EVENT), observed 2026-10-30T10:15:11.466000+00:00 UTC. No confirmed entry from this setup. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b5eacbc3a233b9c28475", "signal_version": "9.374", "kind": "SETUP_EXPIRED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": null, "observed_utc": "2026-10-30T10:15:11.466000Z"}	QUEUED	\N	2026-10-30 10:16:08.084611+00	\N	\N
b84ef960-3467-427d-bd02-0a97737e082e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | Retest observed	Retest observed for Volatility 50 Index.0 (BUY), observed 2026-10-30T10:15:11.467000+00:00 UTC. Confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b588cb85ae1b8b304a16", "signal_version": "9.374", "kind": "RETEST_OBSERVED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:15:11.467000Z"}	QUEUED	\N	2026-10-30 10:16:08.087743+00	\N	\N
dfc66918-d4fd-46fe-b244-864d095e80ce	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | Retest observed	Retest observed for Boom 600 Index.0 (BUY), observed 2026-10-30T10:15:11.986000+00:00 UTC. Confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3838f3b3760b132f56c5", "signal_version": "9.374", "kind": "RETEST_OBSERVED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:15:11.986000Z"}	QUEUED	\N	2026-10-30 10:16:08.089066+00	\N	\N
87fef704-ad62-4c2d-a600-966aa8865f30	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | Early breakout	Early breakout for Volatility 10 Index.0 (SELL), observed 2026-10-30T10:20:08.190000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e21f8f8c1f08f3445b23", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T10:20:08.190000Z"}	QUEUED	\N	2026-10-30 10:20:26.481993+00	\N	\N
0d5aa85b-01ca-491f-9270-e21b67699774	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | Early breakout	Early breakout for Crash 1000 Index.0 (SELL), observed 2026-10-30T10:20:08.203000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4cdd480a9892e1ab49d1", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T10:20:08.203000Z"}	QUEUED	\N	2026-10-30 10:20:26.484277+00	\N	\N
cc153f1e-5926-41c4-a7ec-1255d9bb20cd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 1000 Index.0 | Early breakout	Early breakout for Boom 1000 Index.0 (SELL), observed 2026-10-30T10:30:08.196000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5fcca83fd72bc6504bac", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T10:30:08.196000Z"}	QUEUED	\N	2026-10-30 10:31:01.053653+00	\N	\N
e7b06b94-987b-4abc-8d0b-98b1c86a0f4c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | Early breakout	Early breakout for Volatility 75 Index.0 (BUY), observed 2026-10-30T10:35:08.191000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "47d5091d723a4dada5d6", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:35:08.191000Z"}	QUEUED	\N	2026-10-30 10:36:03.427086+00	\N	\N
bcda3a57-0928-4b23-acba-735072f8cbb4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | Early breakout	Early breakout for Volatility 100 Index.0 (BUY), observed 2026-10-30T10:35:08.192000+00:00 UTC. Breakout only. Retest and confirmation still required. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c6e211a942e4bf8ad90b", "signal_version": "9.374", "kind": "EARLY_BREAKOUT", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:35:08.192000Z"}	QUEUED	\N	2026-10-30 10:36:03.434027+00	\N	\N
b3d23032-0afa-45e8-8da8-5fbe01a95c78	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (SELL), observed 2026-10-30T10:45:05.132000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a18463a4ad602fcbaa15", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T10:45:05.132000Z"}	QUEUED	\N	2026-10-30 10:45:22.465957+00	\N	\N
17855623-6d8a-4a59-a2f7-801d152fdd25	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (SELL), observed 2026-10-30T10:45:05.132000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ca6e41a8efb6c56ca0f9", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T10:45:05.132000Z"}	QUEUED	\N	2026-10-30 10:45:22.468594+00	\N	\N
49cf8882-fdd7-47bc-bc8d-d65c9c4bf545	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (BUY), observed 2026-10-30T10:55:01.883000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "643921a7b00b79ccab91", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:55:01.883000Z"}	QUEUED	\N	2026-10-30 10:55:41.591933+00	\N	\N
b547527b-b17c-4640-9894-eb432bd41096	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (BUY), observed 2026-10-30T10:55:01.883000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d6ab55a03abdf6bf8225", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:55:01.883000Z"}	QUEUED	\N	2026-10-30 10:55:41.596279+00	\N	\N
5598cd7d-615b-4fb7-b536-44a85a1893c3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | Broker order requested	Broker order requested for Volatility 10 Index.0 (BUY), observed 2026-10-30T10:55:01.891000+00:00 UTC. Not a fill; broker response pending. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "567104668f3298e69325", "signal_version": "9.374", "kind": "ORDER_SEND_BEGIN", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:55:01.891000Z"}	QUEUED	\N	2026-10-30 10:55:41.598309+00	\N	\N
05119b59-1664-415c-b518-9dccde5fbe8d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | Broker order response	Broker order response for Volatility 10 Index.0 (BUY), observed 2026-10-30T10:55:02.514000+00:00 UTC. Not independently reconciled. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e85879bfe2d1e33203d2", "signal_version": "9.374", "kind": "ORDER_SEND_RESPONSE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:55:02.514000Z"}	QUEUED	\N	2026-10-30 10:55:41.600341+00	\N	\N
1fde50cd-e1a7-4720-b970-ef9dfa1778ee	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | Protected broker position observed	Protected broker position observed for Volatility 10 Index.0 (BUY), observed 2026-10-30T10:55:02.514000+00:00 UTC. EA reported broker position with SL/TP; independently reconciled closure still pending. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ecd0822d629c8acfc2b0", "signal_version": "9.374", "kind": "BROKER_POSITION_PROTECTED_REPORTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T10:55:02.514000Z"}	QUEUED	\N	2026-10-30 10:55:41.602252+00	\N	\N
86974115-5f86-404c-968b-286e6efaa637	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO EVENT | Deriv DEMO | Native broker deal log	Native broker deal log for Deriv DEMO (EVENT), observed 2026-10-30T10:55:02.520000+00:00 UTC. Not independently reconciled. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "92aa0eb38288f362b928", "signal_version": "9.374", "kind": "NATIVE_BROKER_DEAL_LOG_UNRECONCILED", "demo": true, "broker_fill_certified": false, "symbol": null, "side": null, "observed_utc": "2026-10-30T10:55:02.520000Z"}	QUEUED	\N	2026-10-30 10:55:41.60397+00	\N	\N
df8d24ff-9bbe-4647-9df1-1f17340c699f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (BUY), observed 2026-10-30T11:20:01.884000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f938bebdde1fec856f1b", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:20:01.884000Z"}	QUEUED	\N	2026-10-30 11:20:57.428412+00	\N	\N
01739e3d-73cc-4736-b14c-e75a8a8e7c3f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (BUY), observed 2026-10-30T11:20:01.884000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c6c502c894a5b3cc81d6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:20:01.884000Z"}	QUEUED	\N	2026-10-30 11:20:57.43241+00	\N	\N
a5f09343-3b93-4e87-9897-4ef25a3bfc2f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (BUY), observed 2026-10-30T11:20:01.884000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: existing_symbol_position_or_account_orders. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b15f3e7270f4673baa56", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:20:01.884000Z"}	QUEUED	\N	2026-10-30 11:20:57.434031+00	\N	\N
a89952a3-d381-43b3-8578-7ee3861b89bd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (BUY), observed 2026-10-30T11:25:00.251000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6516239f120242eb3eec", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:25:00.251000Z"}	QUEUED	\N	2026-10-30 11:26:02.446807+00	\N	\N
5ad31594-becf-4a6a-b720-91a7c1c31f86	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (BUY), observed 2026-10-30T11:25:00.251000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1b3b5bdd6937def99994", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:25:00.251000Z"}	QUEUED	\N	2026-10-30 11:26:02.449593+00	\N	\N
a1ed2ff8-6d2e-4942-89b9-a20bb3c1e540	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | Broker order requested	Broker order requested for Volatility 75 Index.0 (BUY), observed 2026-10-30T11:25:00.251000+00:00 UTC. Not a fill; broker response pending. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f0bcc9261705c9059f70", "signal_version": "9.374", "kind": "ORDER_SEND_BEGIN", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:25:00.251000Z"}	QUEUED	\N	2026-10-30 11:26:02.451381+00	\N	\N
f61755a3-f218-4e90-8087-b90f10c1b41f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | Broker order response	Broker order response for Volatility 75 Index.0 (BUY), observed 2026-10-30T11:25:00.871000+00:00 UTC. Not independently reconciled. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6cef6c715c23c1d84ee0", "signal_version": "9.374", "kind": "ORDER_SEND_RESPONSE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:25:00.871000Z"}	QUEUED	\N	2026-10-30 11:26:02.452983+00	\N	\N
70d24b0b-868c-43a8-9e72-1546d03bcd86	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | Protected broker position observed	Protected broker position observed for Volatility 75 Index.0 (BUY), observed 2026-10-30T11:25:00.871000+00:00 UTC. EA reported broker position with SL/TP; independently reconciled closure still pending. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f48562d70c932c9105de", "signal_version": "9.374", "kind": "BROKER_POSITION_PROTECTED_REPORTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:25:00.871000Z"}	QUEUED	\N	2026-10-30 11:26:02.45484+00	\N	\N
e68db6d4-5c8b-4b1f-88ae-082d4ab65bfe	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T11:25:00.875000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a23b3b7b698549a3963c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:25:00.875000Z"}	QUEUED	\N	2026-10-30 11:26:02.456416+00	\N	\N
4df10ab7-8b8f-4870-88b0-6a2827b939d5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T11:25:00.875000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7120a7efe6154194b91c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:25:00.875000Z"}	QUEUED	\N	2026-10-30 11:26:02.458334+00	\N	\N
20c94eaa-86a7-457f-84ac-b2f288bedf0c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T11:25:00.875000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1b0da9c8de1470643260", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:25:00.875000Z"}	QUEUED	\N	2026-10-30 11:26:02.459966+00	\N	\N
3c60bb50-1ec8-4c94-b345-35dfe3e035d4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO EVENT | Deriv DEMO | Native broker deal log	Native broker deal log for Deriv DEMO (EVENT), observed 2026-10-30T11:25:00.879000+00:00 UTC. Not independently reconciled. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5e04d4ae003b425da6d0", "signal_version": "9.374", "kind": "NATIVE_BROKER_DEAL_LOG_UNRECONCILED", "demo": true, "broker_fill_certified": false, "symbol": null, "side": null, "observed_utc": "2026-10-30T11:25:00.879000Z"}	QUEUED	\N	2026-10-30 11:26:02.461124+00	\N	\N
876cea40-cfd0-4ab2-bc67-6d344d053cba	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T11:30:00.245000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "70511abf35413c1961bc", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:30:00.245000Z"}	QUEUED	\N	2026-10-30 11:30:22.507647+00	\N	\N
c4448fb6-24f9-49c7-8e62-e6b8479e185c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T11:30:00.245000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4ce1966a13eed4dc43c6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:30:00.245000Z"}	QUEUED	\N	2026-10-30 11:30:22.510868+00	\N	\N
a227c71f-b948-476b-8e28-406874bfec69	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T11:30:00.245000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "aa4a271583b02e8f8f16", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:30:00.245000Z"}	QUEUED	\N	2026-10-30 11:30:22.512346+00	\N	\N
01fa1a33-beef-4f75-b6dd-6d4986eecb91	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T11:35:00.246000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8dce35b434005651dec0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:35:00.246000Z"}	QUEUED	\N	2026-10-30 11:35:40.427963+00	\N	\N
443bb9fc-ce28-4997-bb9f-a99ed812711d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T11:35:00.246000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "83f749698719b1a4d5d7", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:35:00.246000Z"}	QUEUED	\N	2026-10-30 11:35:40.430575+00	\N	\N
092be4e6-9b2b-42d3-b1f9-71ec7d86b0d7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T11:35:00.246000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "144136aa1263c1000d82", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:35:00.246000Z"}	QUEUED	\N	2026-10-30 11:35:40.4319+00	\N	\N
3c166755-443d-4326-8c98-21f6cf0d5155	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 600 Index.0 (SELL), observed 2026-10-30T11:40:00.247000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "12d7457cb98a8997618d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:40:00.247000Z"}	QUEUED	\N	2026-10-30 11:40:57.485621+00	\N	\N
7de6940d-64c2-42e1-a4c1-f7c09c673e33	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO order checks started	DEMO order checks started for Boom 600 Index.0 (SELL), observed 2026-10-30T11:40:00.247000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4c49c4f0bce318369fdd", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:40:00.247000Z"}	QUEUED	\N	2026-10-30 11:40:57.490273+00	\N	\N
4279c59a-75ea-4bcd-a33f-db94123c5a48	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 600 Index.0 (SELL), observed 2026-10-30T11:40:00.247000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8ab39d771fcbd00d0a4a", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:40:00.247000Z"}	QUEUED	\N	2026-10-30 11:40:57.492212+00	\N	\N
6edbde5f-aa1d-4677-b48d-ff4f5515cb18	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (BUY), observed 2026-10-30T11:45:00.245000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "90cdb16d37737a9c42a7", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:45:00.245000Z"}	QUEUED	\N	2026-10-30 11:45:02.500177+00	\N	\N
6bb22de6-6adf-46bd-9c83-08bd51e4b30a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (BUY), observed 2026-10-30T11:45:00.245000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "decdc9b0eefa9f071f95", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:45:00.245000Z"}	QUEUED	\N	2026-10-30 11:45:02.503212+00	\N	\N
d92d0e43-921a-42f0-9d65-4a9a92c76e22	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (BUY), observed 2026-10-30T11:45:00.245000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2cc9d2f02866341f9141", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T11:45:00.245000Z"}	QUEUED	\N	2026-10-30 11:45:02.50491+00	\N	\N
21857cde-e9ab-485d-b1f6-50742395afb5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (SELL), observed 2026-10-30T11:45:00.248000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "28a875cb46cf3054f23d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:45:00.248000Z"}	QUEUED	\N	2026-10-30 11:45:02.506317+00	\N	\N
f3dd7f39-2ef8-4766-9c48-93a98a55afa9	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (SELL), observed 2026-10-30T11:45:00.248000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9b88f0a89e1d3e3254c8", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:45:00.248000Z"}	QUEUED	\N	2026-10-30 11:45:02.507848+00	\N	\N
677b8d59-07a9-4a1e-84e9-a566e00d5b5a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (SELL), observed 2026-10-30T11:45:00.248000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2aa725dce61ae7938fe0", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:45:00.248000Z"}	QUEUED	\N	2026-10-30 11:45:02.509104+00	\N	\N
8462628b-e618-4bd4-aa4c-70a8e3aef58a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 600 Index.0 (SELL), observed 2026-10-30T11:50:00.247000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c4002e5a062f772ab65d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:50:00.247000Z"}	QUEUED	\N	2026-10-30 11:50:17.576016+00	\N	\N
c1a8b957-34dc-44cc-9a86-8d5920aba4bc	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO order checks started	DEMO order checks started for Boom 600 Index.0 (SELL), observed 2026-10-30T11:50:00.247000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3fadfe87480e24e33b4a", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:50:00.247000Z"}	QUEUED	\N	2026-10-30 11:50:17.579645+00	\N	\N
fde7434b-f52d-4aa4-9dc5-43e822e23514	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 600 Index.0 (SELL), observed 2026-10-30T11:50:00.247000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "67f4b65e3cce3b16c223", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T11:50:00.247000Z"}	QUEUED	\N	2026-10-30 11:50:17.581384+00	\N	\N
9233dff4-e2af-4c11-b8c2-ddf5f106e23b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 600 Index.0 (SELL), observed 2026-10-30T12:00:15.249000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "54ff0ca86804a2b572a8", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:00:15.249000Z"}	QUEUED	\N	2026-10-30 12:00:52.559595+00	\N	\N
d3d522f7-4ed5-4f35-86d7-9283b41a34d9	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO order checks started	DEMO order checks started for Boom 600 Index.0 (SELL), observed 2026-10-30T12:00:15.249000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "cfb0d7e7c259395a4cd6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:00:15.249000Z"}	QUEUED	\N	2026-10-30 12:00:52.563206+00	\N	\N
589cc099-a93a-4a54-8d03-796197b1bdb3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 600 Index.0 (SELL), observed 2026-10-30T12:00:15.249000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ac4a57bf79c35c5d40b9", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:00:15.249000Z"}	QUEUED	\N	2026-10-30 12:00:52.565164+00	\N	\N
28330f5c-5d65-4067-a677-7d4de3e6b610	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO EVENT | Deriv DEMO | Native broker deal log	Native broker deal log for Deriv DEMO (EVENT), observed 2026-10-30T12:01:14.873000+00:00 UTC. Not independently reconciled. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c8592d7354faa2945635", "signal_version": "9.374", "kind": "NATIVE_BROKER_DEAL_LOG_UNRECONCILED", "demo": true, "broker_fill_certified": false, "symbol": null, "side": null, "observed_utc": "2026-10-30T12:01:14.873000Z"}	QUEUED	\N	2026-10-30 12:01:57.429502+00	\N	\N
cc66a6dc-e2ba-4c09-b698-240fda651a86	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (BUY), observed 2026-10-30T12:05:15.311000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7ed26c9e14dcfeb6868e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T12:05:15.311000Z"}	QUEUED	\N	2026-10-30 12:06:01.374073+00	\N	\N
a1d1f411-9e22-4c43-938a-1c5a202e3783	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (BUY), observed 2026-10-30T12:05:15.311000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7e204c9f2fe1d4059a18", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T12:05:15.311000Z"}	QUEUED	\N	2026-10-30 12:06:01.377156+00	\N	\N
9d99b5e8-90c2-4ab8-a922-0e61ab26cac3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (BUY), observed 2026-10-30T12:05:15.311000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b5865a88cb35e2d91840", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T12:05:15.311000Z"}	QUEUED	\N	2026-10-30 12:06:01.379038+00	\N	\N
c9b9f928-8365-4ac7-a44c-c02f8ba98ddd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (SELL), observed 2026-10-30T12:05:15.742000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6d5e0f920c28748c8c60", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:05:15.742000Z"}	QUEUED	\N	2026-10-30 12:06:01.380708+00	\N	\N
58073337-333b-4c27-93d7-ff2432915a8a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (SELL), observed 2026-10-30T12:05:15.742000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e5afca92fef530c2bb0c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:05:15.742000Z"}	QUEUED	\N	2026-10-30 12:06:01.382359+00	\N	\N
5cfa7a84-592f-41ce-9f82-2dd69ef998f2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (SELL), observed 2026-10-30T12:05:15.743000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: shared_daily_exposure_cap. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8389cee362aff65106e6", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:05:15.743000Z"}	QUEUED	\N	2026-10-30 12:06:01.384239+00	\N	\N
0deb0e76-a0f9-46d5-95b6-50ca19aaabdf	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T12:05:15.743000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "27ed155da3382fcb4f15", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:05:15.743000Z"}	QUEUED	\N	2026-10-30 12:06:01.385847+00	\N	\N
7522cbeb-b81d-43d1-bd9f-e333937dd0ec	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T12:05:15.743000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2ee6acd95e1379399fcb", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:05:15.743000Z"}	QUEUED	\N	2026-10-30 12:06:01.388357+00	\N	\N
a0006142-e836-4547-b87a-152b2fccc27b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T12:05:15.743000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: shared_daily_exposure_cap. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2468543a8696c70c7a9f", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:05:15.743000Z"}	QUEUED	\N	2026-10-30 12:06:01.390146+00	\N	\N
e611ef5d-dbb9-450f-b240-efcc17ba0b35	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T12:15:00.246000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "690d3e9461cdc7f3f8d5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:15:00.246000Z"}	QUEUED	\N	2026-10-30 12:15:24.044159+00	\N	\N
74c7fcc9-1d60-47b9-a730-2479d86d43a4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T12:15:00.246000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "24d4b2b3bda2b8fe340b", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:15:00.246000Z"}	QUEUED	\N	2026-10-30 12:15:24.04798+00	\N	\N
b4040344-43e5-48cf-b035-6dcc255f9b9c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T12:15:00.246000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: shared_daily_exposure_cap. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "11289a7451f7412b6842", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:15:00.246000Z"}	QUEUED	\N	2026-10-30 12:15:24.049617+00	\N	\N
4c7a1375-f90c-4670-a5ba-aad27010e4ae	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T12:25:00.245000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6f60fe691f76c3867f6c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:25:00.245000Z"}	QUEUED	\N	2026-10-30 12:26:00.187432+00	\N	\N
a658c13c-65d2-4f09-a04d-cfe1c03e1d03	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T12:25:00.245000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f3b79eb5edbcc3c7ffff", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:25:00.245000Z"}	QUEUED	\N	2026-10-30 12:26:00.190758+00	\N	\N
6a752468-e2e6-4cb5-b60e-288ae4e4c034	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T12:25:00.245000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ff6e8c689ca698ea19ec", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:25:00.245000Z"}	QUEUED	\N	2026-10-30 12:26:00.192227+00	\N	\N
8dd04840-81cb-4a8d-aed5-f8253a83c592	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (SELL), observed 2026-10-30T12:30:04.846000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b38615d1b69955007161", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:30:04.846000Z"}	QUEUED	\N	2026-10-30 12:31:02.571344+00	\N	\N
27a48cf8-2426-412a-8269-78d98eb26d45	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (SELL), observed 2026-10-30T12:30:04.846000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5f28fb5877d461bb90e5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:30:04.846000Z"}	QUEUED	\N	2026-10-30 12:31:02.574559+00	\N	\N
6a358c92-8ec9-46a0-8afd-7c388191706b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (SELL), observed 2026-10-30T12:30:04.847000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: shared_daily_exposure_cap. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "fd742086ef0d80685251", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:30:04.847000Z"}	QUEUED	\N	2026-10-30 12:31:02.576196+00	\N	\N
db0b0190-93a0-4452-9a4b-70452e58fd43	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (SELL), observed 2026-10-30T12:35:07.257000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e63987796d57a7a26e10", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:35:07.257000Z"}	QUEUED	\N	2026-10-30 12:35:19.499581+00	\N	\N
0fa40384-a467-421c-90c7-d7a37cf1b59f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (SELL), observed 2026-10-30T12:35:07.257000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "33990cc2af5eb219d618", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:35:07.257000Z"}	QUEUED	\N	2026-10-30 12:35:19.502615+00	\N	\N
fbce4aea-3e94-4895-8efa-62ccd7be2c6e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (SELL), observed 2026-10-30T12:35:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "81eebc80473029056732", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:35:07.257000Z"}	QUEUED	\N	2026-10-30 12:35:19.505631+00	\N	\N
15b9f3aa-0240-42f3-9b9c-0a807179b76b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (SELL), observed 2026-10-30T12:35:07.259000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1601f4d7c96528bc2d91", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:35:07.259000Z"}	QUEUED	\N	2026-10-30 12:35:19.507763+00	\N	\N
158e750b-aef8-4376-9ad4-578a8a3f70af	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (SELL), observed 2026-10-30T12:35:07.259000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6488473740bbac542f7e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:35:07.259000Z"}	QUEUED	\N	2026-10-30 12:35:19.509864+00	\N	\N
671edd10-f75b-492e-a0e5-ea7009b214d5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (SELL), observed 2026-10-30T12:35:07.259000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d97bb98714fe23b7ee2d", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:35:07.259000Z"}	QUEUED	\N	2026-10-30 12:35:19.511481+00	\N	\N
8655b61a-75f3-49d9-909d-84e9911dfeb5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (SELL), observed 2026-10-30T12:40:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f0ad16aff97d078599bc", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:40:07.256000Z"}	QUEUED	\N	2026-10-30 12:40:33.26995+00	\N	\N
ee478eb5-8f49-491f-ab59-1f485612d89b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (SELL), observed 2026-10-30T12:40:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "cb74f47f4fe432f97027", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:40:07.256000Z"}	QUEUED	\N	2026-10-30 12:40:33.273326+00	\N	\N
92b5593a-a2e6-4ccf-bc06-c2a2861b150e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (SELL), observed 2026-10-30T12:40:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "434329297c24be6bc167", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T12:40:07.256000Z"}	QUEUED	\N	2026-10-30 12:40:33.274991+00	\N	\N
9c5e1e29-a139-4578-8aa3-b5993b5a0019	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (BUY), observed 2026-10-30T13:10:07.255000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "0724082db14203610094", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:10:07.255000Z"}	QUEUED	\N	2026-10-30 13:11:01.289902+00	\N	\N
7cf78f4d-f66b-4564-843a-303dd86ca7ff	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (BUY), observed 2026-10-30T13:10:07.255000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3b6f38bcde6d0d7202a4", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:10:07.255000Z"}	QUEUED	\N	2026-10-30 13:11:01.293482+00	\N	\N
8fb92b41-08de-4620-b6d6-f2b0bed7bbdd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (BUY), observed 2026-10-30T13:10:07.255000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b596a3bab1f46308cf37", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:10:07.255000Z"}	QUEUED	\N	2026-10-30 13:11:01.297464+00	\N	\N
d01afee9-af74-4537-bb48-e858a9b4d831	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (SELL), observed 2026-10-30T13:10:07.255000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5aa1c6d0efb218f3dfb6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:10:07.255000Z"}	QUEUED	\N	2026-10-30 13:11:01.300154+00	\N	\N
2075184b-d072-412e-8300-8f502ea9bfb2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (SELL), observed 2026-10-30T13:10:07.255000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1b46cb7ee4d6ecafeb1e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:10:07.255000Z"}	QUEUED	\N	2026-10-30 13:11:01.302277+00	\N	\N
dab82e85-00a1-442e-8e90-3e2f4262f436	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (SELL), observed 2026-10-30T13:10:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f1a52a250bf9fdc25c02", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:10:07.256000Z"}	QUEUED	\N	2026-10-30 13:11:01.304195+00	\N	\N
c97e8465-3742-4c90-b1ed-0513a386ccdc	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (BUY), observed 2026-10-30T13:10:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ea4a60a86e5ebfee04cb", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:10:07.256000Z"}	QUEUED	\N	2026-10-30 13:11:01.306032+00	\N	\N
8126ec3d-86e7-4502-9c1f-38064ac36776	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (BUY), observed 2026-10-30T13:10:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ae305fcb9c90cb4cdee7", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:10:07.256000Z"}	QUEUED	\N	2026-10-30 13:11:01.307497+00	\N	\N
8f5682d3-1ec6-40f3-bc32-55c7765870f4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (BUY), observed 2026-10-30T13:10:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "dbcae6e538dcd7dd7c23", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:10:07.257000Z"}	QUEUED	\N	2026-10-30 13:11:01.308863+00	\N	\N
b56341e8-414c-481c-b198-5085f6df588f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (SELL), observed 2026-10-30T13:15:07.258000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6ae2abcfd76e5d7bd2f5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:15:07.258000Z"}	QUEUED	\N	2026-10-30 13:15:12.5688+00	\N	\N
a12f5ece-924b-48d1-b4f1-3c6442580788	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (SELL), observed 2026-10-30T13:15:07.258000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "972ec4de05679c2c0f72", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:15:07.258000Z"}	QUEUED	\N	2026-10-30 13:15:12.572616+00	\N	\N
1351a422-739c-432b-a0b3-26297ca39b22	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (SELL), observed 2026-10-30T13:15:07.258000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7231a48cbf7dede2c15c", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:15:07.258000Z"}	QUEUED	\N	2026-10-30 13:15:12.574083+00	\N	\N
12c64e42-1a3b-4a84-8b37-9b7831a99ea2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (BUY), observed 2026-10-30T13:20:07.255000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "98d81d0874ca755d63b5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:20:07.255000Z"}	QUEUED	\N	2026-10-30 13:20:37.532173+00	\N	\N
aa19bc14-1388-4639-bdc0-a55877d906f4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (BUY), observed 2026-10-30T13:20:07.255000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9f5b32f9474e279866f3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:20:07.255000Z"}	QUEUED	\N	2026-10-30 13:20:37.535415+00	\N	\N
e6719063-db18-4429-aade-38e4e5789ad1	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (BUY), observed 2026-10-30T13:20:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2cc89d19cc7d8f3258c4", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:20:07.256000Z"}	QUEUED	\N	2026-10-30 13:20:37.537037+00	\N	\N
c2756f33-87ce-45b5-bf12-f477a5953623	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 600 Index.0 (BUY), observed 2026-10-30T13:30:07.257000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "355a040f98275bbd80f0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:30:07.257000Z"}	QUEUED	\N	2026-10-30 13:31:02.700008+00	\N	\N
a7a0ca53-ae7b-46cc-ae1c-dd820fb07e7e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | DEMO order checks started	DEMO order checks started for Boom 600 Index.0 (BUY), observed 2026-10-30T13:30:07.257000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f122f7f9e2533ab14185", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:30:07.257000Z"}	QUEUED	\N	2026-10-30 13:31:02.703735+00	\N	\N
8ed0d806-e119-4553-99d4-ce0a8321cd43	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 600 Index.0 (BUY), observed 2026-10-30T13:30:07.258000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6666b284681fd75af127", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T13:30:07.258000Z"}	QUEUED	\N	2026-10-30 13:31:02.7052+00	\N	\N
e7d610f4-dc6d-4a2c-9f39-457f47d53837	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 1000 Index.0 (SELL), observed 2026-10-30T13:50:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1c6d799bc7e775572382", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:50:07.256000Z"}	QUEUED	\N	2026-10-30 13:51:01.372329+00	\N	\N
144714a3-254d-4be4-8905-f29e594df2b5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 1000 Index.0 | DEMO order checks started	DEMO order checks started for Boom 1000 Index.0 (SELL), observed 2026-10-30T13:50:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "324651b7671216542fd6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:50:07.256000Z"}	QUEUED	\N	2026-10-30 13:51:01.37549+00	\N	\N
02a82bcc-8d40-4ec5-a741-57d5425fb245	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 1000 Index.0 (SELL), observed 2026-10-30T13:50:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9c2bfe81ad448c14e363", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T13:50:07.257000Z"}	QUEUED	\N	2026-10-30 13:51:01.377064+00	\N	\N
989df434-370a-47ca-9471-87e9989f25d2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 1000 Index.0 (BUY), observed 2026-10-30T14:00:07.259000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c710df3fb011c38f68c6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:00:07.259000Z"}	QUEUED	\N	2026-10-30 14:00:39.38437+00	\N	\N
2f1c7345-1c92-4381-9c69-a8610b851b15	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO order checks started	DEMO order checks started for Boom 1000 Index.0 (BUY), observed 2026-10-30T14:00:07.259000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d23614dcb72128d2d169", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:00:07.259000Z"}	QUEUED	\N	2026-10-30 14:00:39.388548+00	\N	\N
0cc38da0-b650-477c-91e1-4652180a234c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 1000 Index.0 (BUY), observed 2026-10-30T14:00:07.259000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b954c0f698f5db04be46", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:00:07.259000Z"}	QUEUED	\N	2026-10-30 14:00:39.390472+00	\N	\N
354878bf-7934-4acf-9840-c546fe285a91	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (SELL), observed 2026-10-30T14:15:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "297226c3d39b12049d6b", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:15:07.256000Z"}	QUEUED	\N	2026-10-30 14:16:01.462134+00	\N	\N
b9bc7b73-8203-460d-9c81-bdb8a4f17c98	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (SELL), observed 2026-10-30T14:15:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "0f34860475abb83cb3f0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:15:07.256000Z"}	QUEUED	\N	2026-10-30 14:16:01.465762+00	\N	\N
d9ad9465-b983-4df9-a5f6-4fc93fe334ef	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (SELL), observed 2026-10-30T14:15:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7c332800e10acacde169", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:15:07.256000Z"}	QUEUED	\N	2026-10-30 14:16:01.467709+00	\N	\N
2b330e35-c1ea-4855-bd2b-bc6bce4974e2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (SELL), observed 2026-10-30T14:25:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f9ac293a36e509d219ad", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:25:07.256000Z"}	QUEUED	\N	2026-10-30 14:25:11.216991+00	\N	\N
86f0f907-f68e-432f-83f8-4475f672ca96	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (SELL), observed 2026-10-30T14:25:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a419bf11c8a0861a14f5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:25:07.256000Z"}	QUEUED	\N	2026-10-30 14:25:11.221198+00	\N	\N
338d06b4-4f0d-4b24-ac46-76ba57a2d7df	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (SELL), observed 2026-10-30T14:25:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "06d4cab0c35aa220e7ba", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:25:07.257000Z"}	QUEUED	\N	2026-10-30 14:25:11.223475+00	\N	\N
97693a0a-2615-47fa-8786-0c74617cb0aa	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 150 Index.0 (BUY), observed 2026-10-30T14:25:07.257000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ce43cc31ac0421e347bc", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:25:07.257000Z"}	QUEUED	\N	2026-10-30 14:25:11.225471+00	\N	\N
843f8a4f-99cd-4087-894d-33963df87662	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 150 Index.0 | DEMO order checks started	DEMO order checks started for Boom 150 Index.0 (BUY), observed 2026-10-30T14:25:07.257000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8447ea2a64d478928a5e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:25:07.257000Z"}	QUEUED	\N	2026-10-30 14:25:11.227391+00	\N	\N
adf455e7-03cb-45e2-aa29-5e69aa7e1963	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 150 Index.0 (BUY), observed 2026-10-30T14:25:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4e59f05676659b3ab85d", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:25:07.257000Z"}	QUEUED	\N	2026-10-30 14:25:11.229161+00	\N	\N
ae8fcfed-5756-41a6-98f5-1d84f4d5dec4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T14:30:07.258000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "50434b9f248a9f192e78", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:30:07.258000Z"}	QUEUED	\N	2026-10-30 14:30:14.776617+00	\N	\N
6e9a77de-5ca1-44d9-95cb-36dfeed0f343	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T14:30:07.258000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2fd7f47982a8d962c055", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:30:07.258000Z"}	QUEUED	\N	2026-10-30 14:30:14.780601+00	\N	\N
9ad871c9-3034-4ca6-9db7-6d8eaabee4b7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T14:30:07.258000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "43f0312265bd4d9c1bc2", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:30:07.258000Z"}	QUEUED	\N	2026-10-30 14:30:14.782274+00	\N	\N
53b4f27c-f687-4e6d-974f-b52090bc5677	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (BUY), observed 2026-10-30T14:35:07.254000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9bcd56b5c4ed6c9402bd", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:35:07.254000Z"}	QUEUED	\N	2026-10-30 14:35:18.449293+00	\N	\N
a84a62ce-6e96-4fa1-95c8-b0ba9660b644	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (BUY), observed 2026-10-30T14:35:07.254000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ea72d2606f417181e1f2", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:35:07.254000Z"}	QUEUED	\N	2026-10-30 14:35:18.452719+00	\N	\N
e0f2268a-a589-4a4a-ae02-4f65707dff80	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (BUY), observed 2026-10-30T14:35:07.254000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3fd56ad7bbcfb432d297", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T14:35:07.254000Z"}	QUEUED	\N	2026-10-30 14:35:18.45449+00	\N	\N
d848ea65-54a5-4c65-adc5-8e407812c1b8	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (SELL), observed 2026-10-30T14:40:07.257000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "030069de8ada4123b823", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:40:07.257000Z"}	QUEUED	\N	2026-10-30 14:40:24.824607+00	\N	\N
1315b1ca-f7b8-404c-922c-148fde40184e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (SELL), observed 2026-10-30T14:40:07.257000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "75aae8042b2db07e1276", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:40:07.257000Z"}	QUEUED	\N	2026-10-30 14:40:24.828806+00	\N	\N
e56a55ec-7ac3-42fb-bd0e-2b2f02b5c3e4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (SELL), observed 2026-10-30T14:40:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a6ebb1115f3a8a73cb14", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:40:07.257000Z"}	QUEUED	\N	2026-10-30 14:40:24.830668+00	\N	\N
ed583e17-4999-4887-bff0-c3b9b5e66207	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T14:45:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "48cee545fcb40f2f2fb3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:45:07.256000Z"}	QUEUED	\N	2026-10-30 14:45:32.71506+00	\N	\N
10fb01a4-c8d7-477a-830b-e44453705514	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T14:45:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "90989d7c71534f4c2f12", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:45:07.256000Z"}	QUEUED	\N	2026-10-30 14:45:32.718391+00	\N	\N
0e060a9c-c426-4880-b07c-6498db30934f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T14:45:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9fb1c3397d97ab5c4284", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T14:45:07.256000Z"}	QUEUED	\N	2026-10-30 14:45:32.719927+00	\N	\N
69808f10-6be9-4fe7-a9a7-0b043471c2a5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T15:00:07.259000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3849bec4a8392cc1e4a5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:00:07.259000Z"}	QUEUED	\N	2026-10-30 15:00:24.665614+00	\N	\N
cb52df2b-5dd9-413a-bfbf-beb3b9d826b7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T15:00:07.259000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "19c22fbc50c61b2bde25", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:00:07.259000Z"}	QUEUED	\N	2026-10-30 15:00:24.66985+00	\N	\N
c5a02a9e-d5fb-4931-92ab-f5d297761bd9	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T15:00:07.260000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3e938b74b6f84c830605", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:00:07.260000Z"}	QUEUED	\N	2026-10-30 15:00:24.672473+00	\N	\N
d50d1ae7-0a4d-49c4-b6c6-e574e3833dcf	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 600 Index.0 (BUY), observed 2026-10-30T15:00:07.262000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9a3a24be84c6d15ba7da", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:00:07.262000Z"}	QUEUED	\N	2026-10-30 15:01:26.142444+00	\N	\N
3056ee13-3aad-4ba7-93ec-49761ae6b657	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | DEMO order checks started	DEMO order checks started for Boom 600 Index.0 (BUY), observed 2026-10-30T15:00:07.262000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6c2a33d049b9c2b26a42", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:00:07.262000Z"}	QUEUED	\N	2026-10-30 15:01:26.145172+00	\N	\N
c030cf5e-cbc3-49b9-91ad-bef9b33e5f5a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 600 Index.0 (BUY), observed 2026-10-30T15:00:07.262000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3fde6f8d8ed8df0e00ed", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:00:07.262000Z"}	QUEUED	\N	2026-10-30 15:01:26.146802+00	\N	\N
234e6e0d-80cc-4334-8007-1ff5390f5098	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (SELL), observed 2026-10-30T15:05:07.255000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ea85db11652ab47ad415", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:05:07.255000Z"}	QUEUED	\N	2026-10-30 15:05:30.35827+00	\N	\N
f04cf878-1481-4bfa-a910-ade83a6710f3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (SELL), observed 2026-10-30T15:05:07.255000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "af369559113aa1d7b3f8", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:05:07.255000Z"}	QUEUED	\N	2026-10-30 15:05:30.360937+00	\N	\N
20ed1f0c-ada1-48ab-8265-0f42d8ff421e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (SELL), observed 2026-10-30T15:05:07.255000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "821a86e9f78be801a513", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:05:07.255000Z"}	QUEUED	\N	2026-10-30 15:05:30.362446+00	\N	\N
d93bf5f2-62f6-4e7a-ac7a-aa7e14cabc85	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (SELL), observed 2026-10-30T15:10:07.254000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2ce6f2a1fbac235b4335", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:10:07.254000Z"}	QUEUED	\N	2026-10-30 15:10:53.808844+00	\N	\N
419f0dfb-b49a-418c-b725-6a5abec92496	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (SELL), observed 2026-10-30T15:10:07.254000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "0365219199e53d911f7e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:10:07.254000Z"}	QUEUED	\N	2026-10-30 15:10:53.812392+00	\N	\N
7d91dc7b-e89b-4ad4-982c-1bc27c0a9d88	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (SELL), observed 2026-10-30T15:10:07.255000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c3a36613397d0ec3d884", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:10:07.255000Z"}	QUEUED	\N	2026-10-30 15:10:53.814804+00	\N	\N
d8fd8bad-2a80-4af0-bd86-9fdb676b97fd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (BUY), observed 2026-10-30T15:10:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a672d133f4d6fbbe928b", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:10:07.256000Z"}	QUEUED	\N	2026-10-30 15:10:53.816864+00	\N	\N
957efabf-06f5-4222-a98f-3b18ccd36602	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (BUY), observed 2026-10-30T15:10:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3bf30907048e1c0db20e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:10:07.256000Z"}	QUEUED	\N	2026-10-30 15:10:53.81887+00	\N	\N
a1b6d10c-4b62-439f-9e53-ea185c210157	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (BUY), observed 2026-10-30T15:10:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "46bcaff928752fc84fa9", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:10:07.256000Z"}	QUEUED	\N	2026-10-30 15:10:53.820285+00	\N	\N
3ec1e767-8a33-49f9-8538-1630c82c07c4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T15:15:07.258000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8bee525365f0071737c1", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:15:07.258000Z"}	QUEUED	\N	2026-10-30 15:16:01.250525+00	\N	\N
adb42a8a-9f02-4ee2-a757-cbb4df359eff	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T15:15:07.258000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4e5f778e5dfd765099d5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:15:07.258000Z"}	QUEUED	\N	2026-10-30 15:16:01.254078+00	\N	\N
8d91c965-50ed-41ed-829d-a6d275bc8a5c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T15:15:07.259000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b8d9bc6bb7f0f1cd0d44", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:15:07.259000Z"}	QUEUED	\N	2026-10-30 15:16:01.256151+00	\N	\N
84c91084-c947-464c-bbe8-020244b59a0a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 1000 Index.0 (BUY), observed 2026-10-30T15:15:07.261000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3938344466228546d40d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:15:07.261000Z"}	QUEUED	\N	2026-10-30 15:16:01.258015+00	\N	\N
3bb2e1b4-3c55-45d9-956d-5cb0aa6332b4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO order checks started	DEMO order checks started for Boom 1000 Index.0 (BUY), observed 2026-10-30T15:15:07.261000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "23820e64d1508caadac1", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:15:07.261000Z"}	QUEUED	\N	2026-10-30 15:16:01.259937+00	\N	\N
950b8e63-d84a-4f19-87f6-b9553092860b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 1000 Index.0 (BUY), observed 2026-10-30T15:15:07.262000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "bbd9f1d7d24ef0081b1d", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:15:07.262000Z"}	QUEUED	\N	2026-10-30 15:16:01.26158+00	\N	\N
27c443a7-8adf-49e4-a13f-1e70dc6a481b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (SELL), observed 2026-10-30T15:20:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "aebb54c05ebcea72cac4", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:20:07.256000Z"}	QUEUED	\N	2026-10-30 15:21:03.418236+00	\N	\N
7326b30c-dc99-48d0-a58c-a098a24efbad	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (SELL), observed 2026-10-30T15:20:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7761bedcdbe8d7b327b0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:20:07.256000Z"}	QUEUED	\N	2026-10-30 15:21:03.421666+00	\N	\N
6cc0ed7c-9c12-4336-97fb-f58b1a15f7c0	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (SELL), observed 2026-10-30T15:20:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4c0d7b2b97b561db47cf", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:20:07.256000Z"}	QUEUED	\N	2026-10-30 15:21:03.423906+00	\N	\N
48ffdccd-234c-475c-9886-6726deef86fb	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T15:20:07.257000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "bd4200f64a362bfeb39f", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:20:07.257000Z"}	QUEUED	\N	2026-10-30 15:21:03.425814+00	\N	\N
e9128ced-a887-4c2d-896b-b6c20922b8ec	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T15:20:07.257000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a8933fb1ea5779ea6326", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:20:07.257000Z"}	QUEUED	\N	2026-10-30 15:21:03.427385+00	\N	\N
b32aa5c1-f984-4ae1-89de-ba58326a1023	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T15:20:07.257000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8eba20dbdb110628f420", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:20:07.257000Z"}	QUEUED	\N	2026-10-30 15:21:03.429309+00	\N	\N
418bee91-7ba7-4240-a75d-21246e821d30	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (BUY), observed 2026-10-30T15:30:07.255000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "458d3e2d014984a727e3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.255000Z"}	QUEUED	\N	2026-10-30 15:30:37.561764+00	\N	\N
d52a80de-c7c5-4655-a659-f24eac1b5f6b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (BUY), observed 2026-10-30T15:30:07.255000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "43f0ebff0c32e1000c9c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.255000Z"}	QUEUED	\N	2026-10-30 15:30:37.565391+00	\N	\N
e85f791a-96e9-4401-985d-84c52400c6bd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (BUY), observed 2026-10-30T15:30:07.255000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5802bc4afc7aa2a92370", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.255000Z"}	QUEUED	\N	2026-10-30 15:30:37.567381+00	\N	\N
35db617d-5415-4992-80f9-eba369f7ab90	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (BUY), observed 2026-10-30T15:30:07.256000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4628c9bed77801da0108", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.256000Z"}	QUEUED	\N	2026-10-30 15:30:37.569301+00	\N	\N
da39a459-ff6b-4c2f-aed9-d0cc319ab1c2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (BUY), observed 2026-10-30T15:30:07.256000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ae3552bb6b6ba08214d3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.256000Z"}	QUEUED	\N	2026-10-30 15:30:37.571309+00	\N	\N
0ba3261a-a018-4163-97f6-1b65b56a33de	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (BUY), observed 2026-10-30T15:30:07.256000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "fb037430750cf5edf175", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.256000Z"}	QUEUED	\N	2026-10-30 15:30:37.57271+00	\N	\N
bdc3f16f-21a9-4bd1-95d1-5dedafb2d4ea	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 1000 Index.0 (BUY), observed 2026-10-30T15:30:07.258000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c97ca60bbb2ae9d1d498", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.258000Z"}	QUEUED	\N	2026-10-30 15:31:42.570054+00	\N	\N
c634d59d-2801-4e32-8d4f-1b05d5a7244a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO order checks started	DEMO order checks started for Boom 1000 Index.0 (BUY), observed 2026-10-30T15:30:07.258000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "021b4a36078a14260ce5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.258000Z"}	QUEUED	\N	2026-10-30 15:31:42.572969+00	\N	\N
76282743-2d0a-4d13-83b0-65e8ca1da021	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 1000 Index.0 (BUY), observed 2026-10-30T15:30:07.259000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ffc4e78a929c493a86e3", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T15:30:07.259000Z"}	QUEUED	\N	2026-10-30 15:31:42.575751+00	\N	\N
dbcce919-9ab7-4050-b413-cbdb8109ffaa	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T15:50:00.354000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "78f02ff6abc3eb969d3b", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:50:00.354000Z"}	QUEUED	\N	2026-10-30 15:50:27.608041+00	\N	\N
0344fbd7-3344-4529-9d15-bf0f26ca59d2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T15:50:00.354000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d78b74e6e969e037bed3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:50:00.354000Z"}	QUEUED	\N	2026-10-30 15:50:27.612145+00	\N	\N
0794090b-1461-4c2e-8cbb-d4984957ebb0	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T15:50:00.355000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a36ed0ef40fbf606ee06", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:50:00.355000Z"}	QUEUED	\N	2026-10-30 15:50:27.613747+00	\N	\N
f105a490-892f-4760-b91d-a815043ca35a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T15:55:00.342000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e188615d9aff0a9c8989", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:55:00.342000Z"}	QUEUED	\N	2026-10-30 15:55:52.640337+00	\N	\N
b40d2e9e-4b9e-41ce-838b-e2c6c81d1bbe	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T15:55:00.342000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a1a5b9da1133ae19d0fa", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:55:00.342000Z"}	QUEUED	\N	2026-10-30 15:55:52.644451+00	\N	\N
64cadc8a-5af9-4eab-b4c6-4e996c898105	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T15:55:00.342000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "04aaf3e071717ba359a2", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T15:55:00.342000Z"}	QUEUED	\N	2026-10-30 15:55:52.646166+00	\N	\N
87f5d4e5-2cd6-48af-85df-7f8be1739248	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (BUY), observed 2026-10-30T16:00:00.345000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2ed24f6f4d51123942ca", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:00:00.345000Z"}	QUEUED	\N	2026-10-30 16:01:01.358764+00	\N	\N
9dba3667-e9b3-4c0d-955d-b2f333ee0721	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (BUY), observed 2026-10-30T16:00:00.345000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "65fcb7b9ed27b979a934", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:00:00.345000Z"}	QUEUED	\N	2026-10-30 16:01:01.36287+00	\N	\N
108fcb41-3ba3-4de1-8e77-96c7fa51551f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (BUY), observed 2026-10-30T16:00:00.345000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1a31a14ead96a15ab79b", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:00:00.345000Z"}	QUEUED	\N	2026-10-30 16:01:01.365261+00	\N	\N
5c10a00f-e705-4f85-ad69-4ef9b4b226a0	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 600 Index.0 (BUY), observed 2026-10-30T16:00:00.346000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9bc18d3e5bad5d1a3e12", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:00:00.346000Z"}	QUEUED	\N	2026-10-30 16:01:01.367436+00	\N	\N
80cfc808-4003-4208-ab1b-51f66ae4a636	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 600 Index.0 | DEMO order checks started	DEMO order checks started for Crash 600 Index.0 (BUY), observed 2026-10-30T16:00:00.346000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a3e13d99e4702a2afac5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:00:00.346000Z"}	QUEUED	\N	2026-10-30 16:01:01.369977+00	\N	\N
7e080fd9-b408-4480-95f8-cee0f48118c2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 600 Index.0 (BUY), observed 2026-10-30T16:00:00.347000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a02b450b06499d2c040b", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:00:00.347000Z"}	QUEUED	\N	2026-10-30 16:01:01.371635+00	\N	\N
c3a89656-3866-4802-8146-bc20a01beebd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T16:05:00.343000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8fa3c925b46daef0949a", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:05:00.343000Z"}	QUEUED	\N	2026-10-30 16:05:12.548171+00	\N	\N
dd3df35e-3ce1-43d2-aaac-595f6060414e	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T16:05:00.343000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c2377de6610627105aa4", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:05:00.343000Z"}	QUEUED	\N	2026-10-30 16:05:12.551505+00	\N	\N
faf024e5-999d-45e3-85bb-38f4deb66f8a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T16:05:00.343000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "9ccc996bcc2c16966451", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:05:00.343000Z"}	QUEUED	\N	2026-10-30 16:05:12.553129+00	\N	\N
c103612e-9319-43ff-ab56-8040aae8b7be	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (SELL), observed 2026-10-30T16:20:00.342000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "04265cb34bd36e005512", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:20:00.342000Z"}	QUEUED	\N	2026-10-30 16:21:01.375395+00	\N	\N
004fadeb-a675-47bc-ae00-9a0da59dddff	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (SELL), observed 2026-10-30T16:20:00.342000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "093b1fcaf6ca4a06cbde", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:20:00.342000Z"}	QUEUED	\N	2026-10-30 16:21:01.378973+00	\N	\N
c426298d-2531-4fa0-ac7a-9cbcef632270	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (SELL), observed 2026-10-30T16:20:00.343000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "52425c577b08ce44177c", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:20:00.343000Z"}	QUEUED	\N	2026-10-30 16:21:01.381311+00	\N	\N
78326766-6eaa-489b-ac55-0af1363c7889	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (BUY), observed 2026-10-30T16:20:00.343000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2b9f9c3349fec285a2c5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:20:00.343000Z"}	QUEUED	\N	2026-10-30 16:21:01.383239+00	\N	\N
086b8d0b-9f48-4e0e-a2e6-6f0eef234456	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (BUY), observed 2026-10-30T16:20:00.343000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "370c6c3595177ce4fe35", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:20:00.343000Z"}	QUEUED	\N	2026-10-30 16:21:01.385026+00	\N	\N
288eac75-2671-4770-912a-7895556336b0	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (BUY), observed 2026-10-30T16:20:00.343000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "0b7647b473d28ad622ef", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:20:00.343000Z"}	QUEUED	\N	2026-10-30 16:21:01.386598+00	\N	\N
65e2f693-fff4-4a42-95aa-a7de306f12d7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 150 Index.0 (SELL), observed 2026-10-30T16:25:00.346000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "014141bbce69773919b3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:25:00.346000Z"}	QUEUED	\N	2026-10-30 16:25:12.602218+00	\N	\N
1287bbe9-7a63-413a-8f95-8977f8c6847b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 150 Index.0 | DEMO order checks started	DEMO order checks started for Boom 150 Index.0 (SELL), observed 2026-10-30T16:25:00.346000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "73ceeb1cba7065652e20", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:25:00.346000Z"}	QUEUED	\N	2026-10-30 16:25:12.605725+00	\N	\N
b3c608be-b932-44d1-b999-e04e5ce03101	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 150 Index.0 (SELL), observed 2026-10-30T16:25:00.347000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "09b87148d03920459526", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T16:25:00.347000Z"}	QUEUED	\N	2026-10-30 16:25:12.607359+00	\N	\N
bb695c9f-c9ab-4231-a874-175756390b79	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (BUY), observed 2026-10-30T16:45:00.345000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "af64cd5c8fc00e76e53c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:45:00.345000Z"}	QUEUED	\N	2026-10-30 16:45:02.686286+00	\N	\N
0bed9293-9c1a-4d01-b20e-70708d0e1b53	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (BUY), observed 2026-10-30T16:45:00.345000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "40deacddb7c783ee9f44", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:45:00.345000Z"}	QUEUED	\N	2026-10-30 16:45:02.689757+00	\N	\N
49e6989f-7205-48de-9ce2-050413757ce2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (BUY), observed 2026-10-30T16:45:00.345000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c69936133299b552c27f", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:45:00.345000Z"}	QUEUED	\N	2026-10-30 16:45:02.691893+00	\N	\N
e8f2c49a-a4f3-4603-8e60-bc04514216b9	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 600 Index.0 (BUY), observed 2026-10-30T16:45:00.346000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8a3b28b6245e992380dc", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:45:00.346000Z"}	QUEUED	\N	2026-10-30 16:45:02.693703+00	\N	\N
825103cd-00fc-4dbe-a271-3af870d81090	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 600 Index.0 | DEMO order checks started	DEMO order checks started for Crash 600 Index.0 (BUY), observed 2026-10-30T16:45:00.346000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "349e36d8acd1e723252e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:45:00.346000Z"}	QUEUED	\N	2026-10-30 16:45:02.695385+00	\N	\N
6eccada6-7b84-496a-815c-759aaaec1ac3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 600 Index.0 (BUY), observed 2026-10-30T16:45:00.346000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f140e2242e7d93aea430", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:45:00.346000Z"}	QUEUED	\N	2026-10-30 16:45:02.696908+00	\N	\N
a9002871-3661-402b-891a-4327c53fda95	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (BUY), observed 2026-10-30T16:55:00.345000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "37c6ddb92f35e3267550", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:55:00.345000Z"}	QUEUED	\N	2026-10-30 16:56:01.135445+00	\N	\N
f1ccd3a5-6708-4765-99d1-bcf734cbbb0f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (BUY), observed 2026-10-30T16:55:00.345000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5348121c2e4ec6b23a22", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:55:00.345000Z"}	QUEUED	\N	2026-10-30 16:56:01.138667+00	\N	\N
6b4b07fb-2b6a-46b0-8dc7-f1a504a405d1	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (BUY), observed 2026-10-30T16:55:00.345000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8ac2535171206ede3aed", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T16:55:00.345000Z"}	QUEUED	\N	2026-10-30 16:56:01.140527+00	\N	\N
d8b07eec-81f2-4007-a2cf-19e8a97290b7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (BUY), observed 2026-10-30T17:00:00.343000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c7f9fea5249a9eb84b6c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T17:00:00.343000Z"}	QUEUED	\N	2026-10-30 17:00:03.537336+00	\N	\N
d6b45ef8-27a2-400e-8671-b348cc990759	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (BUY), observed 2026-10-30T17:00:00.343000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "fddb038fd9a6126767f8", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T17:00:00.343000Z"}	QUEUED	\N	2026-10-30 17:00:03.541799+00	\N	\N
af7bfe7c-b588-4694-8863-ed4fcc14ccc8	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (BUY), observed 2026-10-30T17:00:00.343000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "550e8f3fcff6f951fcb2", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T17:00:00.343000Z"}	QUEUED	\N	2026-10-30 17:00:03.543966+00	\N	\N
3e544ab7-6291-41f0-9be2-9bb818abc99d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T17:05:00.344000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "073eaf96ebb9cb494a92", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:05:00.344000Z"}	QUEUED	\N	2026-10-30 17:05:27.5299+00	\N	\N
8e643203-557f-465e-85ff-32012ee6dc92	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T17:05:00.344000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c72a2b0bd6aa23475e03", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:05:00.344000Z"}	QUEUED	\N	2026-10-30 17:05:27.534277+00	\N	\N
c0da698b-6fe0-4216-b189-b92ec5a422c0	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T17:05:00.344000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e54c17f555df0b861574", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:05:00.344000Z"}	QUEUED	\N	2026-10-30 17:05:27.536449+00	\N	\N
ea7510e2-0bf2-4956-b427-2aeeaaa95434	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T17:15:00.342000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "516ebc4d6ad21be78096", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:15:00.342000Z"}	QUEUED	\N	2026-10-30 17:16:01.193135+00	\N	\N
8ecf8cee-4c35-4037-b399-ba478a2d76aa	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T17:15:00.342000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f98e49184a4363de05a5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:15:00.342000Z"}	QUEUED	\N	2026-10-30 17:16:01.196825+00	\N	\N
187a12c5-e269-45b5-b39d-6aacabad9c09	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T17:15:00.342000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f2e0d27e3b03eafb5219", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:15:00.342000Z"}	QUEUED	\N	2026-10-30 17:16:01.19892+00	\N	\N
6422902f-a1f3-4dc5-885e-ce5dc3220199	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (SELL), observed 2026-10-30T17:20:00.344000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "43c5c8c252bee18144bd", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:20:00.344000Z"}	QUEUED	\N	2026-10-30 17:20:02.531534+00	\N	\N
946f2af9-14a6-4b6e-a9ee-dc1567039a8f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (SELL), observed 2026-10-30T17:20:00.344000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3a316a4fcbf42ff05b40", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:20:00.344000Z"}	QUEUED	\N	2026-10-30 17:20:02.536707+00	\N	\N
4b8a75f2-f6ca-46f3-a0f6-59392ee7de43	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (SELL), observed 2026-10-30T17:20:00.344000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d307fb35cf69c0fa200c", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:20:00.344000Z"}	QUEUED	\N	2026-10-30 17:20:02.538963+00	\N	\N
87360302-5257-45a4-b15b-f3e512048cc0	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T17:25:00.342000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ed221025e23613c0b09c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:25:00.342000Z"}	QUEUED	\N	2026-10-30 17:25:22.626176+00	\N	\N
f0951a55-fdfd-4b0d-a3d8-0b8d30e85df2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T17:25:00.342000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c77fe46d3daba92d6015", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:25:00.342000Z"}	QUEUED	\N	2026-10-30 17:25:22.630963+00	\N	\N
bda32afb-df63-4aff-82b6-ab8eb9f571e4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T17:25:00.342000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: account_positions_symbol_or_unprotected_risk. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8910ccb321af8b3f70d6", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T17:25:00.342000Z"}	QUEUED	\N	2026-10-30 17:25:22.63328+00	\N	\N
2c758c78-9c2c-4e38-b154-73e3a7ec5273	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (SELL), observed 2026-10-30T18:05:13.201000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7b6f04371320353c6f27", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:05:13.201000Z"}	QUEUED	\N	2026-10-30 18:06:01.123146+00	\N	\N
d128ad2a-1a72-4010-929f-b47c9979e4ad	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (SELL), observed 2026-10-30T18:05:13.201000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b7946adc83b7926090eb", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:05:13.201000Z"}	QUEUED	\N	2026-10-30 18:06:01.127465+00	\N	\N
635ed06b-89b0-4ba9-bac8-32165c8d3c81	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (SELL), observed 2026-10-30T18:05:13.201000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f3d5ec059df147d71b4f", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:05:13.201000Z"}	QUEUED	\N	2026-10-30 18:06:01.129671+00	\N	\N
4ecc67d1-13d8-41c9-905e-011fb98590f9	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (SELL), observed 2026-10-30T18:15:13.201000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7f48d0d13a944057885d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:15:13.201000Z"}	QUEUED	\N	2026-10-30 18:16:12.587091+00	\N	\N
38ecf53c-0b48-4626-96e5-7e7bca192448	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (SELL), observed 2026-10-30T18:15:13.201000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d2b6f9ef0a0dbaaab416", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:15:13.201000Z"}	QUEUED	\N	2026-10-30 18:16:12.590531+00	\N	\N
488c6924-1bef-4fdb-96fa-374a4fb073ce	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (SELL), observed 2026-10-30T18:15:13.201000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "31da3bb1f558ac04c571", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:15:13.201000Z"}	QUEUED	\N	2026-10-30 18:16:12.592576+00	\N	\N
db386388-2193-45ae-b0e6-67cfcc7c46de	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (BUY), observed 2026-10-30T18:25:01.309000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "763741c0ac49face3010", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:25:01.309000Z"}	QUEUED	\N	2026-10-30 18:25:31.370339+00	\N	\N
c7b337ac-3c73-490e-8307-26ab0452c966	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (BUY), observed 2026-10-30T18:25:01.309000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "27e4a99310c6d6276290", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:25:01.309000Z"}	QUEUED	\N	2026-10-30 18:25:31.374359+00	\N	\N
99744e63-89c8-46d7-a3d5-ffca5402a896	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (BUY), observed 2026-10-30T18:25:01.309000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f0f1c99348ffbf6bdba3", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:25:01.309000Z"}	QUEUED	\N	2026-10-30 18:25:31.376328+00	\N	\N
1005b9f8-a606-492b-965b-2a94f2ba8097	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (SELL), observed 2026-10-30T18:30:01.312000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5451e5c5ac7fbf146e2e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:30:01.312000Z"}	QUEUED	\N	2026-10-30 18:30:45.693054+00	\N	\N
3f0c3695-5713-451e-913c-3650345104fa	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (SELL), observed 2026-10-30T18:30:01.312000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f47a0e05320f2245904d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:30:01.312000Z"}	QUEUED	\N	2026-10-30 18:30:45.697363+00	\N	\N
e0ca73df-bcb4-47c7-a250-b6a88d3de442	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (SELL), observed 2026-10-30T18:30:01.312000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "97df41575eae57074610", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:30:01.312000Z"}	QUEUED	\N	2026-10-30 18:30:45.699317+00	\N	\N
18f87e48-5d26-4f79-96a3-b7cb4bac0d68	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (BUY), observed 2026-10-30T18:40:14.796000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "00835c1bf7cd22c0cbb3", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:40:14.796000Z"}	QUEUED	\N	2026-10-30 18:41:01.213742+00	\N	\N
03f4cd7a-0145-4e11-a80a-41a8d082109c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (BUY), observed 2026-10-30T18:40:14.796000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "67a2a3dc935203c09cb5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:40:14.796000Z"}	QUEUED	\N	2026-10-30 18:41:01.218004+00	\N	\N
d045b272-d21e-436f-a7c0-6a884c744d3f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (BUY), observed 2026-10-30T18:40:14.797000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6f6ffc918b12f4ea580c", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:40:14.797000Z"}	QUEUED	\N	2026-10-30 18:41:01.220097+00	\N	\N
fa3dbdf7-77f5-4c8f-889f-17572d6294d3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T18:50:14.790000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f40d2c5eed0774f2e4ad", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:50:14.790000Z"}	QUEUED	\N	2026-10-30 18:50:23.869498+00	\N	\N
54009bcf-7132-4a10-b77b-30ff61675252	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T18:50:14.790000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4b3c3ba498c9d45c93ff", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:50:14.790000Z"}	QUEUED	\N	2026-10-30 18:50:23.876354+00	\N	\N
7848b840-cba8-4f39-9609-cb8d3c387589	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T18:50:14.791000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "640538d8193b96a5c61f", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:50:14.791000Z"}	QUEUED	\N	2026-10-30 18:50:23.879048+00	\N	\N
3486f172-2ed4-4f00-b408-680fa8a11df8	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T18:55:14.788000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8b18dba97e70f7edbe68", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:55:14.788000Z"}	QUEUED	\N	2026-10-30 18:55:36.794927+00	\N	\N
9146e94a-c758-4abb-90fc-bf43ae9dc3af	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T18:55:14.788000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1c1b24c3a9d6e3be56f5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:55:14.788000Z"}	QUEUED	\N	2026-10-30 18:55:36.798218+00	\N	\N
549d0a1c-e90d-4ee7-be81-7ca1387d53db	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T18:55:14.789000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "046be25474da7a940a97", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:55:14.789000Z"}	QUEUED	\N	2026-10-30 18:55:36.800063+00	\N	\N
10ffad84-3bce-4dc1-9455-8e3febb0112c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 100 Index.0 (BUY), observed 2026-10-30T18:55:14.791000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "69cf1ea0316e289913b8", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:55:14.791000Z"}	QUEUED	\N	2026-10-30 18:55:36.801799+00	\N	\N
c8c123ef-b508-4d9c-a520-f28292b1650d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 100 Index.0 (BUY), observed 2026-10-30T18:55:14.791000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "168cf003ef7e534bf1b0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:55:14.791000Z"}	QUEUED	\N	2026-10-30 18:55:36.803713+00	\N	\N
d58783ed-b36b-49eb-b314-0392ba771eb4	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 100 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 100 Index.0 (BUY), observed 2026-10-30T18:55:14.792000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c18a5257b69145654803", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 100 Index.0", "side": "BUY", "observed_utc": "2026-10-30T18:55:14.792000Z"}	QUEUED	\N	2026-10-30 18:55:36.805526+00	\N	\N
ce8a08c3-a8fa-457b-85c1-d1b998ff3860	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 150 Index.0 (SELL), observed 2026-10-30T18:55:14.794000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4fc77bcdc89f5810b68c", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:55:14.794000Z"}	QUEUED	\N	2026-10-30 18:55:36.807236+00	\N	\N
639e9779-10e8-4689-b9a1-e7933e706162	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 150 Index.0 | DEMO order checks started	DEMO order checks started for Boom 150 Index.0 (SELL), observed 2026-10-30T18:55:14.794000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c5b9e320b4c8cf5eaee8", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:55:14.794000Z"}	QUEUED	\N	2026-10-30 18:55:36.808906+00	\N	\N
d27b0493-6851-48f4-bb57-1141133a18db	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Boom 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 150 Index.0 (SELL), observed 2026-10-30T18:55:14.795000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "38b21a24efcfb1988c5a", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T18:55:14.795000Z"}	QUEUED	\N	2026-10-30 18:55:36.81039+00	\N	\N
53751f5a-1738-4de0-987f-4454f470ce8b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (BUY), observed 2026-10-30T19:00:14.802000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1aa0196550d7326e9da9", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:00:14.802000Z"}	QUEUED	\N	2026-10-30 19:00:52.55434+00	\N	\N
9ea27bce-2574-4e5d-b117-a37bf5e13904	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (BUY), observed 2026-10-30T19:00:14.802000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f5f3dae6ff32e766be95", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:00:14.802000Z"}	QUEUED	\N	2026-10-30 19:00:52.557425+00	\N	\N
e96eb16a-7d5f-481d-9c0b-49480597bbb2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (BUY), observed 2026-10-30T19:00:14.803000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7e8c0c04ccb409be6f29", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:00:14.803000Z"}	QUEUED	\N	2026-10-30 19:00:52.559065+00	\N	\N
2454bd13-a3e8-4f18-8767-24780b863e04	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (BUY), observed 2026-10-30T19:10:14.790000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e1df3a77d12d3772d3ec", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:10:14.790000Z"}	QUEUED	\N	2026-10-30 19:11:01.425834+00	\N	\N
40394ddc-f8da-44cd-a319-189792a94224	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (BUY), observed 2026-10-30T19:10:14.790000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "77a6e1a020f75e32ccb1", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:10:14.790000Z"}	QUEUED	\N	2026-10-30 19:11:01.430643+00	\N	\N
26333eb8-1ad6-426d-bfd2-851a0bd21a02	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (BUY), observed 2026-10-30T19:10:14.791000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c48fdece882e665e8197", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:10:14.791000Z"}	QUEUED	\N	2026-10-30 19:11:01.433139+00	\N	\N
d6feee15-b9e7-4555-99fa-397c7cdb929d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (SELL), observed 2026-10-30T19:20:14.789000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "09add1f3ff1fc3c7e534", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:20:14.789000Z"}	QUEUED	\N	2026-10-30 19:21:17.590626+00	\N	\N
2baa5c76-9e73-40ee-b9d4-e44775d10d5d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (SELL), observed 2026-10-30T19:20:14.789000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ae46d94bbf0b17fb43c9", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:20:14.789000Z"}	QUEUED	\N	2026-10-30 19:21:17.594657+00	\N	\N
0eca03c2-be04-47a5-92b3-6bf4caa90de3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (SELL), observed 2026-10-30T19:20:14.790000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "01ec783ac65200247a26", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:20:14.790000Z"}	QUEUED	\N	2026-10-30 19:21:17.597239+00	\N	\N
871fd8d8-2bce-477f-ac65-a6f89a9d0f52	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Boom 150 Index.0 (BUY), observed 2026-10-30T19:20:14.792000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f021e8fe4b99202a38e4", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:20:14.792000Z"}	QUEUED	\N	2026-10-30 19:21:17.599126+00	\N	\N
e6c5a124-6c73-42c3-937e-508429c18fe9	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 150 Index.0 | DEMO order checks started	DEMO order checks started for Boom 150 Index.0 (BUY), observed 2026-10-30T19:20:14.792000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "1330035341159388db69", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:20:14.792000Z"}	QUEUED	\N	2026-10-30 19:21:17.601038+00	\N	\N
6884f6a1-b9f7-4d2e-874a-9041aab57d57	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Boom 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Boom 150 Index.0 (BUY), observed 2026-10-30T19:20:14.792000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8cfdb2db0043bd40d071", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Boom 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T19:20:14.792000Z"}	QUEUED	\N	2026-10-30 19:21:17.603349+00	\N	\N
21e925de-94e3-4a77-830d-db2406e8cca7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T19:30:14.788000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "ae2be0d5dc499297c52f", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:30:14.788000Z"}	QUEUED	\N	2026-10-30 19:30:29.581245+00	\N	\N
d7fecdbd-7af0-43bf-ba6e-ab90ed590f70	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T19:30:14.788000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "df2582f51bd386151a29", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:30:14.788000Z"}	QUEUED	\N	2026-10-30 19:30:29.584807+00	\N	\N
a9aa5891-b622-4bf6-a5bc-7d65bd7f5de1	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T19:30:14.789000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "220dc0ba3cde74afc78b", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:30:14.789000Z"}	QUEUED	\N	2026-10-30 19:30:29.586609+00	\N	\N
1aa0645b-012f-4475-8d48-96500387b97d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (SELL), observed 2026-10-30T19:35:14.791000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "de87e9a138f8edc59349", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:35:14.791000Z"}	QUEUED	\N	2026-10-30 19:35:37.870172+00	\N	\N
58acf1cb-973c-444b-98e1-a3edc5f4cacc	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (SELL), observed 2026-10-30T19:35:14.791000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "896402d71750bbe775f0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:35:14.791000Z"}	QUEUED	\N	2026-10-30 19:35:37.875114+00	\N	\N
a9a73c72-97f9-42d6-95f3-8082014f6573	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (SELL), observed 2026-10-30T19:35:14.792000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7be5999de360cde2f2ce", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:35:14.792000Z"}	QUEUED	\N	2026-10-30 19:35:37.877304+00	\N	\N
478727a1-4c75-470c-911a-03ada1d524d8	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 75 Index.0 (SELL), observed 2026-10-30T19:45:14.791000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2688f6c0f9d17002f300", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:45:14.791000Z"}	QUEUED	\N	2026-10-30 19:46:01.051179+00	\N	\N
41cc76c5-4b64-4372-b5fb-3976ab7849ee	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 75 Index.0 (SELL), observed 2026-10-30T19:45:14.791000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "f4f773f34584ed8ca690", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:45:14.791000Z"}	QUEUED	\N	2026-10-30 19:46:01.054232+00	\N	\N
091996a0-735d-4a2b-b159-0d71cf01a655	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 75 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 75 Index.0 (SELL), observed 2026-10-30T19:45:14.791000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "fc04b702338bac257e51", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 75 Index.0", "side": "SELL", "observed_utc": "2026-10-30T19:45:14.791000Z"}	QUEUED	\N	2026-10-30 19:46:01.055853+00	\N	\N
a54914fc-5fe2-4e7f-b5a8-7cb57004c57b	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (SELL), observed 2026-10-30T20:05:14.791000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "eadf37f77d85afd8f798", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T20:05:14.791000Z"}	QUEUED	\N	2026-10-30 20:05:22.557326+00	\N	\N
111f4523-398f-4314-b1a2-0a24a5c69b7f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (SELL), observed 2026-10-30T20:05:14.791000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8ae7e7188883a0dd7da0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T20:05:14.791000Z"}	QUEUED	\N	2026-10-30 20:05:22.561857+00	\N	\N
27ff2447-9403-482c-bc9a-9f9f035d87cb	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (SELL), observed 2026-10-30T20:05:14.791000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "576ccf633d2d82427baa", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "SELL", "observed_utc": "2026-10-30T20:05:14.791000Z"}	QUEUED	\N	2026-10-30 20:05:22.563826+00	\N	\N
51c3af22-98b6-4191-9202-43800dd07429	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (BUY), observed 2026-10-30T20:10:14.788000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4ede70112109b7a6d451", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:10:14.788000Z"}	QUEUED	\N	2026-10-30 20:10:33.51289+00	\N	\N
95e72709-9545-40bc-90d3-e243a8a2c80c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (BUY), observed 2026-10-30T20:10:14.788000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "5de0ded2baa6690e4794", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:10:14.788000Z"}	QUEUED	\N	2026-10-30 20:10:33.516847+00	\N	\N
1d9d7aa4-65fd-45ca-a95b-dfe44683716c	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (BUY), observed 2026-10-30T20:10:14.789000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d77e9ae3f076d9239470", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:10:14.789000Z"}	QUEUED	\N	2026-10-30 20:10:33.518609+00	\N	\N
51459242-9e33-40d2-8c83-96bfcff4f3b5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 600 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 600 Index.0 (SELL), observed 2026-10-30T20:20:14.791000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "dbf702de7b79463adcec", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T20:20:14.791000Z"}	QUEUED	\N	2026-10-30 20:20:49.069164+00	\N	\N
2e1d57c9-b056-4dc5-ad79-6e94156662db	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 600 Index.0 | DEMO order checks started	DEMO order checks started for Crash 600 Index.0 (SELL), observed 2026-10-30T20:20:14.791000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4bc52dba470d9a09c7e0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T20:20:14.791000Z"}	QUEUED	\N	2026-10-30 20:20:49.07455+00	\N	\N
4341a40c-8fb5-40e3-b6d2-b4ab3e428482	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Crash 600 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 600 Index.0 (SELL), observed 2026-10-30T20:20:14.791000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6dcb5feb48ed3f577222", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 600 Index.0", "side": "SELL", "observed_utc": "2026-10-30T20:20:14.791000Z"}	QUEUED	\N	2026-10-30 20:20:49.077515+00	\N	\N
8101adda-db1f-4145-ae50-7c06fc7c6a90	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (BUY), observed 2026-10-30T20:35:14.344000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "c84fc1311c45b7a1568f", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:35:14.344000Z"}	QUEUED	\N	2026-10-30 20:36:03.4405+00	\N	\N
29db2383-3d7d-4d3b-a656-f0ac009ff5d2	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (BUY), observed 2026-10-30T20:35:14.344000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "b466a2f25b5a7dc8c2f0", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:35:14.344000Z"}	QUEUED	\N	2026-10-30 20:36:03.444437+00	\N	\N
7f605ec4-aede-486a-840a-1521fe6e9022	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (BUY), observed 2026-10-30T20:35:14.345000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "de634e432d2facf0dc70", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:35:14.345000Z"}	QUEUED	\N	2026-10-30 20:36:03.446691+00	\N	\N
4e62de77-9a25-4153-b239-d30dbc8c0a43	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 300 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 300 Index.0 (BUY), observed 2026-10-30T20:35:14.345000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "989b9cb18c3a38684cc5", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:35:14.345000Z"}	QUEUED	\N	2026-10-30 20:36:03.44864+00	\N	\N
25beca08-43b0-4133-9a4f-b5418897a98d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 300 Index.0 | DEMO order checks started	DEMO order checks started for Crash 300 Index.0 (BUY), observed 2026-10-30T20:35:14.345000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "6f6e83c01d70553d3eaa", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:35:14.345000Z"}	QUEUED	\N	2026-10-30 20:36:03.450864+00	\N	\N
4b3a1b5d-5fd3-4e3f-a386-4646fe6845d1	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 300 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 300 Index.0 (BUY), observed 2026-10-30T20:35:14.346000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "d441377c4b31b6a47bb8", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 300 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:35:14.346000Z"}	QUEUED	\N	2026-10-30 20:36:03.452457+00	\N	\N
a1b78f87-1799-4145-a0e9-d2ba8ec95d07	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (BUY), observed 2026-10-30T20:45:07.749000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "737795bdd21f5742d053", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:45:07.749000Z"}	QUEUED	\N	2026-10-30 20:45:19.509147+00	\N	\N
52983ffd-ec0f-4718-baa8-cb4b4c7520f6	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (BUY), observed 2026-10-30T20:45:07.749000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "2b06b2dbdd160df0a3f6", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:45:07.749000Z"}	QUEUED	\N	2026-10-30 20:45:19.512859+00	\N	\N
4725d9a2-1319-48cd-bdeb-3b95a695e115	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (BUY), observed 2026-10-30T20:45:07.749000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "0eece5d0afd869e41624", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:45:07.749000Z"}	QUEUED	\N	2026-10-30 20:45:19.514924+00	\N	\N
2152dbb1-8605-482c-981d-db35f7d268ea	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 1000 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 1000 Index.0 (BUY), observed 2026-10-30T20:45:07.762000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7c7db2d6433789312910", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:45:07.762000Z"}	QUEUED	\N	2026-10-30 20:45:19.516936+00	\N	\N
faf50247-ecc0-47c5-900b-f53a3a4ae87a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 1000 Index.0 | DEMO order checks started	DEMO order checks started for Crash 1000 Index.0 (BUY), observed 2026-10-30T20:45:07.762000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "14857c5fba0d24afd91e", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:45:07.762000Z"}	QUEUED	\N	2026-10-30 20:45:19.519008+00	\N	\N
aa084592-b3e5-4d2c-8061-54f7acc57870	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 1000 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 1000 Index.0 (BUY), observed 2026-10-30T20:45:07.763000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "131206881e2d98e30317", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 1000 Index.0", "side": "BUY", "observed_utc": "2026-10-30T20:45:07.763000Z"}	QUEUED	\N	2026-10-30 20:45:19.520642+00	\N	\N
8374d53f-753a-4eb7-a602-1f23b5d29c7f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Crash 150 Index.0 (BUY), observed 2026-10-30T21:10:01.022000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4851395f3a484bfaf8fc", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T21:10:01.022000Z"}	QUEUED	\N	2026-10-30 21:10:32.617932+00	\N	\N
4ac242bd-be4e-4d1b-9256-4d93a9450005	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO order checks started	DEMO order checks started for Crash 150 Index.0 (BUY), observed 2026-10-30T21:10:01.022000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "54cb22fb12fd267c8bdb", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T21:10:01.022000Z"}	QUEUED	\N	2026-10-30 21:10:32.622445+00	\N	\N
a1d028d1-b6b6-4fdb-b526-62ddd6a60e2d	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Crash 150 Index.0 | DEMO trade blocked	DEMO trade blocked for Crash 150 Index.0 (BUY), observed 2026-10-30T21:10:01.022000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "71aa5de5e3fd5cf947a3", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Crash 150 Index.0", "side": "BUY", "observed_utc": "2026-10-30T21:10:01.022000Z"}	QUEUED	\N	2026-10-30 21:10:32.625095+00	\N	\N
2a9618fb-dc89-4715-b4ed-711c593f191f	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (SELL), observed 2026-10-30T21:20:01.017000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "04ee9068ee239680fd9b", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:20:01.017000Z"}	QUEUED	\N	2026-10-30 21:21:01.240616+00	\N	\N
d52d0d5d-c5cb-4328-8fcb-10464fd9e428	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (SELL), observed 2026-10-30T21:20:01.017000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "e39f51b2a734f2207428", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:20:01.017000Z"}	QUEUED	\N	2026-10-30 21:21:01.243701+00	\N	\N
8ffa7c3d-737d-4886-bf0a-dc4aec984b39	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (SELL), observed 2026-10-30T21:20:01.017000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "7eb470e5741292149bb6", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:20:01.017000Z"}	QUEUED	\N	2026-10-30 21:21:01.245459+00	\N	\N
8defe92d-e9c6-490f-aa1c-8c829e4a10b5	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 10 Index.0 (SELL), observed 2026-10-30T21:30:01.017000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "eff748b619c32b10e595", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:30:01.017000Z"}	QUEUED	\N	2026-10-30 21:30:22.780241+00	\N	\N
561de453-dae1-4ec3-9c5d-130cd88ea9fd	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 10 Index.0 (SELL), observed 2026-10-30T21:30:01.017000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "3efeda548748f7740e16", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:30:01.017000Z"}	QUEUED	\N	2026-10-30 21:30:22.783467+00	\N	\N
0437a518-c6a9-46ab-b840-d8b6959959b7	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 10 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 10 Index.0 (SELL), observed 2026-10-30T21:30:01.018000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a948df098356d909a1ad", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 10 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:30:01.018000Z"}	QUEUED	\N	2026-10-30 21:30:22.785545+00	\N	\N
e2360556-c6c2-4dd5-89ec-914586ad2078	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 25 Index.0 (BUY), observed 2026-10-30T21:40:01.016000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "58c64480dafa007e22dd", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T21:40:01.016000Z"}	QUEUED	\N	2026-10-30 21:40:39.747723+00	\N	\N
0dc8e0bd-9311-4281-95ba-46e29bb83833	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 25 Index.0 (BUY), observed 2026-10-30T21:40:01.016000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "02c19646e182aff12e51", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T21:40:01.016000Z"}	QUEUED	\N	2026-10-30 21:40:39.752038+00	\N	\N
b0712c9a-abaf-4b6b-b06a-6c53b871a3f3	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 25 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 25 Index.0 (BUY), observed 2026-10-30T21:40:01.017000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: DEMO_PREMIUM_DISCOUNT_ENTRY_VETO. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "375fcde4d57ad9ec1cfc", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 25 Index.0", "side": "BUY", "observed_utc": "2026-10-30T21:40:01.017000Z"}	QUEUED	\N	2026-10-30 21:40:39.75494+00	\N	\N
6204c780-226c-478e-af8b-3ed63ebe2547	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (SELL), observed 2026-10-30T21:40:01.017000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "fd8f9717213a7492ed4d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:40:01.017000Z"}	QUEUED	\N	2026-10-30 21:40:39.758128+00	\N	\N
5e5ff9b1-820f-4425-87f6-0540ebf741d1	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO order checks started	DEMO order checks started for Volatility 50 Index.0 (SELL), observed 2026-10-30T21:40:01.017000+00:00 UTC. Not proof of order submission or broker fill. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "a42706f6933ac5d5a931", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_GATES_STARTED", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:40:01.017000Z"}	QUEUED	\N	2026-10-30 21:40:39.761179+00	\N	\N
b8e6e47f-ce10-4fa9-b314-380d65a84f1a	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO SELL | Volatility 50 Index.0 | DEMO trade blocked	DEMO trade blocked for Volatility 50 Index.0 (SELL), observed 2026-10-30T21:40:01.018000+00:00 UTC. An execution safeguard rejected the order candidate; no order was sent. Gate: BROKER_AUTO_LOT_MINIMUM_UNAFFORDABLE. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "4f5f9554e240cdcce394", "signal_version": "9.374", "kind": "ORDER_HOLD", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "SELL", "observed_utc": "2026-10-30T21:40:01.018000Z"}	QUEUED	\N	2026-10-30 21:40:39.763405+00	\N	\N
228a5e24-00a0-4b37-bbb4-a076435f2e50	fe7d0d57-cd0a-4747-bf86-235197993ffe	Kronos DEMO BUY | Volatility 50 Index.0 | DEMO M5 entry candidate	DEMO M5 entry candidate for Volatility 50 Index.0 (BUY), observed 2026-10-30T22:00:13.688000+00:00 UTC. Closed M5 structure confirmed. Broker risk/permission checks and order submission remain separate. Current observation; still subject to trading safeguards. DEMO only; LIVE not authorized.	{"abutron_event_id": "8a6bf4d44f500c88c03d", "signal_version": "9.374", "kind": "DEMO_BREAKOUT_ORDER_CANDIDATE", "demo": true, "broker_fill_certified": false, "symbol": "Volatility 50 Index.0", "side": "BUY", "observed_utc": "2026-10-30T22:00:13.688000Z"}	QUEUED	\N	2026-10-30 22:01:11.866313+00	\N	\N
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
-- Data for Name: prop_firm_accounts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.prop_firm_accounts (id, customer_id, external_reference, firm_name, program_name, phase, verified_source, source_reconciled_at, created_at) FROM stdin;
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
a064cb8d-822e-42b0-8014-ba1bd74f9c3b	e7909abd-8eb4-4378-82a2-59f28c61549c	a0390e70-d987-4688-90c8-444774c5e3a5	32456207	Deriv-Demo	USD	0.00	INELIGIBLE	verified_existing_owner_deriv_demo_readonly_no_orders	PAUSED	\N	2026-10-28 22:00:09.432574+00	2026-11-08 17:12:29.519+00
\.


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

\unrestrict gjM6mVd9EbceZqhlHbK0aHiaFcz9wPYHe4COuAVzoTX6XhjHeNwbyS3zYiaUeZj

