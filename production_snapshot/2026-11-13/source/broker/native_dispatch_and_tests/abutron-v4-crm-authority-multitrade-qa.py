#!/usr/bin/python3
"""ABUTRON Deriv 6207 phase-aware status and guarded CLAIM/SEND transport.

A STATUS response is broker/CRM evidence, not trade authorization.
The root-owned CRM/broker status service directly validates revision-fenced
CLAIM/SEND. No separately loaded guardian module or process is required.
"""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import re
import runpy
import stat
import sqlite3
import time
from socketserver import ThreadingMixIn
from decimal import Decimal, InvalidOperation
import json
import secrets

# Integrated direct CRM/broker authorization: deterministic, DEMO 6207 only.
CID="d6fc2524ec373b8d1bc278a8be3ec635"
DB="/var/lib/apex-signup/accounts.sqlite3"
BASE=Path("/var/lib/abutron-v4-broker-crm-supervisor-6207")
HEALTH=Path("/var/lib/private/abutron-client-mt5-"+CID+"/worker-health.json")
SHA="83f9ea4c23f81064a1fcdfe9c902f1a9824799d99d799e52d02e5ea3a1dec275"
SYMBOLS={"Volatility "+str(x)+" Index.0" for x in (10,25,50,75,100)}
HEX32=re.compile(r"[0-9a-f]{32}\Z")
HEX64=re.compile(r"[0-9a-f]{64}\Z")
NUM=re.compile(r"[0-9]{1,9}(\.[0-9]{1,9})?\Z")
NAT=re.compile(r"[1-9][0-9]{0,17}\Z")
class Denied(Exception): pass

def decode(raw, now):
    if not isinstance(raw,bytes) or not 10<len(raw)<=1024 or b"\x00" in raw:
        raise Denied("BODY")
    try: p=raw.decode("ascii").splitlines()
    except UnicodeError as ex: raise Denied("ASCII") from ex
    if len(p)!=14 or p[0]!="ABUTRON_V4_LOCAL_GUARD_V1":
        print("ABUTRON_V4_POST_FORMAT line_count="+str(len(p))+" bytes="+str(len(raw))+" first_line_length="+str(len(p[0]) if p else 0)+" nul="+str(b"\x00" in raw),flush=True)
        raise Denied("PROTOCOL")
    _,phase,nonce,signal,login,server,symbol,side,lots,sl,tp,rev,exp,lease=p
    if (phase not in ("CLAIM","SEND") or not HEX32.fullmatch(nonce) or
        not HEX64.fullmatch(signal) or login!="32456207" or server!="Deriv-Demo" or
        symbol not in SYMBOLS or side not in ("BUY","SELL") or
        not NAT.fullmatch(rev) or not NAT.fullmatch(exp) or
        not int(exp)>=now or int(exp)>now+12 or
        (lease!="-" if phase=="CLAIM" else not HEX64.fullmatch(lease))):
        raise Denied("IDENTITY_PHASE_EXPIRY")
    try:
        if not all(NUM.fullmatch(x) for x in (lots,sl,tp)):raise Denied("FORMAT")
        v,s,t=(Decimal(x) for x in (lots,sl,tp))
        if not Decimal(".01")<=v<=Decimal("100") or s<=0 or t<=0:
            raise Denied("SIZE_STOP")
        if (side=="BUY" and not s<t) or (side=="SELL" and not t<s):
            raise Denied("STOP_TP_GEOMETRY")
    except (ValueError,InvalidOperation) as ex:raise Denied("NUMERIC") from ex
    digest=hashlib.sha256("\n".join((nonce,signal,login,server,symbol,side,lots,sl,tp,rev,exp)).encode("ascii")).hexdigest()
    return dict(phase=phase,nonce=nonce,signal=signal,revision=int(rev),
                expiry=int(exp),lease=lease,digest=digest)

def fresh(path, now, ttl):
    s=path.lstat()
    if path.is_symlink() or s.st_size>150000 or s.st_size<2 or now-s.st_mtime>ttl or s.st_mtime>now+2:
        raise Denied("STALE_ATTESTATION")
    return json.loads(path.read_bytes())

