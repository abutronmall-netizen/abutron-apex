--
-- PostgreSQL database dump
--

\restrict Am1UaI2bhxrFMK7rLFwaLaxORtlq5wyMhkEBGW7fKpqSVmwkH6OgUB7QIU12suf

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
-- Data for Name: audit_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.audit_events (id, actor, action, subject, detail, created_ts) FROM stdin;
1	certification-20260919221629@abutronfx.online	USER_REGISTERED	2		1789856211
2	certification-20260919221629@abutronfx.online	TRADING_ACCOUNT_ADDED	1		1789856261
3	admin@abutronfx.online	LICENSE_STATE_CHANGED	2	active	1789857096
7	step15-cert	STEP15_CERTIFIED	STEP15-20260924-151141-8a63bd3a	Database/audit persistence, restart reconciliation, idempotency and mixed-backend backup/restore drill passed. No trading action performed.	1790262750
8	step19-certification	STEP19_CERT_ACCOUNT_BOUND	****3285	tier=SCALPER;server=ICMarketsSC-Demo;license_expires_ts=1790539197	1790279997
9	step19-certification	STEP19_CERT_ACCOUNT_BOUND	****4047	tier=MASTER;server=ICMarketsSC-Demo;license_expires_ts=1790541654	1790282454
10	abutroncloud@gmail.com	USER_REGISTERED	4		1790413642
11	abutroncloud@gmail.com	CUSTOMER_PROFILE_UPDATED	4		1790413805
12	abutroncloud@gmail.com	SUPPORT_TICKET_CREATED	1	normal	1790416344
13	abutroncloud@gmail.com	CUSTOMER_PROFILE_UPDATED	4		1790416361
\.


--
-- Data for Name: licenses; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.licenses (id, user_id, product, status, expires_ts, created_ts) FROM stdin;
1	2	ABUTRON_V4	active	\N	1789856211
2	3	ABUTRON_V4	active	1790541654	1790279997
3	4	ABUTRON_V4	pending	\N	1790413642
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.notifications (id, user_id, title, body, channel, state, created_ts) FROM stdin;
\.


--
-- Data for Name: step26a_customer_preferences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step26a_customer_preferences (id, user_id, notifications_enabled, preferred_symbol, updated_ts) FROM stdin;
1	4	t	XAUUSD	1790416361
\.


--
-- Data for Name: step26a_devices; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step26a_devices (id, user_id, device_id, platform, push_token, app_version, active, created_ts, last_seen_ts) FROM stdin;
\.


--
-- Data for Name: step26a_notification_receipts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step26a_notification_receipts (id, user_id, notification_id, read_ts) FROM stdin;
\.


--
-- Data for Name: step26a_support_tickets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step26a_support_tickets (id, user_id, subject, message, priority, status, admin_note, created_ts, updated_ts) FROM stdin;
1	4	Step 26B Android Test	Testing the android app from a samsung device	normal	open		1790416344	1790416344
\.


--
-- Data for Name: step27_billing_invoices; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_billing_invoices (id, invoice_number, user_id, plan, product, currency, amount_minor, status, provider, provider_ref, notes, due_ts, paid_ts, created_by, created_ts, updated_ts) FROM stdin;
\.


--
-- Data for Name: step27_crm_notes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_crm_notes (id, user_id, body, created_by, created_ts) FROM stdin;
\.


--
-- Data for Name: step27_crm_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_crm_profiles (id, user_id, lifecycle_stage, lead_source, broker_partner, country, assigned_to, tags_json, last_contact_ts, created_ts, updated_ts) FROM stdin;
\.


--
-- Data for Name: step27_crm_tasks; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_crm_tasks (id, user_id, title, detail, priority, status, due_ts, assigned_to, created_by, created_ts, updated_ts) FROM stdin;
\.


--
-- Data for Name: step27_license_grants; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_license_grants (id, user_id, invoice_id, license_id, product, status, requested_by, approved_by, approved_ts, revoked_ts, created_ts, updated_ts) FROM stdin;
\.


--
-- Data for Name: step27_notification_outbox; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_notification_outbox (id, user_id, channel, category, title, body, state, dedupe_key, attempts, provider_message_id, last_error, next_attempt_ts, created_by, created_ts, updated_ts) FROM stdin;
\.


--
-- Data for Name: step27_notification_preferences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_notification_preferences (id, user_id, in_app_enabled, email_enabled, push_enabled, billing_enabled, support_enabled, marketing_enabled, updated_ts) FROM stdin;
\.


--
-- Data for Name: step27_payment_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.step27_payment_events (id, invoice_id, provider, event_id, event_type, amount_minor, currency, verified, payload_digest, created_ts) FROM stdin;
\.


