#!/usr/bin/env python3
"""Isolated APEX client login & broker verification requests; NO trading or credential capture.

This server cannot access MT5/Wine trading sessions. Broker entries here are NOT connections.
"""
from __future__ import annotations
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
import time
import sys
sys.path.insert(0,'/opt/apex-signup')
import account_flow
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import apex_admin
import apex_trading_controls
import apex_crm
import apex_crm_license_policy
import apex_customer_worker_entitlement
import apex_trial
import apex_pricing
import apex_mt5_linking
import apex_mt5_mfa
import apex_mt5_private_client
import abutron_mt5_portal_adapter
import apex_mt5_secure_auth
import apex_mt5_direct_auth
import abutron_fp_market_portal
import abutron_fp_history_portal
from pathlib import Path
sys.path.append('/opt/apex/runtime')  # Read-only AI telemetry package
from apex_ui.trading_health import snapshot as read_trading_health

HOST="127.0.0.1"
PORT=int(os.environ.get("APEX_CLIENT_PORT","18890"))
STATEDIR=Path(os.environ.get("APEX_CLIENT_STATE_DIR","/var/lib/apex-signup"))
DBFILE=STATEDIR/"accounts.sqlite3"
SECRETFILE=STATEDIR/"ip_hmac_secret"
SESSION_LIFETIME=8*60*60
ORIGINS={"https://abutronfx.online","https://www.abutronfx.online"}
IP_RE=re.compile(r"^[0-9a-fA-F:.]{3,75}$")
EMAIL_RE=re.compile(r"^[^\s@]{1,64}@[^\s@]{3,189}\.[a-zA-Z]{2,63}$")
REF_RE=re.compile(r"^[A-Za-z0-9_.-]{4,40}$")
SERVER_RE=re.compile(r"^[a-zA-Z0-9 _.-]{3,100}$")
SEMAPHORE=threading.BoundedSemaphore(2)
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
DUMMY_SALT=bytes.fromhex("b88d194365f1248c0db65478a920439aa0dbd87381245699")

def now_epoch():return int(time.time())
def now_iso():return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def db_connect():
    c=sqlite3.connect(DBFILE,timeout=12,isolation_level=None)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=12000")
    return c