def attest(req, now):
    try:
        h=fresh(HEALTH,now,25)
        a=fresh(BASE/"v4-ro-attachment-evidence.json",now,95)
        r=fresh(BASE/"customer-wide-risk-evidence.json",now,95)
        owner=fresh(BASE/"evidence.json",now,95)
        om=owner.get("metrics",{}).get("apex11_owner_operational_risk",{})
        oc=owner.get("checks",{})
        am=a.get("metrics",{}); ac=a.get("checks",{})
        return (h.get("id")==CID and h.get("mode")=="DEMO" and
            h.get("broker")=="Deriv" and h.get("server")=="Deriv-Demo" and
            h.get("status")=="CONNECTED" and h.get("heartbeat_fresh") is True and
            h.get("nonce")==req["nonce"] and
            a.get("state")=="V4_NATIVE_CHART_ATTACHED" and
            ac.get("exact_v4_release_binary_installed") is True and
            ac.get("independent_native_mt5_chart_load") is True and
            am.get("release_sha256")==SHA and
            am.get("automatic_order_input_enabled_at_last_init") is True and
            am.get("v4_revision_capability_file_present") is True and
            r.get("native_current_open_exposure_reconciled") is True and
            r.get("native_position_sets_verified")==r.get("connected_accounts") and
            r.get("unknown_connected_position_sets")==0 and
            oc.get("customer_cashflow_adjusted_portfolio_risk") is True and
            oc.get("exclusive_writer_and_unknown_orders_reconciled") is True and
            om.get("owner_native_current_risk_proven") is True and
            om.get("preserved_3pct_daily_cash_loss_limit") is True and
            om.get("preserved_20pct_portfolio_open_risk_ceiling") is True and
            r.get("live_authorized") is False)
    except (OSError,ValueError,TypeError,Denied): return False

DDL="""CREATE TABLE IF NOT EXISTS abutron_v4_6207_send_lease (
 signal_id TEXT PRIMARY KEY, lease_id TEXT NOT NULL UNIQUE,
 revision INTEGER NOT NULL CHECK(revision>=1), request_digest TEXT NOT NULL,
 created_utc INTEGER NOT NULL, expires_utc INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('CLAIMED','SEND_UNKNOWN','RECONCILED')),
 updated_utc INTEGER NOT NULL)"""

def migrate(db=DB):
    c=sqlite3.connect(db,timeout=8,isolation_level=None)
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute(DDL)
        c.commit()
    except BaseException:
        c.rollback(); raise
    finally:c.close()

