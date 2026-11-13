#!/usr/bin/env python3
"""Isolated APEX DEMO registration and immutable-version consent intake.

No broker API credentials, trading privileges, withdrawals or live access are issued.
"""
import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import sys
import account_flow
import apex_trial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("APEX_SIGNUP_PORT", "18889"))
DOCROOT = Path(os.environ.get("APEX_DOCROOT", "/var/www/apex-landing"))
STATEDIR = Path(os.environ.get("APEX_STATE_DIR", "/var/lib/apex-signup"))
DBFILE = STATEDIR / "accounts.sqlite3"
SECRETFILE = STATEDIR / "ip_hmac_secret"
DOCS = ("terms", "risk", "trading-authorization", "privacy", "api", "refund", "cookies", "status", "methodology")
VERSION = "2026-11-01"
PASSWORD_SEMAPHORE = threading.BoundedSemaphore(2)
ALLOWED_ORIGINS = {"https://abutronfx.online", "https://www.abutronfx.online"}
EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{3,189}\.[A-Za-z]{2,63}$")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

def connect():
    db = sqlite3.connect(DBFILE, timeout=15, isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    return db

def init():
    if not SECRETFILE.is_file():
        raise RuntimeError("IP HMAC key missing; refusing to start")
    if SECRETFILE.stat().st_mode & 0o077:
        raise RuntimeError("IP HMAC key permissions are too permissive")
    if not all((DOCROOT / "legal" / d / "index.html").is_file() for d in DOCS):
        raise RuntimeError("Published policy pages missing; refusing to start")
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("""CREATE TABLE IF NOT EXISTS accounts(
            id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            country TEXT NOT NULL, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending_review','approved','rejected','disabled')),
            demo_execution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(demo_execution_enabled=0),
            live_execution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(live_execution_enabled=0)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS consent_receipts(
            receipt_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
            document TEXT NOT NULL, document_sha256 TEXT NOT NULL,
            version TEXT NOT NULL, accepted_at TEXT NOT NULL,
            ip_hmac TEXT NOT NULL, user_agent TEXT NOT NULL,
            acknowledgement INTEGER NOT NULL CHECK(acknowledgement=1),
            UNIQUE(account_id,document)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS rate_events(
            id INTEGER PRIMARY KEY, ip_hmac TEXT NOT NULL, event_at INTEGER NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS rate_events_lookup ON rate_events(ip_hmac,event_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS email_rate_events(
            id INTEGER PRIMARY KEY,ip_hmac TEXT NOT NULL,created_at INTEGER NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS email_rate_lookup ON email_rate_events(ip_hmac,created_at)")
        account_flow.init(db)
        apex_trial.init(db)

def verified_document_hashes():
    """Fail closed if a published agreement changes without a versioned archive."""
    hashes = {}
    archive = STATEDIR / "policy_snapshots" / VERSION
    for slug in DOCS:
        live = (DOCROOT / "legal" / slug / "index.html").read_bytes()
        original = (archive / (slug + ".html")).read_bytes()
        if live != original:
            raise RuntimeError("Policy version drift detected: " + slug)
        hashes[slug] = hashlib.sha256(original).hexdigest()
    return hashes

def password_hash(password):
    salt = secrets.token_bytes(24)
    hashed = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=128*1024*1024)
    return "scrypt32768$" + salt.hex() + "$" + hashed.hex()

def ip_digest(ip):
    secret = SECRETFILE.read_bytes()
    return hmac.new(secret, ip.encode("utf-8", "replace"), hashlib.sha256).hexdigest()

class Handler(BaseHTTPRequestHandler):
    server_version = "APEX-Registration"
    sys_version = ""
    def log_message(self, format, *args):
        logging.info("request endpoint=%s method=%s", self.path.split("?")[0][:80], self.command)

    def send_json(self, status, data):
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != "/account/api/status":
            return self.send_json(404, {"error":"Not found"})
        try:
            verified_document_hashes()
            with connect() as db:
                db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone()
            return self.send_json(200, {"registration":"operational","checked_at":utcnow(),
                "broker_execution":"not_independently_verified","live_signup_execution":"disabled"})
        except Exception:
            logging.exception("status check failed")
            return self.send_json(503, {"registration":"unavailable","checked_at":utcnow()})

    def do_POST(self):
        if self.path == "/account/api/resend/webhook":
            import resend_webhook
            return resend_webhook.handle(self)
        if self.path in ("/account/api/account/verify","/account/api/account/resend",
                         "/account/api/account/password/request","/account/api/account/password/confirm"):
            import account_flow_http
            return account_flow_http.handle(self,sys.modules[__name__])
        if self.path != "/account/api/register":
            return self.send_json(404, {"error":"Not found"})
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            return self.send_json(403, {"error":"Registration must be submitted from the secure ABUTRON website."})
        if self.headers.get("Content-Type","").split(";")[0].strip().lower() != "application/json":
            return self.send_json(415, {"error":"JSON request required."})
        try:
            size = int(self.headers.get("Content-Length","0"))
        except ValueError:
            return self.send_json(400, {"error":"Invalid request size."})
        if not 0 < size <= 16384:
            return self.send_json(413, {"error":"Request size is invalid."})
        try:
            payload = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            return self.send_json(400, {"error":"Invalid request."})
        if not isinstance(payload, dict):
            return self.send_json(400, {"error":"Invalid registration fields."})
        consents = payload.get("consents")
        if not isinstance(consents, dict) or set(consents) != set(DOCS) or any(consents[d] is not True for d in DOCS):
            return self.send_json(422, {"error":"Every one of the nine agreement acknowledgements is required."})
        if payload.get("adult") is not True:
            return self.send_json(422, {"error":"You must confirm you are at least 18 years old."})
        name = re.sub(r"\s+", " ", str(payload.get("name","")).strip())
        email = str(payload.get("email","")).strip().casefold()
        country = payload.get("country")
        password = payload.get("password")
        if not 2 <= len(name) <= 120 or any(ord(c)<32 for c in name):
            return self.send_json(422, {"error":"Enter your full legal name."})
        if len(email)>254 or not EMAIL_RE.fullmatch(email):
            return self.send_json(422, {"error":"Enter a valid email address."})
        if country not in ("ZA","OTHER"):
            return self.send_json(422, {"error":"Choose your country of residence."})
        if not isinstance(password, str) or not 12 <= len(password) <= 128 or email.split("@")[0] in password.casefold():
            return self.send_json(422, {"error":"Use a unique password of at least 12 characters."})
        client_ip = self.headers.get("X-APEX-Client-IP","")[:75]
        if not client_ip or not re.fullmatch(r"[0-9a-fA-F.:]{3,75}",client_ip):
            return self.send_json(403, {"error":"Secure registration routing is required."})
        digest = ip_digest(client_ip)
        agent = self.headers.get("User-Agent","")[:256]
        timestamp = utcnow()
        now = int(dt.datetime.now(dt.timezone.utc).timestamp())
        try:
            # Reserve a rate-limit slot atomically BEFORE the memory-hard password hash.
            with connect() as rate_db:
                rate_db.execute("BEGIN IMMEDIATE")
                rate_db.execute("DELETE FROM rate_events WHERE event_at < ?", (now-86400,))
                attempts = rate_db.execute("SELECT count(*) FROM rate_events WHERE ip_hmac=? AND event_at>?",
                                           (digest,now-3600)).fetchone()[0]
                if attempts >= 7:
                    rate_db.execute("ROLLBACK")
                    return self.send_json(429, {"error":"Too many applications from this connection. Try again later."})
                rate_db.execute("INSERT INTO rate_events(ip_hmac,event_at) VALUES(?,?)",(digest,now))
                rate_db.execute("COMMIT")
            if not PASSWORD_SEMAPHORE.acquire(blocking=False):
                return self.send_json(429, {"error":"Registration service is busy. Please retry shortly."})
            try:
                pw = password_hash(password)
            finally:
                PASSWORD_SEMAPHORE.release()
            document_hashes = verified_document_hashes()
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM accounts WHERE email=?",(email,)).fetchone():
                    db.execute("COMMIT")
                    return self.send_json(201, {"status":"verification_requested","message":"If the address is registered, check your inbox for verification."})
                account_id = secrets.token_hex(16)
                db.execute("""INSERT INTO accounts(id,full_name,email,country,password_hash,created_at,status)
                    VALUES(?,?,?,?,?,?,?)""",(account_id,name,email,country,pw,timestamp,"pending_review"))
                db.executemany("""INSERT INTO consent_receipts(account_id,document,document_sha256,version,
                    accepted_at,ip_hmac,user_agent,acknowledgement) VALUES(?,?,?,?,?,?,?,1)""",
                    [(account_id,d,document_hashes[d],VERSION,timestamp,digest,agent) for d in DOCS])
                account_flow.enqueue(db,account_id,"verify",now,limit=False)
                db.execute("COMMIT")
            logging.info("registration application recorded, no execution permissions issued")
            return self.send_json(201, {"status":"verification_requested","message":"Check your inbox to verify your email and activate your ABUTRON account."})
        except Exception:
            logging.exception("registration processing failed")
            return self.send_json(503, {"error":"Registration is temporarily unavailable. Please try later."})

if __name__ == "__main__":
    init()
    server = ThreadingHTTPServer((HOST,PORT),Handler)
    logging.info("APEX DEMO registration listening on loopback port %d",PORT)
    server.serve_forever(poll_interval=0.5)
