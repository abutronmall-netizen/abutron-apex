--
-- PostgreSQL database dump
--

\restrict LcTAn3bM8ApNnLq7YrwDiOyAUS2RsQ4SZWz1pzM54Fsk3dohXkheMyRT9sxGaQ1

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
    id integer NOT NULL,
    actor character varying(255) NOT NULL,
    action character varying(128) NOT NULL,
    subject character varying(255) NOT NULL,
    detail text NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_events_id_seq OWNED BY public.audit_events.id;


--
-- Name: licenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.licenses (
    id integer NOT NULL,
    user_id integer NOT NULL,
    product character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    expires_ts integer,
    created_ts integer NOT NULL
);


--
-- Name: licenses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.licenses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: licenses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.licenses_id_seq OWNED BY public.licenses.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer,
    title character varying(255) NOT NULL,
    body text NOT NULL,
    channel character varying(32) NOT NULL,
    state character varying(32) NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: step26a_customer_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step26a_customer_preferences (
    id integer NOT NULL,
    user_id integer NOT NULL,
    notifications_enabled boolean NOT NULL,
    preferred_symbol character varying(32) NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step26a_customer_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step26a_customer_preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step26a_customer_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step26a_customer_preferences_id_seq OWNED BY public.step26a_customer_preferences.id;


--
-- Name: step26a_devices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step26a_devices (
    id integer NOT NULL,
    user_id integer NOT NULL,
    device_id character varying(255) NOT NULL,
    platform character varying(16) NOT NULL,
    push_token character varying(1024) NOT NULL,
    app_version character varying(64) NOT NULL,
    active boolean NOT NULL,
    created_ts integer NOT NULL,
    last_seen_ts integer NOT NULL
);


--
-- Name: step26a_devices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step26a_devices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step26a_devices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step26a_devices_id_seq OWNED BY public.step26a_devices.id;


--
-- Name: step26a_notification_receipts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step26a_notification_receipts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    notification_id integer NOT NULL,
    read_ts integer NOT NULL
);


--
-- Name: step26a_notification_receipts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step26a_notification_receipts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step26a_notification_receipts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step26a_notification_receipts_id_seq OWNED BY public.step26a_notification_receipts.id;