def transact(raw, db=DB, now=None, check=None, direct_intent=False):
    n=int(time.time()) if now is None else int(now)
    q=decode(raw,n)
    if not (attest(q,n) if check is None else check(q,n)):
        raise Denied("INDEPENDENT_BROKER_AND_RISK_PROOF")
    c=sqlite3.connect(db,timeout=4,isolation_level=None)
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            rows=c.execute("""SELECT f.revision,f.desired_enabled,f.effective_enabled,
              f.connection_status,f.ack_revision,f.ack_expires_utc,
              t.desired_enabled,t.effective_enabled,x.status
              FROM abutron_v4_6207_activation_revision f
              JOIN apex_trade_controls t ON t.connection_id=f.connection_id
              JOIN apex_mt5_connections x ON x.id=f.connection_id
              WHERE f.connection_id=? AND x.broker='Deriv'
              AND x.environment='DEMO' AND x.account_reference='32456207'
              AND x.broker_server='Deriv-Demo'""",(CID,)).fetchall()
            if len(rows)!=1:raise Denied("CRM_ACCOUNT")
            rev,d,e,st,ack,until,d2,e2,st2=rows[0]
            if (rev!=q["revision"] or rev!=ack or
                not d==e==d2==e2==1 or st!=st2 or st!="CONNECTED" or
                until is None or until<n): raise Denied("CLIENT_OFF_STALE_OR_NO_ACK")
            if direct_intent:
                direct_require_in_transaction(c,q,n)
            owner=c.execute("""SELECT 1 FROM apex_mt5_connections x
                JOIN accounts a ON a.id=x.account_id
                JOIN apex_crm_licenses l ON l.account_id=a.id
                JOIN apex_admin_roles r ON r.account_id=a.id
                WHERE x.id=? AND a.status='approved' AND
                l.plan='Enterprise' AND l.status='active' AND l.seats=3 AND
                r.role='SUPERADMIN' AND r.email_verified_at IS NOT NULL""",(CID,)).fetchall()
            if len(owner)!=1:raise Denied("OWNER_LICENSE_MFA")
            seen=c.execute("""SELECT lease_id,revision,request_digest,expires_utc,status
                 FROM abutron_v4_6207_send_lease WHERE signal_id=?""",(q["signal"],)).fetchone()
            if q["phase"]=="CLAIM":
                if seen:raise Denied("REPLAY")
                # At most one unresolved native writer intent for this account.
                if c.execute("""SELECT 1 FROM abutron_v4_6207_send_lease
                    WHERE status='SEND_UNKNOWN' OR
                    (status='CLAIMED' AND expires_utc>=?) LIMIT 1""",
                    (n,)).fetchone():
                    raise Denied("EXCLUSIVE_WRITER_BUSY_OR_UNKNOWN_RECEIPT")
                lease=secrets.token_hex(32)
                c.execute("""INSERT INTO abutron_v4_6207_send_lease VALUES(?,?,?,?,?,?,?,?)""",
                    (q["signal"],lease,rev,q["digest"],n,q["expiry"],"CLAIMED",n))
            else:
                if not seen:raise Denied("NO_CLAIM")
                lease,lsrev,hash_,expires,status=seen
                if (q["lease"]!=lease or lsrev!=rev or hash_!=q["digest"]
                    or expires!=q["expiry"] or status!="CLAIMED"):
                    raise Denied("REPLAY_OR_STALE_LEASE")
                if c.execute("""UPDATE abutron_v4_6207_send_lease
                     SET status='SEND_UNKNOWN',updated_utc=?
                     WHERE signal_id=? AND revision=? AND status='CLAIMED'""",
                     (n,q["signal"],rev)).rowcount!=1: raise Denied("SEND_RACE")
            if direct_intent:
                direct_advance_in_transaction(c,q,n)
            c.commit()
            return "ALLOW|"+lease+"\n"
        except BaseException:
            c.rollback();raise
    finally:c.close()



PORT = 19743
TOKEN_PATH = Path("/etc/abutron/v4-6207-readonly-ack.token")
INSPECTOR_PATH = "/usr/local/sbin/abutron-v4-broker-crm-supervisor-6207"
HEX64 = re.compile(r"^[a-f0-9]{64}$")
REQUIRED = (
    "root_inspector",
    "apex_crm_owner_mfa_account_binding",
    "apex_enterprise_license",
    "apex_v7_same_owner",
    "v7_remains_readonly",
    "crm_monotonic_revision_ledger",
    "client_requested_on",
    "deriv_worker_fresh_identity",
    "deriv_independent_readonly_broker_session",
    "deriv_native_account_snapshot",
    "live_orders_disabled",
    "unapproved_dispatch_inactive",
)

def trusted_secret_digest(path=TOKEN_PATH):
    if path.is_symlink():
        raise RuntimeError("TOKEN_SYMLINK")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
                stat.S_IMODE(st.st_mode) != 0o400 or st.st_nlink != 1 or
                st.st_size != 65):
            raise RuntimeError("TOKEN_MODE_SIZE_DENIED")
        data = os.read(fd, 66)
        if len(data) != 65 or data[-1:] != b"\n":
            raise RuntimeError("TOKEN_TRUNCATED")
        raw = data[:-1].decode("ascii")
        if not HEX64.fullmatch(raw):
            raise RuntimeError("TOKEN_FORMAT_DENIED")
        return hashlib.sha256(data[:-1]).digest()
    finally:
        os.close(fd)