--
-- Data for Name: subscriptions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.subscriptions (id, user_id, plan, status, external_ref, created_ts, updated_ts) FROM stdin;
\.


--
-- Data for Name: trade_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.trade_records (id, account_id, symbol, side, tier, state, ticket, volume, entry, sl, tp, profit, signal_id, opened_ts, closed_ts, payload, created_ts) FROM stdin;
1	1	BTCUSD	BUY	FLIPPER	CLOSED	1945197093	0.01	81231.03	0	0	-0.05		1789873106	1789873107	{"reconciliation": {"version": 1, "position_id": 1945197093, "broker_login": "53054439", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1566419956": {"ticket": 1566419956, "position_id": 1945197093, "entry": 0, "type": 0, "symbol": "BTCUSD", "volume": 0.01, "price": 81231.03, "profit": 0.0, "commission": 0.0, "swap": 0.0, "fee": 0.0, "time": 1789873106, "magic": 400040, "comment": "ABUTRON FLIPPER"}, "1566419958": {"ticket": 1566419958, "position_id": 1945197093, "entry": 1, "type": 1, "symbol": "BTCUSD", "volume": 0.01, "price": 81226.04, "profit": -0.05, "commission": 0.0, "swap": 0.0, "fee": 0.0, "time": 1789873107, "magic": 400040, "comment": "ABUTRON CLOSE"}}}}	1790253746
4	1	XAUUSD	BUY	FLIPPER	CLOSED	1962932427	0.01	4273.9	4271.3826	4276.150844444444	-0.17	STEP19-1790278078-fd27dbdf9c46	1790288895	1790288896	{"pipeline": {"symbol": "XAUUSD", "route": {"selected": "FLIPPER", "locked": false}, "strategy": {"name": "flipper-v4-adaptive-directional", "tier": "FLIPPER"}, "plan": {"symbol": "XAUUSD", "direction": "BUY", "tier": "FLIPPER", "strategy_profile": "flipper-v4-adaptive-directional", "volume": 0.01, "entry": 4274.01, "sl": 4271.3826, "tp": 4276.150844444444, "risk_amount": 2.6274, "confidence": 99.0, "idempotency_key": "STEP19-1790278078-fd27dbdf9c46", "thesis_reason": "STEP19_CONTROLLED_DEMO_ROUTER_CERT_NOT_A_MARKET_SIGNAL"}, "execution": {"accepted": true, "retcode": 10009, "order": 1962932427, "deal": 1578311273, "position_ticket": 1962932427, "comment": "Request executed", "symbol": "XAUUSD", "volume": 0.01, "check_retcode": 0, "check_comment": "Done"}, "certification": {"step": 19, "market_signal_used": false}}, "execution_result": {"accepted": true, "retcode": 10009, "order": 1962932427, "deal": 1578311273, "position_ticket": 1962932427, "comment": "Request executed", "symbol": "XAUUSD", "volume": 0.01, "check_retcode": 0, "check_comment": "Done"}, "broker_account": {"login": "53054439", "server": "ICMarketsSC-Demo"}, "reconciliation": {"version": 1, "position_id": 1962932427, "broker_login": "53054439", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1578311273": {"ticket": 1578311273, "position_id": 1962932427, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4273.9, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790288895, "magic": 400040, "comment": "ABUTRON FLIPPER"}, "1578311279": {"ticket": 1578311279, "position_id": 1962932427, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4273.81, "profit": -0.09, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790288896, "magic": 400040, "comment": "ABUTRON CLOSE"}}}}	1790278095
5	2	XAUUSD	BUY	SCALPER	CLOSED	1963054915	0.01	4265.16	4250.14	4283.89	-0.17	STEP19-1790281404-04020d5a9655	1790292221	1790292222	{"pipeline": {"symbol": "XAUUSD", "route": {"selected": "SCALPER", "locked": false}, "strategy": {"name": "scalper-v4-precision-sniper", "tier": "SCALPER"}, "plan": {"symbol": "XAUUSD", "direction": "BUY", "tier": "SCALPER", "strategy_profile": "scalper-v4-precision-sniper", "volume": 0.01, "entry": 4265.14, "sl": 4250.14, "tp": 4283.89, "risk_amount": 15.0, "confidence": 99.0, "idempotency_key": "STEP19-1790281404-04020d5a9655", "thesis_reason": "STEP19_CONTROLLED_DEMO_ROUTER_CERT_NOT_A_MARKET_SIGNAL"}, "execution": {"accepted": true, "retcode": 10009, "order": 1963054915, "deal": 1578380344, "position_ticket": 1963054915, "comment": "Request executed", "symbol": "XAUUSD", "volume": 0.01, "check_retcode": 0, "check_comment": "Done"}, "certification": {"step": 19, "market_signal_used": false}}, "execution_result": {"accepted": true, "retcode": 10009, "order": 1963054915, "deal": 1578380344, "position_ticket": 1963054915, "comment": "Request executed", "symbol": "XAUUSD", "volume": 0.01, "check_retcode": 0, "check_comment": "Done"}, "broker_account": {"login": "53063285", "server": "ICMarketsSC-Demo"}, "reconciliation": {"version": 1, "position_id": 1963054915, "broker_login": "53063285", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1578380344": {"ticket": 1578380344, "position_id": 1963054915, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4265.16, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790292221, "magic": 400040, "comment": "ABUTRON SCALPER"}, "1578380351": {"ticket": 1578380351, "position_id": 1963054915, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4265.07, "profit": -0.09, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790292222, "magic": 400040, "comment": "ABUTRON CLOSE"}}}}	1790281422
6	3	XAUUSD	BUY	MASTER	CLOSED	1963094634	0.01	4271.24	4245.09	4310.715	-0.48999999999999994	STEP19-1790282794-a3248548010f	1790293610	1790293611	{"pipeline": {"symbol": "XAUUSD", "route": {"selected": "MASTER", "locked": false}, "strategy": {"name": "master-v4-mtf-capital", "tier": "MASTER"}, "plan": {"symbol": "XAUUSD", "direction": "BUY", "tier": "MASTER", "strategy_profile": "master-v4-mtf-capital", "volume": 0.01, "entry": 4271.34, "sl": 4245.09, "tp": 4310.715, "risk_amount": 26.249999999999993, "confidence": 99.0, "idempotency_key": "STEP19-1790282794-a3248548010f", "thesis_reason": "STEP19_CONTROLLED_DEMO_ROUTER_CERT_NOT_A_MARKET_SIGNAL"}, "execution": {"accepted": true, "retcode": 10009, "order": 1963094634, "deal": 1578404471, "position_ticket": 1963094634, "comment": "Request executed", "symbol": "XAUUSD", "volume": 0.01, "check_retcode": 0, "check_comment": "Done"}, "certification": {"step": 19, "market_signal_used": false}}, "execution_result": {"accepted": true, "retcode": 10009, "order": 1963094634, "deal": 1578404471, "position_ticket": 1963094634, "comment": "Request executed", "symbol": "XAUUSD", "volume": 0.01, "check_retcode": 0, "check_comment": "Done"}, "broker_account": {"login": "53064047", "server": "ICMarketsSC-Demo"}, "reconciliation": {"version": 1, "position_id": 1963094634, "broker_login": "53064047", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1578404471": {"ticket": 1578404471, "position_id": 1963094634, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4271.24, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790293610, "magic": 400040, "comment": "ABUTRON MASTER"}, "1578404476": {"ticket": 1578404476, "position_id": 1963094634, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4270.83, "profit": -0.41, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790293611, "magic": 400040, "comment": "ABUTRON CLOSE"}}}}	1790282811
7	1	XAUUSD	BUY	FLIPPER	CLOSED	1962350154	0.01	4278.76	0	0	2.13		1790278860	1790278920	{"reconciliation": {"version": 1, "position_id": 1962350154, "broker_login": "53054439", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1577901947": {"ticket": 1577901947, "position_id": 1962350154, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4278.76, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790278860, "magic": 400040, "comment": "ABUTRON FLIPPER"}, "1577905358": {"ticket": 1577905358, "position_id": 1962350154, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4280.97, "profit": 2.21, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790278920, "magic": 400040, "comment": "[tp 4280.49]"}}}}	1790286443
8	1	XAUUSD	BUY	FLIPPER	CLOSED	1962493091	0.01	4270.91	0	0	-1.36		1790280902	1790280915	{"reconciliation": {"version": 1, "position_id": 1962493091, "broker_login": "53054439", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1578008598": {"ticket": 1578008598, "position_id": 1962493091, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4270.91, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790280902, "magic": 400040, "comment": "ABUTRON FLIPPER"}, "1578009222": {"ticket": 1578009222, "position_id": 1962493091, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4269.63, "profit": -1.28, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790280915, "magic": 400040, "comment": "[sl 4270.01]"}}}}	1790286443
9	1	XAUUSD	BUY	FLIPPER	CLOSED	1962572054	0.01	4263.03	0	0	-0.009999999999999995		1790282161	1790282161	{"reconciliation": {"version": 1, "position_id": 1962572054, "broker_login": "53054439", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1578066680": {"ticket": 1578066680, "position_id": 1962572054, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4263.03, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790282161, "magic": 400040, "comment": "ABUTRON FLIPPER"}, "1578066728": {"ticket": 1578066728, "position_id": 1962572054, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4263.1, "profit": 0.07, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790282161, "magic": 400040, "comment": "ABUTRON CLOSE"}}}}	1790286443
10	1	XAUUSD	BUY	FLIPPER	CLOSED	1962748995	0.01	4273.78	0	0	-0.07		1790285274	1790285275	{"reconciliation": {"version": 1, "position_id": 1962748995, "broker_login": "53054439", "broker_server": "ICMarketsSC-Demo", "opened_volume": 0.01, "closed_volume": 0.01, "deal_count": 2, "deals": {"1578192705": {"ticket": 1578192705, "position_id": 1962748995, "entry": 0, "type": 0, "symbol": "XAUUSD", "volume": 0.01, "price": 4273.78, "profit": 0.0, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790285274, "magic": 400040, "comment": "ABUTRON FLIPPER"}, "1578192711": {"ticket": 1578192711, "position_id": 1962748995, "entry": 1, "type": 1, "symbol": "XAUUSD", "volume": 0.01, "price": 4273.79, "profit": 0.01, "commission": -0.04, "swap": 0.0, "fee": 0.0, "time": 1790285275, "magic": 400040, "comment": "ABUTRON CLOSE"}}}}	1790286443
\.


--
-- Data for Name: trading_accounts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.trading_accounts (id, user_id, broker, login, server, symbol, current_tier, active, created_ts) FROM stdin;
1	2	IC Markets	53054439	ICMarketsSC-Demo	XAUUSD	FLIPPER	t	1789856261
2	3	IC Markets	53063285	ICMarketsSC-Demo	XAUUSD	SCALPER	t	1790279997
3	3	IC Markets	53064047	ICMarketsSC-Demo	XAUUSD	MASTER	t	1790282454
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, email, full_name, phone, password_hash, role, active, created_ts) FROM stdin;
1	admin@abutronfx.online	Abutron Administrator		$argon2id$v=19$m=65536,t=3,p=4$v79PSUa3rsfpPugphA+UHQ$Ts4MHIyKi94XnCWyQXdmHl6srTtCizVN2t3dosF7mQ4	superadmin	t	1789853419
2	certification-20260919221629@abutronfx.online	Abutron Certification		$argon2id$v=19$m=65536,t=3,p=4$1iIW+15zCOSVzFVmSzuyMQ$aPkpsh1CjGtbtjStEh9v2Y0YcxjWnRfwxi+cWNWta1E	customer	t	1789856211
3	step19-certification@abutron.local	ABUTRON STEP 19 CERTIFICATION		$argon2id$v=19$m=65536,t=3,p=4$/7OYebE0GcWzJSViTgn5nA$9GW5uhzSrB25cp6ykudEJ8L1j/CK7ttV8quXf2eWHlU	customer	t	1790279997
4	abutroncloud@gmail.com	David Morgan Walker	0672401776	$argon2id$v=19$m=65536,t=3,p=4$djreMcTMzWJ65rKgoS3wbg$XVUYtrNyJxOImmKK0qC36F8N8J/WROa3yXSN5oqFnCw	customer	t	1790413642
\.


--
-- Name: audit_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.audit_events_id_seq', 13, true);


--
-- Name: licenses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.licenses_id_seq', 3, true);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.notifications_id_seq', 1, false);


--
-- Name: step26a_customer_preferences_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step26a_customer_preferences_id_seq', 1, true);


--
-- Name: step26a_devices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step26a_devices_id_seq', 1, false);


--
-- Name: step26a_notification_receipts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step26a_notification_receipts_id_seq', 1, false);


--
-- Name: step26a_support_tickets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step26a_support_tickets_id_seq', 1, true);


--
-- Name: step27_billing_invoices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_billing_invoices_id_seq', 1, false);


--
-- Name: step27_crm_notes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_crm_notes_id_seq', 1, false);


--
-- Name: step27_crm_profiles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_crm_profiles_id_seq', 1, false);


--
-- Name: step27_crm_tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_crm_tasks_id_seq', 1, false);


--
-- Name: step27_license_grants_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_license_grants_id_seq', 1, false);


--
-- Name: step27_notification_outbox_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_notification_outbox_id_seq', 1, false);


--
-- Name: step27_notification_preferences_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_notification_preferences_id_seq', 1, false);


--
-- Name: step27_payment_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.step27_payment_events_id_seq', 1, false);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.subscriptions_id_seq', 1, false);


--
-- Name: trade_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.trade_records_id_seq', 10, true);


--
-- Name: trading_accounts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.trading_accounts_id_seq', 3, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 4, true);


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

\unrestrict Am1UaI2bhxrFMK7rLFwaLaxORtlq5wyMhkEBGW7fKpqSVmwkH6OgUB7QIU12suf

