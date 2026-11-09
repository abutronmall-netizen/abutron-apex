"""APEX Superadmin role, email MFA, audit and read-only administration.

No registration route can grant roles. No trading, payments, broker credentials,
licenses or user role-management writes are exposed by this module.
"""
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import apex_crm
import time
from http import cookies
from pathlib import Path

connect=None
keyfile=None
ROLE="SUPERADMIN"
MFA_LIFETIME=600
ADMIN_LIFETIME=1800
ADMIN_EMAIL="abutroncloud@gmail.com"
def configure(db_connect,secret_path):
    global connect,keyfile
    connect=db_connect
    keyfile=Path(secret_path)
def stamp():return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def now():return int(time.time())
def init():
    if connect is None or not keyfile or not keyfile.is_file() or keyfile.stat().st_mode & 0o077:
        raise RuntimeError("APEX admin MFA secret is missing/insecure")
    if len(keyfile.read_bytes())<32:raise RuntimeError("Invalid APEX admin MFA secret")
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS apex_admin_roles(
            account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role='SUPERADMIN'),
            granted_email TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            email_verified_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_admin_challenges(
            challenge_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            delivered_at INTEGER,
            consumed_at INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_admin_mail_jobs(
            challenge_id TEXT PRIMARY KEY REFERENCES apex_admin_challenges(challenge_id) ON DELETE CASCADE,
            status TEXT NOT NULL CHECK(status IN ('queued','sending','sent','failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_admin_sessions(
            token_hash TEXT PRIMARY KEY,
            parent_session_hash TEXT NOT NULL,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_admin_audit(
            id INTEGER PRIMARY KEY,
            event TEXT NOT NULL,
            account_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            details TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS apex_admin_session_account ON apex_admin_sessions(account_id)")
        c.execute("CREATE INDEX IF NOT EXISTS apex_admin_mfa_account ON apex_admin_challenges(account_id,created_at)")
def cookie_token(header,name):
    jar=cookies.SimpleCookie()
    try:jar.load(header or "")
    except cookies.CookieError:return None
    item=jar.get(name)
    token=item.value if item else ""
    return token if re.fullmatch("[0-9a-f]{64}",token) else None
def otp_for(account_id,challenge_id):
    secret=keyfile.read_bytes()
    msg=("APEX/ADMIN/EMAIL/MFA/V1:"+account_id+":"+challenge_id).encode()
    digits=int.from_bytes(hmac.new(secret,msg,hashlib.sha256).digest()[:8],"big")%100000000
    return f"{digits:08d}"
def role_row(account):
    if account is None:return None
    aid,name,email,country,status,demo,live=account
    with connect() as c:
        role=c.execute("""SELECT role,granted_email,email_verified_at FROM apex_admin_roles
                          WHERE account_id=?""",(aid,)).fetchone()
    if not role or role[0]!=ROLE or role[1]!=email or email!=ADMIN_EMAIL or status!="approved":
        return None
    return role
def log(c,event,account_id,details=""):
    c.execute("INSERT INTO apex_admin_audit(event,account_id,recorded_at,details) VALUES(?,?,?,?)",
              (event,account_id,stamp(),str(details)[:160]))
class AdminMixin:
    def admin_parent(self):
        # The inherited method authenticates the regular APEX password/session.
        return self.authenticated()
    def admin_session(self,account,reply_error=True):
        role=role_row(account)
        if not role:
            if reply_error:self.reply(403,{"error":"Administrator role required."})
            return False
        parent=cookie_token(self.headers.get("Cookie"),"apex_client")
        admin=cookie_token(self.headers.get("Cookie"),"apex_admin")
        if not parent or not admin or not role[2]:
            if reply_error:self.reply(403,{"error":"Superadmin email code verification required."})
            return False
        digest=hashlib.sha256(admin.encode()).hexdigest()
        parent_digest=hashlib.sha256(parent.encode()).hexdigest()
        with connect() as c:
            row=c.execute("""SELECT 1 FROM apex_admin_sessions
                WHERE token_hash=? AND parent_session_hash=? AND account_id=? AND expires_at>?""",
                (digest,parent_digest,account[0],now())).fetchone()
        if not row and reply_error:self.reply(403,{"error":"Superadmin email code verification required."})
        return bool(row)
    def admin_get(self):
        account=self.admin_parent()
        if account is None:return
        role=role_row(account)
        if not role:return self.reply(403,{"error":"Administrator role required."})
        if self.path=="/account/api/client/admin/me":
            return self.reply(200,{"role":ROLE,"email":account[2],"email_verified":bool(role[2]),
                "mfa_authenticated":self.admin_session(account,False),
                "permissions":["READ_ONLY_PLATFORM_OVERVIEW"],
                "live_trading_enabled":False})
        if self.path.startswith(apex_crm.BASE):
            if not self.admin_session(account):return
            try:return apex_crm.get(self,account[0])
            except (ValueError,LookupError) as exc:return self.reply(422,{"error":str(exc)})
        if self.path=="/account/api/client/admin/overview":
            if not self.admin_session(account):return
            with connect() as c:
                statuses=c.execute("SELECT status,count(*) FROM accounts GROUP BY status").fetchall()
                pending=c.execute("""SELECT id,full_name,email,country,created_at,status FROM accounts
                                     WHERE status='pending_review' ORDER BY created_at DESC LIMIT 50""").fetchall()
                broker=c.execute("""SELECT broker,platform,environment,status,count(*)
                                    FROM broker_link_requests GROUP BY broker,platform,environment,status""").fetchall()
                audit=c.execute("""SELECT event,recorded_at FROM apex_admin_audit
                                   WHERE account_id=? ORDER BY id DESC LIMIT 15""",(account[0],)).fetchall()
            return self.reply(200,{"role":ROLE,"admin_mode":"READ_ONLY",
                "customer_status_counts":dict(statuses),
                "pending_registrations":[dict(zip(("id","name","email","country","created_at","status"),r)) for r in pending],
                "broker_verification_requests":[dict(zip(("broker","platform","environment","status","count"),r)) for r in broker],
                "audit":[{"event":e,"timestamp":t} for e,t in audit],
                "live_trading_enabled":False,"payments_enabled":False,
                "notice":"Administration is read-only. No account, broker, trading, payment or role mutations are enabled."})
        return self.reply(404,{"error":"Not found"})
    def admin_post(self,payload):
        account=self.admin_parent()
        if account is None:return
        role=role_row(account)
        if not role:return self.reply(403,{"error":"Administrator role required."})
        if self.path.startswith(apex_crm.BASE):
            if not self.admin_session(account):return
            try:return apex_crm.post(self,account[0],payload)
            except (ValueError,LookupError) as exc:return self.reply(422,{"error":str(exc)})
            except sqlite3.IntegrityError:return self.reply(409,{"error":"Record conflict. Please reload."})
        if self.path=="/account/api/client/admin/mfa/request":
            with connect() as c:
                c.execute("BEGIN IMMEDIATE")
                moment=now()
                # Count codes the email relay could deliver, not expired never-sent
                # queue items from a stopped/crashed mailer. Preserve per-hour
                # delivery limits AND a hard overall request cap to stop abuse.
                delivered_or_pending=c.execute("""SELECT count(*)
                    FROM apex_admin_challenges ch
                    JOIN apex_admin_mail_jobs j ON j.challenge_id=ch.challenge_id
                    WHERE ch.account_id=? AND ch.created_at>?
                      AND (j.status='sent'
                           OR (j.status IN ('queued','sending') AND ch.expires_at>?))
                      """,(account[0],moment-3600,moment)).fetchone()[0]
                total_requests=c.execute("""SELECT count(*) FROM apex_admin_challenges
                    WHERE account_id=? AND created_at>?""",(account[0],moment-3600)).fetchone()[0]
                if delivered_or_pending>=4 or total_requests>=12:
                    c.execute("ROLLBACK")
                    return self.reply(429,{"error":"Email verification rate limit reached. Try later."})
                # Never invalidate an already-delivered code until the next code is queued.
                challenge=secrets.token_hex(24)
                c.execute("""INSERT INTO apex_admin_challenges(challenge_id,account_id,created_at,expires_at)
                             VALUES(?,?,?,?)""",(challenge,account[0],moment,moment+MFA_LIFETIME))
                c.execute("""INSERT INTO apex_admin_mail_jobs(challenge_id,status,updated_at)
                             VALUES(?,'queued',?)""",(challenge,moment))
                log(c,"ADMIN_MFA_QUEUED",account[0])
                c.execute("COMMIT")
            return self.reply(202,{"status":"verification_email_queued",
                "message":"An eight-digit verification code has been requested for your registered email. Delivery may take a moment."})
        if self.path=="/account/api/client/admin/mfa/verify":
            code=payload.get("code","")
            if not isinstance(code,str) or not re.fullmatch(r"[0-9]{8}",code):
                return self.reply(422,{"error":"Enter the eight-digit verification code."})
            with connect() as c:
                c.execute("BEGIN IMMEDIATE")
                moment=now()
                row=c.execute("""SELECT ch.challenge_id,ch.attempt_count
                    FROM apex_admin_challenges ch JOIN apex_admin_mail_jobs j ON ch.challenge_id=j.challenge_id
                    WHERE ch.account_id=? AND ch.expires_at>? AND ch.consumed_at IS NULL
                    AND ch.delivered_at IS NOT NULL AND j.status='sent'
                    ORDER BY ch.created_at DESC LIMIT 1""",(account[0],moment)).fetchone()
                if row is None:
                    c.execute("ROLLBACK")
                    return self.reply(403,{"error":"No delivered verification code is available. Request another."})
                cid,attempts=row
                if attempts>=6:
                    c.execute("ROLLBACK")
                    return self.reply(429,{"error":"Too many incorrect codes. Request a new code."})
                expected=otp_for(account[0],cid)
                c.execute("UPDATE apex_admin_challenges SET attempt_count=attempt_count+1 WHERE challenge_id=?",(cid,))
                if not hmac.compare_digest(code,expected):
                    log(c,"ADMIN_MFA_BAD_CODE",account[0])
                    c.execute("COMMIT")
                    return self.reply(403,{"error":"Incorrect verification code."})
                token=secrets.token_hex(32)
                parent=cookie_token(self.headers.get("Cookie"),"apex_client")
                if not parent:
                    c.execute("ROLLBACK");return self.reply(401,{"error":"Sign in again."})
                c.execute("UPDATE apex_admin_challenges SET consumed_at=? WHERE challenge_id=?",(moment,cid))
                c.execute("DELETE FROM apex_admin_sessions WHERE account_id=?",(account[0],))
                c.execute("""INSERT INTO apex_admin_sessions(token_hash,parent_session_hash,account_id,created_at,expires_at)
                             VALUES(?,?,?,?,?)""",(hashlib.sha256(token.encode()).hexdigest(),
                     hashlib.sha256(parent.encode()).hexdigest(),account[0],moment,moment+ADMIN_LIFETIME))
                c.execute("""UPDATE apex_admin_roles SET email_verified_at=COALESCE(email_verified_at,?)
                             WHERE account_id=?""",(stamp(),account[0]))
                log(c,"ADMIN_MFA_VERIFIED",account[0])
                c.execute("COMMIT")
            cookie="apex_admin="+token+"; Path=/account; Max-Age="+str(ADMIN_LIFETIME)+"; Secure; HttpOnly; SameSite=Strict"
            return self.reply(200,{"role":ROLE,"email_verified":True,
                 "admin_authenticated":True,"live_trading_enabled":False},[("Set-Cookie",cookie)])
        if self.path=="/account/api/client/admin/logout":
            token=cookie_token(self.headers.get("Cookie"),"apex_admin")
            if token:
                with connect() as c:
                    c.execute("DELETE FROM apex_admin_sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
                    log(c,"ADMIN_SESSION_REVOKED",account[0])
            return self.reply(200,{"admin_authenticated":False},
                [("Set-Cookie","apex_admin=; Path=/account; Max-Age=0; Secure; HttpOnly; SameSite=Strict")])
        return self.reply(404,{"error":"Not found"})