# Integrated short-lived root-approved exact-order intent ledger.
DIRECT_CID="d6fc2524ec373b8d1bc278a8be3ec635"
DIRECT_DB="/var/lib/apex-signup/accounts.sqlite3"
DIRECT_HEX64=re.compile(r"^[0-9a-f]{64}$")
DIRECT_HEX32=re.compile(r"^[0-9a-f]{32}$")
DIRECT_DDL="""CREATE TABLE IF NOT EXISTS abutron_v4_6207_direct_intents(
 signal_id TEXT PRIMARY KEY CHECK(length(signal_id)=64),
 account_id TEXT NOT NULL,
 worker_nonce TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>=1),
 request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
 expires_utc INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('APPROVED','CLAIMED','SEND_UNKNOWN')),
 created_utc INTEGER NOT NULL,
 updated_utc INTEGER NOT NULL
)"""


def direct_digest_fields(*,nonce,signal,login,server,symbol,side,lots,sl,tp,revision,expiry):
    fields=[nonce,signal,login,server,symbol,side,lots,sl,tp,str(revision),str(expiry)]
    if not (DIRECT_HEX32.fullmatch(nonce) and DIRECT_HEX64.fullmatch(signal)
            and login=="32456207" and server=="Deriv-Demo"
            and symbol in {"Volatility 10 Index.0","Volatility 25 Index.0",
                           "Volatility 50 Index.0","Volatility 75 Index.0",
                           "Volatility 100 Index.0"}
            and side in ("BUY","SELL") and all(isinstance(x,str) and
            0<len(x)<=80 and "\n" not in x and "\r" not in x
            for x in fields)):
        raise Denied("DIRECT_INTENT_INVALID_ACCOUNT_OR_PROTOCOL")
    return hashlib.sha256("\n".join(fields).encode("ascii")).hexdigest()

def direct_migrate(db_path=DIRECT_DB):
    with sqlite3.connect(db_path,timeout=10) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(DIRECT_DDL)

def direct_prepare(request, evidence, *,db_path=DIRECT_DB,now=None):
    """Root APEX V4 writer only, after broker/account and risk reservations.

    Receives verified writer evidence, not HTTP input. Never synthesizes an
    account entitlement, CRM ACK, broker costs or favorable instrument risk.
    """
    n=int(time.time()) if now is None else int(now)
    if (request.account_id!=DIRECT_CID or request.broker!="deriv" or
        request.server!="Deriv-Demo" or request.mt5_login!="32456207" or
        type(request.activation_revision) is not int or
        type(request.expires_at_utc) is not int or
        not n<request.expires_at_utc<=n+15):
        raise Denied("DIRECT_INTENT_6207_ONLY")
    gate=evidence.gate
    native=evidence.native
    if (gate.connection_id!=CID or gate.environment!="DEMO" or
        gate.server!="Deriv-Demo" or gate.broker!="deriv" or
        gate.owner!=request.customer_id or
        evidence.worker_nonce!=request.worker_nonce or
        evidence.mt5_login!=request.mt5_login or
        evidence.effective_activation_revision!=request.activation_revision or
        evidence.native_ea_protocol<4 or not evidence.revision_fenced_by_native_ea or
        not evidence.native_ea_heartbeat_fresh or
        not evidence.legacy_writer_same_lock_verified or
        not evidence.outstanding_unknown_orders_reconciled or
        not gate.crm_entitlement_approved or
        not gate.customer_switch_effective or
        not gate.single_writer_exclusive or
        not gate.broker_exposure_reconciled or
        not native.broker_calc_profit_verified or
        not native.broker_order_check_verified):
        raise Denied("INDEPENDENT_APEX_BROKER_RISK_EVIDENCE_NOT_CERTIFIED")
    d=direct_digest_fields(nonce=request.worker_nonce,signal=request.signal_id,
      login=request.mt5_login,server=request.server,symbol=request.symbol,
      side=request.side,lots=request.volume_lots,sl=request.stop_price,
      tp=request.take_price,revision=request.activation_revision,
      expiry=request.expires_at_utc)
    with sqlite3.connect(db_path,timeout=5,isolation_level=None) as db:
        try:
            db.execute("BEGIN IMMEDIATE")
            f=db.execute("""SELECT f.revision,f.desired_enabled,f.effective_enabled,
               f.ack_revision,f.ack_expires_utc,t.desired_enabled,t.effective_enabled,
               x.status,x.account_id FROM abutron_v4_6207_activation_revision f
               JOIN apex_trade_controls t ON t.connection_id=f.connection_id
               JOIN apex_mt5_connections x ON x.id=f.connection_id
               WHERE f.connection_id=? AND x.broker='Deriv' AND x.environment='DEMO'
               AND x.account_reference='32456207' AND x.broker_server='Deriv-Demo'""",
               (DIRECT_CID,)).fetchone()
            if (not f or f[0]!=request.activation_revision or
                (f[1],f[2],f[3],f[5],f[6],f[7],f[8])!=
                (1,1,request.activation_revision,1,1,"CONNECTED",request.customer_id) or
                type(f[4]) is not int or f[4]<=n):
                raise Denied("CRM_ON_REVISION_ACK_INVALID")
            db.execute("""INSERT INTO abutron_v4_6207_direct_intents
               VALUES(?,?,?,?,? ,?,'APPROVED',?,?)""",
               (request.signal_id,DIRECT_CID,request.worker_nonce,request.activation_revision,
                d,request.expires_at_utc,n,n))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return d