--
-- Name: step26a_support_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step26a_support_tickets (
    id integer NOT NULL,
    user_id integer NOT NULL,
    subject character varying(255) NOT NULL,
    message text NOT NULL,
    priority character varying(16) NOT NULL,
    status character varying(32) NOT NULL,
    admin_note text NOT NULL,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step26a_support_tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step26a_support_tickets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step26a_support_tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step26a_support_tickets_id_seq OWNED BY public.step26a_support_tickets.id;


--
-- Name: step27_billing_invoices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_billing_invoices (
    id integer NOT NULL,
    invoice_number character varying(64) NOT NULL,
    user_id integer NOT NULL,
    plan character varying(64) NOT NULL,
    product character varying(64) NOT NULL,
    currency character varying(8) NOT NULL,
    amount_minor integer NOT NULL,
    status character varying(32) NOT NULL,
    provider character varying(64) NOT NULL,
    provider_ref character varying(255) NOT NULL,
    notes text NOT NULL,
    due_ts integer,
    paid_ts integer,
    created_by character varying(255) NOT NULL,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step27_billing_invoices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_billing_invoices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_billing_invoices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_billing_invoices_id_seq OWNED BY public.step27_billing_invoices.id;


--
-- Name: step27_crm_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_crm_notes (
    id integer NOT NULL,
    user_id integer NOT NULL,
    body text NOT NULL,
    created_by character varying(255) NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: step27_crm_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_crm_notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_crm_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_crm_notes_id_seq OWNED BY public.step27_crm_notes.id;


--
-- Name: step27_crm_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_crm_profiles (
    id integer NOT NULL,
    user_id integer NOT NULL,
    lifecycle_stage character varying(32) NOT NULL,
    lead_source character varying(128) NOT NULL,
    broker_partner character varying(128) NOT NULL,
    country character varying(64) NOT NULL,
    assigned_to character varying(255) NOT NULL,
    tags_json text NOT NULL,
    last_contact_ts integer,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step27_crm_profiles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_crm_profiles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_crm_profiles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_crm_profiles_id_seq OWNED BY public.step27_crm_profiles.id;


--
-- Name: step27_crm_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_crm_tasks (
    id integer NOT NULL,
    user_id integer NOT NULL,
    title character varying(255) NOT NULL,
    detail text NOT NULL,
    priority character varying(16) NOT NULL,
    status character varying(32) NOT NULL,
    due_ts integer,
    assigned_to character varying(255) NOT NULL,
    created_by character varying(255) NOT NULL,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step27_crm_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_crm_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_crm_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_crm_tasks_id_seq OWNED BY public.step27_crm_tasks.id;


--
-- Name: step27_license_grants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_license_grants (
    id integer NOT NULL,
    user_id integer NOT NULL,
    invoice_id integer,
    license_id integer,
    product character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    requested_by character varying(255) NOT NULL,
    approved_by character varying(255) NOT NULL,
    approved_ts integer,
    revoked_ts integer,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step27_license_grants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_license_grants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_license_grants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_license_grants_id_seq OWNED BY public.step27_license_grants.id;


--
-- Name: step27_notification_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_notification_outbox (
    id integer NOT NULL,
    user_id integer,
    channel character varying(32) NOT NULL,
    category character varying(32) NOT NULL,
    title character varying(255) NOT NULL,
    body text NOT NULL,
    state character varying(32) NOT NULL,
    dedupe_key character varying(255) NOT NULL,
    attempts integer NOT NULL,
    provider_message_id character varying(255) NOT NULL,
    last_error text NOT NULL,
    next_attempt_ts integer,
    created_by character varying(255) NOT NULL,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step27_notification_outbox_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_notification_outbox_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_notification_outbox_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_notification_outbox_id_seq OWNED BY public.step27_notification_outbox.id;


--
-- Name: step27_notification_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_notification_preferences (
    id integer NOT NULL,
    user_id integer NOT NULL,
    in_app_enabled boolean NOT NULL,
    email_enabled boolean NOT NULL,
    push_enabled boolean NOT NULL,
    billing_enabled boolean NOT NULL,
    support_enabled boolean NOT NULL,
    marketing_enabled boolean NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: step27_notification_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_notification_preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_notification_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_notification_preferences_id_seq OWNED BY public.step27_notification_preferences.id;


--
-- Name: step27_payment_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.step27_payment_events (
    id integer NOT NULL,
    invoice_id integer,
    provider character varying(64) NOT NULL,
    event_id character varying(255) NOT NULL,
    event_type character varying(64) NOT NULL,
    amount_minor integer NOT NULL,
    currency character varying(8) NOT NULL,
    verified boolean NOT NULL,
    payload_digest character varying(128) NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: step27_payment_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.step27_payment_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: step27_payment_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.step27_payment_events_id_seq OWNED BY public.step27_payment_events.id;


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscriptions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    plan character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    external_ref character varying(255) NOT NULL,
    created_ts integer NOT NULL,
    updated_ts integer NOT NULL
);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;


--
-- Name: trade_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trade_records (
    id integer NOT NULL,
    account_id integer,
    symbol character varying(32) NOT NULL,
    side character varying(8) NOT NULL,
    tier character varying(32) NOT NULL,
    state character varying(32) NOT NULL,
    ticket character varying(64) NOT NULL,
    volume double precision NOT NULL,
    entry double precision NOT NULL,
    sl double precision NOT NULL,
    tp double precision NOT NULL,
    profit double precision NOT NULL,
    signal_id character varying(128) NOT NULL,
    opened_ts integer,
    closed_ts integer,
    payload text NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: trade_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trade_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trade_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trade_records_id_seq OWNED BY public.trade_records.id;


--
-- Name: trading_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trading_accounts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    broker character varying(128) NOT NULL,
    login character varying(128) NOT NULL,
    server character varying(128) NOT NULL,
    symbol character varying(32) NOT NULL,
    current_tier character varying(32) NOT NULL,
    active boolean NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: trading_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trading_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trading_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trading_accounts_id_seq OWNED BY public.trading_accounts.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    phone character varying(64) NOT NULL,
    password_hash character varying(512) NOT NULL,
    role character varying(32) NOT NULL,
    active boolean NOT NULL,
    created_ts integer NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: audit_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events ALTER COLUMN id SET DEFAULT nextval('public.audit_events_id_seq'::regclass);


--
-- Name: licenses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses ALTER COLUMN id SET DEFAULT nextval('public.licenses_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: step26a_customer_preferences id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_customer_preferences ALTER COLUMN id SET DEFAULT nextval('public.step26a_customer_preferences_id_seq'::regclass);


--
-- Name: step26a_devices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_devices ALTER COLUMN id SET DEFAULT nextval('public.step26a_devices_id_seq'::regclass);


--
-- Name: step26a_notification_receipts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_notification_receipts ALTER COLUMN id SET DEFAULT nextval('public.step26a_notification_receipts_id_seq'::regclass);


--
-- Name: step26a_support_tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_support_tickets ALTER COLUMN id SET DEFAULT nextval('public.step26a_support_tickets_id_seq'::regclass);


--
-- Name: step27_billing_invoices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_billing_invoices ALTER COLUMN id SET DEFAULT nextval('public.step27_billing_invoices_id_seq'::regclass);


--
-- Name: step27_crm_notes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_notes ALTER COLUMN id SET DEFAULT nextval('public.step27_crm_notes_id_seq'::regclass);


--
-- Name: step27_crm_profiles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_profiles ALTER COLUMN id SET DEFAULT nextval('public.step27_crm_profiles_id_seq'::regclass);


--
-- Name: step27_crm_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_tasks ALTER COLUMN id SET DEFAULT nextval('public.step27_crm_tasks_id_seq'::regclass);


--
-- Name: step27_license_grants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_license_grants ALTER COLUMN id SET DEFAULT nextval('public.step27_license_grants_id_seq'::regclass);


--
-- Name: step27_notification_outbox id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_outbox ALTER COLUMN id SET DEFAULT nextval('public.step27_notification_outbox_id_seq'::regclass);


--
-- Name: step27_notification_preferences id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_preferences ALTER COLUMN id SET DEFAULT nextval('public.step27_notification_preferences_id_seq'::regclass);


--
-- Name: step27_payment_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_payment_events ALTER COLUMN id SET DEFAULT nextval('public.step27_payment_events_id_seq'::regclass);


--
-- Name: subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);


--
-- Name: trade_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_records ALTER COLUMN id SET DEFAULT nextval('public.trade_records_id_seq'::regclass);


--
-- Name: trading_accounts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_accounts ALTER COLUMN id SET DEFAULT nextval('public.trading_accounts_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);


--
-- Name: licenses licenses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: step26a_customer_preferences step26a_customer_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_customer_preferences
    ADD CONSTRAINT step26a_customer_preferences_pkey PRIMARY KEY (id);


--
-- Name: step26a_devices step26a_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_devices
    ADD CONSTRAINT step26a_devices_pkey PRIMARY KEY (id);


--
-- Name: step26a_notification_receipts step26a_notification_receipts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_notification_receipts
    ADD CONSTRAINT step26a_notification_receipts_pkey PRIMARY KEY (id);


--
-- Name: step26a_support_tickets step26a_support_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_support_tickets
    ADD CONSTRAINT step26a_support_tickets_pkey PRIMARY KEY (id);


--
-- Name: step27_billing_invoices step27_billing_invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_billing_invoices
    ADD CONSTRAINT step27_billing_invoices_pkey PRIMARY KEY (id);


--
-- Name: step27_crm_notes step27_crm_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_notes
    ADD CONSTRAINT step27_crm_notes_pkey PRIMARY KEY (id);


--
-- Name: step27_crm_profiles step27_crm_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_profiles
    ADD CONSTRAINT step27_crm_profiles_pkey PRIMARY KEY (id);


--
-- Name: step27_crm_tasks step27_crm_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_tasks
    ADD CONSTRAINT step27_crm_tasks_pkey PRIMARY KEY (id);


--
-- Name: step27_license_grants step27_license_grants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_license_grants
    ADD CONSTRAINT step27_license_grants_pkey PRIMARY KEY (id);


--
-- Name: step27_notification_outbox step27_notification_outbox_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_outbox
    ADD CONSTRAINT step27_notification_outbox_pkey PRIMARY KEY (id);


--
-- Name: step27_notification_preferences step27_notification_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_preferences
    ADD CONSTRAINT step27_notification_preferences_pkey PRIMARY KEY (id);


--
-- Name: step27_payment_events step27_payment_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_payment_events
    ADD CONSTRAINT step27_payment_events_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: trade_records trade_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_records
    ADD CONSTRAINT trade_records_pkey PRIMARY KEY (id);


--
-- Name: trading_accounts trading_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_pkey PRIMARY KEY (id);


--
-- Name: step26a_customer_preferences uq_step26a_customer_preference_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_customer_preferences
    ADD CONSTRAINT uq_step26a_customer_preference_user UNIQUE (user_id);


--
-- Name: step26a_devices uq_step26a_device_user_device; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_devices
    ADD CONSTRAINT uq_step26a_device_user_device UNIQUE (user_id, device_id);


--
-- Name: step26a_notification_receipts uq_step26a_notification_receipt; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_notification_receipts
    ADD CONSTRAINT uq_step26a_notification_receipt UNIQUE (user_id, notification_id);


--
-- Name: step27_crm_profiles uq_step27_crm_profile_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_profiles
    ADD CONSTRAINT uq_step27_crm_profile_user UNIQUE (user_id);


--
-- Name: step27_notification_outbox uq_step27_notification_outbox_dedupe; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_outbox
    ADD CONSTRAINT uq_step27_notification_outbox_dedupe UNIQUE (dedupe_key);


--
-- Name: step27_notification_preferences uq_step27_notification_preference_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_preferences
    ADD CONSTRAINT uq_step27_notification_preference_user UNIQUE (user_id);


--
-- Name: step27_payment_events uq_step27_payment_provider_event; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_payment_events
    ADD CONSTRAINT uq_step27_payment_provider_event UNIQUE (provider, event_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_audit_events_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_action ON public.audit_events USING btree (action);


--
-- Name: ix_licenses_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_licenses_user_id ON public.licenses USING btree (user_id);


--
-- Name: ix_notifications_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);


--
-- Name: ix_step26a_customer_preferences_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_customer_preferences_user_id ON public.step26a_customer_preferences USING btree (user_id);


--
-- Name: ix_step26a_devices_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_devices_device_id ON public.step26a_devices USING btree (device_id);


--
-- Name: ix_step26a_devices_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_devices_user_id ON public.step26a_devices USING btree (user_id);


--
-- Name: ix_step26a_notification_receipts_notification_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_notification_receipts_notification_id ON public.step26a_notification_receipts USING btree (notification_id);


--
-- Name: ix_step26a_notification_receipts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_notification_receipts_user_id ON public.step26a_notification_receipts USING btree (user_id);


--
-- Name: ix_step26a_support_tickets_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_support_tickets_status ON public.step26a_support_tickets USING btree (status);


--
-- Name: ix_step26a_support_tickets_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step26a_support_tickets_user_id ON public.step26a_support_tickets USING btree (user_id);


--
-- Name: ix_step27_billing_invoices_invoice_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_step27_billing_invoices_invoice_number ON public.step27_billing_invoices USING btree (invoice_number);


--
-- Name: ix_step27_billing_invoices_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_billing_invoices_status ON public.step27_billing_invoices USING btree (status);


--
-- Name: ix_step27_billing_invoices_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_billing_invoices_user_id ON public.step27_billing_invoices USING btree (user_id);


--
-- Name: ix_step27_crm_notes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_crm_notes_user_id ON public.step27_crm_notes USING btree (user_id);


--
-- Name: ix_step27_crm_profiles_lifecycle_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_crm_profiles_lifecycle_stage ON public.step27_crm_profiles USING btree (lifecycle_stage);


--
-- Name: ix_step27_crm_profiles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_crm_profiles_user_id ON public.step27_crm_profiles USING btree (user_id);


--
-- Name: ix_step27_crm_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_crm_tasks_status ON public.step27_crm_tasks USING btree (status);


--
-- Name: ix_step27_crm_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_crm_tasks_user_id ON public.step27_crm_tasks USING btree (user_id);


--
-- Name: ix_step27_license_grants_invoice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_license_grants_invoice_id ON public.step27_license_grants USING btree (invoice_id);


--
-- Name: ix_step27_license_grants_license_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_license_grants_license_id ON public.step27_license_grants USING btree (license_id);


--
-- Name: ix_step27_license_grants_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_license_grants_status ON public.step27_license_grants USING btree (status);


--
-- Name: ix_step27_license_grants_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_license_grants_user_id ON public.step27_license_grants USING btree (user_id);


--
-- Name: ix_step27_notification_outbox_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_notification_outbox_category ON public.step27_notification_outbox USING btree (category);


--
-- Name: ix_step27_notification_outbox_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_notification_outbox_channel ON public.step27_notification_outbox USING btree (channel);


--
-- Name: ix_step27_notification_outbox_dedupe_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_step27_notification_outbox_dedupe_key ON public.step27_notification_outbox USING btree (dedupe_key);


--
-- Name: ix_step27_notification_outbox_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_notification_outbox_state ON public.step27_notification_outbox USING btree (state);


--
-- Name: ix_step27_notification_outbox_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_notification_outbox_user_id ON public.step27_notification_outbox USING btree (user_id);


--
-- Name: ix_step27_notification_preferences_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_notification_preferences_user_id ON public.step27_notification_preferences USING btree (user_id);


--
-- Name: ix_step27_payment_events_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_payment_events_event_id ON public.step27_payment_events USING btree (event_id);


--
-- Name: ix_step27_payment_events_invoice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_step27_payment_events_invoice_id ON public.step27_payment_events USING btree (invoice_id);


--
-- Name: ix_subscriptions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_subscriptions_user_id ON public.subscriptions USING btree (user_id);


--
-- Name: ix_trade_records_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trade_records_account_id ON public.trade_records USING btree (account_id);


--
-- Name: ix_trade_records_signal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trade_records_signal_id ON public.trade_records USING btree (signal_id);


--
-- Name: ix_trade_records_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trade_records_symbol ON public.trade_records USING btree (symbol);


--
-- Name: ix_trading_accounts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trading_accounts_user_id ON public.trading_accounts USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: licenses licenses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step26a_customer_preferences step26a_customer_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_customer_preferences
    ADD CONSTRAINT step26a_customer_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step26a_devices step26a_devices_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_devices
    ADD CONSTRAINT step26a_devices_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step26a_notification_receipts step26a_notification_receipts_notification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_notification_receipts
    ADD CONSTRAINT step26a_notification_receipts_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES public.notifications(id);


--
-- Name: step26a_notification_receipts step26a_notification_receipts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_notification_receipts
    ADD CONSTRAINT step26a_notification_receipts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step26a_support_tickets step26a_support_tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step26a_support_tickets
    ADD CONSTRAINT step26a_support_tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_billing_invoices step27_billing_invoices_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_billing_invoices
    ADD CONSTRAINT step27_billing_invoices_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_crm_notes step27_crm_notes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_notes
    ADD CONSTRAINT step27_crm_notes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_crm_profiles step27_crm_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_profiles
    ADD CONSTRAINT step27_crm_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_crm_tasks step27_crm_tasks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_crm_tasks
    ADD CONSTRAINT step27_crm_tasks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_license_grants step27_license_grants_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_license_grants
    ADD CONSTRAINT step27_license_grants_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.step27_billing_invoices(id);


--
-- Name: step27_license_grants step27_license_grants_license_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_license_grants
    ADD CONSTRAINT step27_license_grants_license_id_fkey FOREIGN KEY (license_id) REFERENCES public.licenses(id);


--
-- Name: step27_license_grants step27_license_grants_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_license_grants
    ADD CONSTRAINT step27_license_grants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_notification_outbox step27_notification_outbox_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_outbox
    ADD CONSTRAINT step27_notification_outbox_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_notification_preferences step27_notification_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_notification_preferences
    ADD CONSTRAINT step27_notification_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: step27_payment_events step27_payment_events_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.step27_payment_events
    ADD CONSTRAINT step27_payment_events_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.step27_billing_invoices(id);


--
-- Name: subscriptions subscriptions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: trade_records trade_records_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_records
    ADD CONSTRAINT trade_records_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.trading_accounts(id);


--
-- Name: trading_accounts trading_accounts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict LcTAn3bM8ApNnLq7YrwDiOyAUS2RsQ4SZWz1pzM54Fsk3dohXkheMyRT9sxGaQ1