def init():
    if not DBFILE.is_file() or not SECRETFILE.is_file() or SECRETFILE.stat().st_mode & 0o077:
        raise RuntimeError("Existing registration DB / HMAC key unavailable or insecure")
    with db_connect() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone():
            raise RuntimeError("Registration accounts schema unavailable")
        c.execute("""CREATE TABLE IF NOT EXISTS client_sessions(
          token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS client_sessions_account ON client_sessions(account_id)")
        c.execute("""CREATE TABLE IF NOT EXISTS client_login_attempts(
          id INTEGER PRIMARY KEY,ip_hmac TEXT NOT NULL, attempted_at INTEGER NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS client_login_attempts_index ON client_login_attempts(ip_hmac,attempted_at)")
        c.execute("""CREATE TABLE IF NOT EXISTS broker_link_requests(
          id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
          platform TEXT NOT NULL CHECK(platform IN ('MT5','cTrader')),
          environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
          account_reference TEXT NOT NULL, broker_server TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('verification_pending','oauth_pending')),
          created_at TEXT NOT NULL,
          execution_enabled INTEGER NOT NULL DEFAULT 0 CHECK(execution_enabled=0),
          owner_verified INTEGER NOT NULL DEFAULT 0 CHECK(owner_verified=0),
          UNIQUE(account_id,broker,platform,environment,account_reference,broker_server))""")
        c.execute("PRAGMA secure_delete=ON")
    with db_connect() as c:
        apex_trading_controls.init(c)
        apex_mt5_linking.init(c)
        apex_mt5_mfa.init(c)
        apex_mt5_direct_auth.init(c)
        account_flow.init(c)
        apex_trial.init(c)
    apex_admin.configure(db_connect,STATEDIR/"admin_mfa_secret")
    apex_admin.init()
    apex_crm.configure(db_connect)
    apex_crm.init()
    with db_connect() as c:apex_customer_worker_entitlement.init(c)
def ip_digest(ip):
    return hmac.new(SECRETFILE.read_bytes(),ip.encode(),hashlib.sha256).hexdigest()
def valid_password(password, encoded):
    try:
        tag,salt_hex,expected_hex=encoded.split("$")
        if tag!="scrypt32768":return False
        salt=bytes.fromhex(salt_hex);expected=bytes.fromhex(expected_hex)
        if len(salt)!=24 or len(expected)!=32:return False
    except (ValueError,TypeError,AttributeError):
        return False
    candidate=hashlib.scrypt(password.encode("utf-8"),salt=salt,n=2**15,r=8,p=1,dklen=32,maxmem=128*1024*1024)
    return hmac.compare_digest(candidate,expected)
def fake_password_work(password):
    hashlib.scrypt(password.encode("utf-8"),salt=DUMMY_SALT,n=2**15,r=8,p=1,dklen=32,maxmem=128*1024*1024)
def cookie_token(header):
    jar=cookies.SimpleCookie()
    try:jar.load(header or "")
    except cookies.CookieError:return None
    morsel=jar.get("apex_client")
    if morsel is None:return None
    token=morsel.value
    return token if re.fullmatch(r"[a-f0-9]{64}",token) else None
def verify_session(header):
    token=cookie_token(header)
    if not token:return None
    h=hashlib.sha256(token.encode()).hexdigest()
    with db_connect() as c:
        row=c.execute("""SELECT a.id,a.full_name,a.email,a.country,a.status,a.demo_execution_enabled,a.live_execution_enabled
                         FROM client_sessions s JOIN accounts a ON a.id=s.account_id
                         WHERE s.token_hash=? AND s.expires_at>?
                         AND a.status IN ('pending_review','approved')""",(h,now_epoch())).fetchone()
    return row
class Handler(apex_admin.AdminMixin,BaseHTTPRequestHandler):
    server_version="APEX-Client"
    sys_version=""
    def log_message(self,fmt,*args):
        logging.info("client endpoint=%s method=%s",self.path.split("?")[0][:90],self.command)
    def reply(self,status,body,extra=None):
        data=json.dumps(body,separators=(",",":"),allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'none'")
        if extra:
            for key,value in extra:self.send_header(key,value)
        self.send_header("Content-Length",str(len(data)))
        self.end_headers();self.wfile.write(data)
    def csrf_allowed(self):
        return self.headers.get("Origin") in ORIGINS and self.headers.get("Sec-Fetch-Site","same-origin") in ("same-origin","none",None)
    def read_json(self):
        if self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
            raise ValueError("JSON required")
        try:n=int(self.headers.get("Content-Length","0"))
        except ValueError:raise ValueError("Invalid content length")
        if n<=0 or n>4096:raise ValueError("Invalid request size")
        x=json.loads(self.rfile.read(n))
        if not isinstance(x,dict):raise ValueError("JSON object required")
        return x
    def authenticated(self):
        row=verify_session(self.headers.get("Cookie"))
        if row is None:
            self.reply(401,{"error":"Sign in to continue."})
            return None
        return row
    def do_GET(self):
        if self.path=="/account/api/client/admin/runtime-health":
            account=self.authenticated()
            if account is None:return
            if not self.admin_session(account):return
            return self.reply(200,read_trading_health())
        if self.path=="/account/api/client/runtime-health":
            account=self.authenticated()
            if account is None:return
            global_health=read_trading_health()
            with db_connect() as c:
                rows=c.execute("""SELECT x.broker,x.environment,x.status,COALESCE(t.effective_enabled,0)
                    FROM apex_mt5_connections x
                    LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
                    WHERE x.account_id=?""",(account[0],)).fetchall()
            counts={}
            for broker,env,status,effective in rows:
                if env!="DEMO" or broker not in ("Deriv","FP Markets","IC Markets"):continue
                counts[broker]=counts.get(broker,{"connected":0,"account_controls_on":0})
                if status=="CONNECTED":
                    counts[broker]["connected"]+=1
                    counts[broker]["account_controls_on"]+=int(effective==1)
            out={"schema":"abutron.apex.runtime_health.readonly.v1",
                 "available":global_health.get("available") is True,
                 "checked_at_utc":global_health.get("checked_at_utc"),
                 "scope":"AUTHENTICATED_CLIENT_ACCOUNTS_ONLY",
                 "environment":"DEMO","execution_authority":False,
                 "portfolio_ceiling_pct":20,"accounts":counts,
                 "platform_signal_research":{"source":"PLATFORM_RESEARCH_NOT_ACCOUNT_ORDER_APPROVAL",
                     "deriv_scanner_status":global_health.get("deriv",{}).get("scanner_status","UNVERIFIED") if counts.get("Deriv",{}).get("connected",0) else "NO_DERIV_ACCOUNT",
                     "deriv_hold_reasons":global_health.get("deriv",{}).get("signal_reasons",{}) if counts.get("Deriv",{}).get("connected",0) else {},
                     "deriv_m5_directional_symbols":global_health.get("deriv",{}).get("m5_directional_symbols") if counts.get("Deriv",{}).get("connected",0) else None,
                     "fp_market_coverage":global_health.get("fpmarkets",{}).get("symbols_verified") if counts.get("FP Markets",{}).get("connected",0) else None}}
            return self.reply(200,out)
        if self.path=="/account/api/client/admin/fp-native-history":
            account=self.authenticated()
            if account is None:return
            if not self.admin_session(account):return
            try:return self.reply(200,abutron_fp_history_portal.admin_snapshot(db_connect))
            except (OSError,ValueError,TypeError,KeyError,OverflowError,sqlite3.Error):
                return self.reply(503,{"available":False,"reason":"FP_HISTORY_SOURCE_UNAVAILABLE"})
        if self.path=="/account/api/client/admin/fp-market":
            account=self.authenticated()
            if account is None:return
            if not self.admin_session(account):return
            try:return self.reply(200,abutron_fp_market_portal.admin_snapshot(db_connect))
            except (OSError,ValueError,TypeError,KeyError,OverflowError,sqlite3.Error):
                return self.reply(503,{"available":False,"error":"FP Markets source unavailable or stale."})
        if self.path.startswith("/account/api/client/admin/"):
            return self.admin_get()
        if self.path=="/account/api/client/ai-engine":
            account=self.authenticated()
            if account is None:return
            try:
                from urllib.request import urlopen
                with urlopen("http://127.0.0.1:18888/api/apex11-engines",timeout=3.0) as res:
                    data=json.loads(res.read(25000))
                if data.get("schema")!="abutron.apex11.operator_dashboard.readonly.v1":
                    raise ValueError("APEX 1.1 source mismatch")
                components=data.get("research_components",[])
                return self.reply(200,{
                    "schema":"abutron.apex.client_apex11_engine.readonly.v1",
                    "checked_at_utc":data.get("checked_at_utc"),
                    "engine":data.get("engine","APEX 1.1.0"),
                    "fresh_publishers":data.get("fresh_account_publishers",0),
                    "total_publishers":data.get("total_account_publishers",5),
                    "observed_components":sum(1 for x in components if isinstance(x,dict) and x.get("recent_output_observed") is True),
                    "total_components":6,
                    "orders_submitted_by_publishers":data.get("orders_submitted_by_publishers"),
                    "broker_execution_verified":False,
                    "fp_apex11_link_verified":data.get("fp_apex11_engine_link_verified") is True,
                    "scope":"PLATFORM_RESEARCH_NOT_ACCOUNT_EXECUTION"})
            except (OSError,ValueError,TypeError,KeyError,TimeoutError):
                return self.reply(503,{"schema":"abutron.apex.client_apex11_engine.readonly.v1","available":False})
        if self.path=="/account/api/client/health":
            return self.reply(200,{"client_portal":"operational","live_execution":"disabled","broker_linking":"demo_terminal_manager_installed_execution_off"})
        if self.path=="/account/api/client/me":
            account=self.authenticated()
            if account is None:return
            account_id,name,email,country,status,demo,live=account
            return self.reply(200,{"name":name,"email":email,"country":country,"status":status,
                "demo_execution_enabled":False,"live_execution_enabled":False,
                "broker_trading_enabled":False,"email_verification_required":status!="approved",
                "role":("SUPERADMIN" if apex_admin.role_row(account) else "CUSTOMER"),
                "crm_license":apex_crm.client_license(account_id),
                "crm_subscription":apex_crm.client_subscription(account_id)})
        if self.path=="/account/api/client/fp-native-history":
            account=self.authenticated()
            if account is None:return
            if account[4]!="approved":return self.reply(403,{"available":False,"reason":"VERIFY_EMAIL_FIRST"})
            try:return self.reply(200,abutron_fp_history_portal.client_snapshot(db_connect,account[0]))
            except (OSError,ValueError,TypeError,KeyError,OverflowError,sqlite3.Error):
                return self.reply(503,{"available":False,"reason":"FP_HISTORY_SOURCE_UNAVAILABLE"})
        if self.path=="/account/api/client/fp-market":
            account=self.authenticated()
            if account is None:return
            if account[4]!="approved":
                return self.reply(403,{"available":False,"error":"Verify your email first."})
            try:return self.reply(200,abutron_fp_market_portal.client_snapshot(db_connect,account[0]))
            except (OSError,ValueError,TypeError,KeyError,OverflowError,sqlite3.Error):
                return self.reply(503,{"available":False,"error":"FP Markets source unavailable or stale."})
        if self.path=="/account/api/client/mt5/gateway":
            account=self.authenticated()
            if account is None:return
            return self.reply(200,abutron_mt5_portal_adapter.probe())
        if self.path=="/account/api/client/connections":
            account=self.authenticated()
            if account is None:return
            return apex_mt5_linking.get_connections(self,db_connect,account[0])
        m=re.fullmatch(r"/account/api/client/connections/([a-f0-9]{32})/status",self.path)
        if m:
            account=self.authenticated()
            if account is None:return
            return abutron_mt5_portal_adapter.status(self,account[0],m.group(1))
        if self.path=="/account/api/client/license/summary":
            account=self.authenticated()
            if account is None:return
            with db_connect() as c:
                return self.reply(200,{"trial":apex_trial.trial(c,account[0]),
                        "requests":apex_trial.requests(c,account[0]),
                        "crm_license":apex_crm.client_license(account[0]),
                        "pricing":apex_pricing.catalog(),
                        "payment_provider_connected":False})
        if self.path=="/account/api/client/license-permissions":
            account=self.authenticated()
            if account is None:return
            with db_connect() as c:
                return self.reply(200,apex_crm_license_policy.list_client(c,account[0]))
        if self.path=="/account/api/client/trading-controls":
            account=self.authenticated()
            if account is None:return
            return apex_trading_controls.list_controls(self,db_connect,account[0])
        if self.path=="/account/api/client/requests":
            account=self.authenticated()
            if account is None:return
            with db_connect() as c:
                rows=c.execute("""SELECT id,broker,platform,environment,account_reference,broker_server,status,created_at
                                  FROM broker_link_requests WHERE account_id=?
                                  ORDER BY created_at DESC LIMIT 30""",(account[0],)).fetchall()
            return self.reply(200,{"requests":[dict(zip(("id","broker","platform","environment","account_reference",
                  "broker_server","status","created_at"),r)) for r in rows],
                  "note":"Account connections are pending verification. No broker trades are enabled."})
        return self.reply(404,{"error":"Not found"})
    def do_POST(self):
        if self.path==apex_customer_worker_entitlement.PATH:
            try:payload=self.read_json()
            except (ValueError,UnicodeDecodeError):
                return self.reply(400,{"allowed":False,"reason_codes":["INVALID_JSON"]})
            return apex_customer_worker_entitlement.handle(self,db_connect,payload)
        if not self.csrf_allowed():return self.reply(403,{"error":"Secure same-origin request required."})
        try:x=self.read_json()
        except (ValueError,UnicodeDecodeError):
            return self.reply(400,{"error":"Invalid request."})
        if self.path.startswith("/account/api/client/admin/"):
            return self.admin_post(x)
        if self.path=="/account/api/client/login":return self.login(x)
        if self.path=="/account/api/client/logout":return self.logout()
        matched=re.fullmatch(r"/account/api/client/trading-controls/([a-f0-9]{32})",self.path)
        if matched:
            account=self.authenticated()
            if account is None:return
            if account[4]!="approved":return self.reply(403,{"error":"Verify your email first."})
            return apex_trading_controls.change_control(self,db_connect,account[0],matched.group(1),x)
        legacy_mt5_otp=re.fullmatch(r"/account/api/client/connections/([a-f0-9]{32})/auth/(begin|finish)",self.path)
        if legacy_mt5_otp:
            return self.reply(410,{"error":"The additional MT5 email-code step has been removed. Refresh the client portal and use direct DEMO MT5 broker verification."})
        mt5_direct=re.fullmatch(r"/account/api/client/connections/([a-f0-9]{32})/auth/connect",self.path)
        if mt5_direct:
            account=self.authenticated()
            if account is None:return
            if account[4]!="approved":return self.reply(403,{"error":"Verify your ABUTRON account email first."})
            return self.reply(410,{"error":"Legacy MT5 one-shot verification was retired. Use Connect Trading Account."})
        if self.path=="/account/api/client/connections/mt5/start":
            return self.reply(410,{"error":"Enrollment-only MT5 linking was removed. Use Connect Trading Account once the dedicated MT5 service is operational."})
        if self.path=="/account/api/client/connections/mt5/connect":
            account=self.authenticated()
            if account is None:return
            if account[4]!="approved":return self.reply(403,{"error":"Verify your ABUTRON account email first."})
            return abutron_mt5_portal_adapter.connect(self,db_connect,account[0],x)
        if self.path=="/account/api/client/license/request":
            account=self.authenticated()
            if account is None:return
            if account[4]!="approved":return self.reply(403,{"error":"Verify your email first."})
            try:
                with db_connect() as c:
                    c.execute("BEGIN IMMEDIATE")
                    result=apex_trial.create_request(c,account[0],x)
                    c.execute("COMMIT")
                return self.reply(201,result)
            except ValueError as exc:return self.reply(422,{"error":str(exc)})
            except sqlite3.IntegrityError:return self.reply(409,{"error":"A license request is already open."})
        if self.path=="/account/api/client/requests":return self.broker_request(x)
        return self.reply(404,{"error":"Not found"})
    def do_DELETE(self):
        if not self.csrf_allowed():return self.reply(403,{"error":"Secure same-origin request required."})
        account=self.authenticated()
        if account is None:return
        m=re.fullmatch(r"/account/api/client/connections/([a-f0-9]{32})",self.path)
        if m:return abutron_mt5_portal_adapter.disconnect(self,account[0],m.group(1))
        m=re.fullmatch(r"/account/api/client/requests/([a-f0-9]{32})",self.path)
        if not m:return self.reply(404,{"error":"Not found"})
        with db_connect() as c:
            c.execute("DELETE FROM broker_link_requests WHERE account_id=? AND id=?",(account[0],m.group(1)))
        return self.reply(200,{"status":"request_removed","execution_enabled":False})
    def login(self,x):
        email=x.get("email","");password=x.get("password","")
        if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or not EMAIL_RE.fullmatch(email.strip()) or len(password)<1 or len(password)>128:
            return self.reply(401,{"error":"Email or password incorrect."})
        email=email.strip().casefold()
        ip=self.headers.get("X-APEX-Client-IP","")
        if not IP_RE.fullmatch(ip):
            return self.reply(403,{"error":"Secure client routing required."})
        stamp=now_epoch()
        digest=ip_digest(ip)
        with db_connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM client_login_attempts WHERE attempted_at<?",(stamp-86400,))
            n=c.execute("SELECT count(*) FROM client_login_attempts WHERE ip_hmac=? AND attempted_at>?",(digest,stamp-3600)).fetchone()[0]
            if n>=12:
                c.execute("COMMIT")
                return self.reply(429,{"error":"Too many sign-in attempts. Try again later."})
            c.execute("INSERT INTO client_login_attempts(ip_hmac,attempted_at) VALUES(?,?)",(digest,stamp))
            c.execute("COMMIT")
        if not SEMAPHORE.acquire(blocking=False):
            return self.reply(429,{"error":"Sign-in service busy; retry shortly."})
        try:
            with db_connect() as c:
                row=c.execute("SELECT id,password_hash,status FROM accounts WHERE email=?",(email,)).fetchone()
            if row is None:fake_password_work(password);return self.reply(401,{"error":"Email or password incorrect."})
            if not valid_password(password,row[1]) or row[2] not in ("approved","pending_review"):
                return self.reply(401,{"error":"Email or password incorrect."})
        finally:SEMAPHORE.release()
        token=secrets.token_hex(32)
        with db_connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM client_sessions WHERE expires_at<=?",(stamp,))
            c.execute("DELETE FROM client_sessions WHERE account_id=?",(row[0],))
            c.execute("INSERT INTO client_sessions(token_hash,account_id,created_at,expires_at) VALUES(?,?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(),row[0],stamp,stamp+SESSION_LIFETIME))
            c.execute("COMMIT")
        cookie="apex_client="+token+"; Path=/account; Max-Age="+str(SESSION_LIFETIME)+"; Secure; HttpOnly; SameSite=Strict"
        return self.reply(200,{"status":"authenticated","account_status":row[2],"live_execution_enabled":False},
                          [("Set-Cookie",cookie)])
    def logout(self):
        token=cookie_token(self.headers.get("Cookie"))
        if token:
            with db_connect() as c:c.execute("DELETE FROM client_sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
        return self.reply(200,{"status":"signed_out"},
            [("Set-Cookie","apex_client=; Path=/account; Max-Age=0; Secure; HttpOnly; SameSite=Strict")])
    def broker_request(self,x):
        account=self.authenticated()
        if account is None:return
        if account[4]!="approved":
            return self.reply(403,{"error":"Verify your email before adding a trading account."})
        broker=x.get("broker");platform=x.get("platform");env=x.get("environment")
        reference=x.get("account_reference","");server=x.get("broker_server","")
        if not (broker in ("Deriv","IC Markets","FP Markets") and platform in ("MT5","cTrader")
                and env in ("DEMO","LIVE") and (broker!="Deriv" or platform=="MT5")
                and isinstance(reference,str) and REF_RE.fullmatch(reference)
                and isinstance(server,str) and SERVER_RE.fullmatch(server)
                and x.get("understand_not_connected") is True):
            return self.reply(422,{"error":"Valid account details and acknowledgement are required. No passwords or secrets accepted."})
        if any(k.lower() in ("password","secret","token","api_key","authorization") for k in x):
            return self.reply(422,{"error":"Do not send broker credentials or passwords to this endpoint."})
        with db_connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if not apex_crm.accepting_requests(c,broker,platform):
                c.execute("ROLLBACK")
                return self.reply(409,{"error":"This broker intake channel is currently paused."})
            count=c.execute("SELECT count(*) FROM broker_link_requests WHERE account_id=?",(account[0],)).fetchone()[0]
            if count>=8:
                c.execute("ROLLBACK")
                return self.reply(429,{"error":"Maximum pending requests reached."})
            reference=reference.strip();server=server.strip()
            status="oauth_pending" if platform=="cTrader" else "verification_pending"
            try:
                c.execute("""INSERT INTO broker_link_requests
                    (id,account_id,broker,platform,environment,account_reference,broker_server,status,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",(secrets.token_hex(16),account[0],broker,platform,env,reference,server,status,now_iso()))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return self.reply(409,{"error":"This account verification request already exists."})
            account_flow.notice(c,account[0],"broker_notice")
            c.execute("COMMIT")
        return self.reply(201,{"status":status,"connection_status":"not_connected",
            "live_execution_enabled":False,"message":"Request recorded. Broker authorization and ownership verification are still required."})

if __name__=="__main__":
    init()
    http=ThreadingHTTPServer((HOST,PORT),Handler)
    logging.info("APEX client portal listening on loopback port %d; broker execution disabled",PORT)
    http.serve_forever(poll_interval=0.5)