def direct_require_in_transaction(db,q,n):
    """Call INSIDE the direct CRM service's BEGIN IMMEDIATE transaction."""
    row=db.execute("""SELECT account_id,worker_nonce,revision,
                  request_digest,expires_utc,state,created_utc
                  FROM abutron_v4_6207_direct_intents WHERE signal_id=?""",
                  (q["signal"],)).fetchone()
    if (row is None or row[:5]!=(DIRECT_CID,q["nonce"],q["revision"],
        q["digest"],q["expiry"]) or not n<=row[4]<=n+12 or
        not n-row[6]>=0 or n-row[6]>15 or
        row[5]!=("APPROVED" if q["phase"]=="CLAIM" else "CLAIMED")):
        raise Denied("NO_ROOT_APPROVED_EXACT_ORDER_INTENT")

def direct_advance_in_transaction(db,q,n):
    state="CLAIMED" if q["phase"]=="CLAIM" else "SEND_UNKNOWN"
    prior="APPROVED" if q["phase"]=="CLAIM" else "CLAIMED"
    if db.execute("""UPDATE abutron_v4_6207_direct_intents
              SET state=?,updated_utc=? WHERE signal_id=? AND revision=?
              AND request_digest=? AND state=?""",
              (state,n,q["signal"],q["revision"],q["digest"],prior)).rowcount!=1:
        raise Denied("DIRECT_ORDER_INTENT_RACE")


def transact_direct(raw):
    return transact(raw,direct_intent=True)

def readonly_revision(report):
    if (not isinstance(report, dict) or
        report.get("schema") != "abutron.v4.broker_crm.readonly.admission.v1" or
        report.get("state") != "BLOCKED" or
        report.get("production_release_certified") is not False or
        report.get("order_authorized") is not False or
        report.get("orders_submitted") != 0 or
        report.get("client_switches_modified") is not False or
        report.get("read_only_evidence_only") is not True or
        report.get("broker") != "Deriv" or
        report.get("environment") != "DEMO" or
        report.get("account_suffix") != "6207"):
        raise ValueError("READONLY_ONLY_REPORT_REQUIRED")
    checks = report.get("checks")
    if not isinstance(checks, dict) or any(checks.get(x) is not True for x in REQUIRED):
        raise ValueError("READONLY_BROKER_CRM_NOT_ATTESTED")
    # This endpoint deliberately operates only BEFORE activation; it must
    # never be interpreted as an effective client permission or order ACK.
    if checks.get("client_effective_on") is not False:
        raise ValueError("EFFECTIVE_EXECUTION_NOT_OFF")
    metrics = report.get("metrics")
    revision = metrics.get("crm_revision") if isinstance(metrics, dict) else None
    if type(revision) is not int or not 1 <= revision < 2**63:
        raise ValueError("CRM_REVISION_INVALID")
    if metrics.get("crm_broker_ack_recorded") is not False:
        raise ValueError("EXECUTION_ACK_MUST_NOT_BE_PRESENT")
    return revision


# STATUS is an authenticated session/revision heartbeat, NEVER an order grant.
# PREPARE and ACTIVE are verified independently to avoid an ACK deadlock.
def current_native_active_proof(report):
    now = int(time.time())
    metrics = report.get("metrics", {})
    rev = metrics.get("crm_revision")
    try:
        with sqlite3.connect("file:/var/lib/apex-signup/accounts.sqlite3?mode=ro",
                             uri=True, timeout=3) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute("""SELECT f.revision,f.desired_enabled,
                f.effective_enabled,f.ack_revision,f.ack_expires_utc,
                x.status,t.desired_enabled,t.effective_enabled
                FROM abutron_v4_6207_activation_revision f
                JOIN apex_mt5_connections x ON x.id=f.connection_id
                JOIN apex_trade_controls t ON t.connection_id=f.connection_id
                WHERE f.connection_id=? AND x.broker='Deriv' AND
                x.environment='DEMO' AND x.account_reference='32456207' AND
                x.broker_server='Deriv-Demo'""",
                ("d6fc2524ec373b8d1bc278a8be3ec635",)).fetchone()
        if (row is None or type(rev) is not int or
            row[:4] != (rev, 1, 1, rev) or
            type(row[4]) is not int or row[4] <= now or
            row[5:] != ("CONNECTED", 1, 1)):
            return False
        health = fresh(HEALTH, now, 25)
        nonce = health.get("nonce")
        if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
            return False
        chart = fresh(BASE/"v4-ro-attachment-evidence.json", now, 95)
        cc=chart.get("checks",{})
        return (health.get("id")==CID and health.get("broker")=="Deriv"
             and health.get("mode")=="DEMO" and health.get("server")=="Deriv-Demo"
             and health.get("status")=="CONNECTED" and health.get("heartbeat_fresh") is True
             and chart.get("state")=="V4_NATIVE_CHART_ATTACHED"
             and cc.get("independent_native_mt5_chart_load") is True
             and cc.get("exact_v4_release_binary_installed") is True
             and chart.get("metrics",{}).get("release_sha256")==SHA)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error, Denied):
        return False

# GET STATUS is an MT5 session heartbeat, not an OrderSend permit.
# The POST CLAIM/SEND path independently verifies current risk, writer and CRM state.
ACTIVE_REQUIRED = tuple(k for k in REQUIRED if k != "unapproved_dispatch_inactive")

def status_revision(report, active_proof=None):
    # Legacy PREPARE behavior remains byte-for-byte compatible with the EA.
    try:
        return readonly_revision(report)
    except ValueError:
        pass
    # ACTIVE is not inferred from a CRM flag. It requires authenticated,
    # owner-bound broker/EA/risk attestation and matching unexpired CRM ACK.
    if (not isinstance(report, dict) or
        report.get("schema") != "abutron.v4.broker_crm.readonly.admission.v1" or
        report.get("broker") != "Deriv" or
        report.get("environment") != "DEMO" or
        report.get("account_suffix") != "6207" or
        report.get("client_switches_modified") is not False or
        report.get("orders_submitted") != 0 or
        report.get("read_only_evidence_only") is not True or
        report.get("live_authorized") is True):
        raise ValueError("ACTIVE_STATUS_BROKER_IDENTITY_UNVERIFIED")
    checks = report.get("checks")
    metrics = report.get("metrics")
    if (not isinstance(checks, dict) or not isinstance(metrics, dict) or
        any(checks.get(key) is not True for key in ACTIVE_REQUIRED) or
        checks.get("client_effective_on") is not True or
        metrics.get("crm_broker_ack_recorded") is not True or
        metrics.get("crm_broker_ack_revision_matches") is not True):
        raise ValueError("ACTIVE_STATUS_CRM_ACK_OR_NATIVE_GATES_MISSING")
    revision = metrics.get("crm_revision")
    if (type(revision) is not int or not 1 <= revision < 2**63 or
        not callable(active_proof) or active_proof(report) is not True):
        raise ValueError("ACTIVE_STATUS_INDEPENDENT_BROKER_PROOF_MISSING")
    return revision

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    # Permit immediate, still-exclusive localhost rebind after controlled restart.
    # SO_REUSEADDR is not SO_REUSEPORT; concurrent listeners remain rejected.
    allow_reuse_address = True

def make_handler(inspect, expected_digest, guard_transact=None, active_proof=None,
                 direct_transact=None):
    class ReadOnlyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "ABUTRON-ReadOnly/1"
        sys_version = ""
        def log_message(self, fmt, *args):
            # Never log token, revisions, customer identities or paths.
            return
        def deny(self):
            self.send_response(403)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"DENY\n")
        def authorized(self):
            tokens = self.headers.get_all("X-Abutron-Worker-Token", [])
            if len(tokens) != 1 or not HEX64.fullmatch(tokens[0]):
                return False
            if self.client_address[0] != "127.0.0.1":
                return False
            return hmac.compare_digest(hashlib.sha256(tokens[0].encode("ascii")).digest(), expected_digest)
        def do_GET(self):
            direct_path=(self.path=="/v4/direct/status")
            if direct_path:
                if self.client_address[0]!="127.0.0.1":return self.deny()
            elif self.path!="/v4/status" or not self.authorized():
                return self.deny()
            try:
                revision = status_revision(inspect(), active_proof)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                return self.deny()
            content = f"STATUS|{revision}\n".encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def do_POST(self):
            print("ABUTRON_V4_POST_ARRIVED path="+str(self.path),flush=True)
            direct_path=(self.path=="/v4/direct/authorize")
            if direct_path:
                if self.client_address[0]!="127.0.0.1" or not callable(direct_transact):
                    return self.deny()
                transact_handler=direct_transact
            elif self.path=="/v4/guard" and self.authorized() and callable(guard_transact):
                transact_handler=guard_transact
            else:
                return self.deny()
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or not 10 < int(length) <= 1024:
                return self.deny()
            try:
                answer = transact_handler(self.rfile.read(int(length)))
                if not isinstance(answer, str) or not re.fullmatch(r"ALLOW\|[a-f0-9]{64}\n", answer):
                    return self.deny()
            except Exception as ex:
                # Existing native CRM denial diagnostics: reason codes only.
                # No request bodies, broker credentials, owner ID or tokens logged.
                if direct_path:
                    code=str(ex)
                    if not re.fullmatch(r"[A-Z0-9_]{3,96}",code):
                        code=type(ex).__name__
                    print("ABUTRON_V4_DIRECT_REQUEST_REJECTED " + code,flush=True)
                return self.deny()
            raw = answer.encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_PUT(self):
            return self.deny()
        do_PATCH = do_DELETE = do_PUT
    return ReadOnlyHandler

def main():
    if os.geteuid() != 0:
        raise SystemExit("ROOT_INSPECTOR_REQUIRED")
    # A single root-owned CRM/broker service replaces the separate guardian.
    # No plugin, per-worker path or local OFF flag can mint an order permit.
    me=Path("/usr/local/sbin/abutron-v4-readonly-status-6207")
    if (me.is_symlink() or me.stat().st_uid != 0 or
        stat.S_IMODE(me.stat().st_mode) != 0o500 or
        me.stat().st_nlink != 1):
        raise RuntimeError("DIRECT_CRM_BROKER_AUTH_SOURCE_UNTRUSTED")
    digest = trusted_secret_digest()
    scope = runpy.run_path(INSPECTOR_PATH, run_name="_abutron_v4_readonly_only")
    inspect = scope["inspect"]
    # Direct CRM/broker authorization now lives in this root-owned service.
    active_proof = current_native_active_proof
    # Restarting in ACTIVE must work. The previous PREPARE-only startup check
    # would have killed the status service immediately after a valid ACK.
    if status_revision(inspect(), active_proof) < 1:
        raise SystemExit("V4_INDEPENDENT_PHASE_STATUS_PROOF_MISSING")
    # Existing DB schema is explicitly migrated under transactional lock.
    direct_migrate()
    server = ThreadedHTTPServer(("127.0.0.1", PORT),
                                make_handler(inspect, digest,
                                    guard_transact=transact,
                                    active_proof=active_proof,
                                    direct_transact=transact_direct))
    print("ABUTRON_V4_CRM_BROKER_DIRECT_AUTH_READY; CLAIM_SEND_ATTESTATION_REQUIRED", flush=True)
    server.serve_forever(poll_interval=0.5)

if __name__ == "__main__":
    main()
