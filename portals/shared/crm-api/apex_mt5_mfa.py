"""APEX MT5 login action email MFA. No broker secrets are accepted or stored here.

Challenge binds authenticated owner, live client session token hash and a single
MT5 connection enrollment. Only a delivered, fresh, single-use code succeeds.
"""
from __future__ import annotations
import hashlib,hmac,re,secrets,sqlite3,time
from pathlib import Path

SECRET_PATH=Path("/var/lib/apex-signup/mt5_mfa_secret")
TTL_SECONDS=600
SESSION_DIGEST=re.compile(r"^[a-f0-9]{64}$")
ID_RE=re.compile(r"^[a-f0-9]{32}$")
OTP_RE=re.compile(r"^[0-9]{8}$")

class MFAError(Exception):
    pass

def init(db:sqlite3.Connection):
    db.execute("""CREATE TABLE IF NOT EXISTS apex_mt5_mfa(
       id TEXT PRIMARY KEY,
       account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
       connection_id TEXT NOT NULL REFERENCES apex_mt5_connections(id) ON DELETE CASCADE,
       session_hash TEXT NOT NULL,
       created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
       attempts INTEGER NOT NULL DEFAULT 0,
       verified_at INTEGER, consumed_at INTEGER,
       email_state TEXT NOT NULL DEFAULT 'queued'
          CHECK(email_state IN ('queued','sending','sent','failed')),
       email_attempts INTEGER NOT NULL DEFAULT 0,
       email_next_at INTEGER NOT NULL,
       email_sent_at INTEGER
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS apex_mt5_mfa_account_time ON apex_mt5_mfa(account_id,created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS apex_mt5_mfa_queue ON apex_mt5_mfa(email_state,email_next_at)")

def _secret():
    s=SECRET_PATH.lstat()
    import stat,os
    if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o600 or s.st_uid!=os.geteuid():
        raise MFAError("MFA_SECRET_UNSAFE")
    value=SECRET_PATH.read_bytes()
    if len(value)!=32:raise MFAError("MFA_SECRET_INVALID")
    return value

def code_for(secret:bytes,challenge_id:str,account_id:str,connection_id:str,session_hash:str,expires_at:int):
    if type(secret) is not bytes or len(secret)!=32:
        raise MFAError("INVALID_SECRET")
    msg=f"apex:mt5:mfa:v1|{challenge_id}|{account_id}|{connection_id}|{session_hash}|{expires_at}".encode()
    digest=hmac.new(secret,msg,hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:8],'big')%100_000_000:08d}"

def begin(db,account_id:str,connection_id:str,session_hash:str,*,now:int=None):
    now=int(time.time()) if now is None else int(now)
    if not ID_RE.fullmatch(connection_id) or not SESSION_DIGEST.fullmatch(session_hash):
        raise MFAError("INVALID_BINDING")
    # All queries use exact tenant ID, not email or any user-provided customer key.
    row=db.execute("""SELECT c.environment,c.broker,c.broker_server,c.status,a.status
       FROM apex_mt5_connections c JOIN accounts a ON a.id=c.account_id
       WHERE c.id=? AND c.account_id=?""",(connection_id,account_id)).fetchone()
    if not row or row[0]!="DEMO" or row[3]!="CONNECTING" or row[4]!="approved":
        raise MFAError("ACCOUNT_NOT_ELIGIBLE_FOR_DEMO_AUTH")
    approved={
        ("Deriv","Deriv-Demo"),
        ("IC Markets","ICMarketsSC-Demo"),
        ("FP Markets","FPMarketsSC-Demo Server")
    }
    if (row[1],row[2]) not in approved:
        raise MFAError("BROKER_SERVER_NOT_SUPPORTED")
    n=db.execute("SELECT COUNT(*) FROM apex_mt5_mfa WHERE account_id=? AND created_at>?",
                 (account_id,now-3600)).fetchone()[0]
    if n>=3:raise MFAError("MFA_RATE_LIMIT")
    db.execute("""UPDATE apex_mt5_mfa SET email_state='failed'
        WHERE account_id=? AND consumed_at IS NULL AND email_state!='failed'""",(account_id,))
    challenge_id=secrets.token_hex(16)
    db.execute("""INSERT INTO apex_mt5_mfa
       (id,account_id,connection_id,session_hash,created_at,expires_at,email_next_at)
       VALUES(?,?,?,?,?,?,?)""",
       (challenge_id,account_id,connection_id,session_hash,now,now+TTL_SECONDS,now))
    return {"challenge_id":challenge_id,"expires_at":now+TTL_SECONDS,
            "message":"One-time verification email queued. Broker password entry remains disabled."}

def verify_once(db,account_id:str,connection_id:str,session_hash:str,challenge_id:str,otp:str,*,secret:bytes,now:int=None):
    now=int(time.time()) if now is None else int(now)
    if not all((ID_RE.fullmatch(x) for x in (connection_id,challenge_id))) or not SESSION_DIGEST.fullmatch(session_hash):
        raise MFAError("INVALID_BINDING")
    if not isinstance(otp,str) or not OTP_RE.fullmatch(otp):
        raise MFAError("INVALID_CODE")
    row=db.execute("""SELECT account_id,connection_id,session_hash,expires_at,
       attempts,consumed_at,email_state FROM apex_mt5_mfa WHERE id=?""",(challenge_id,)).fetchone()
    if not row or not hmac.compare_digest(row[0],account_id) or not hmac.compare_digest(row[1],connection_id) or not hmac.compare_digest(row[2],session_hash):
        raise MFAError("OWNER_SESSION_CONNECTION_MISMATCH")
    if row[5] is not None or row[3]<=now or row[4]>=5 or row[6]!="sent":
        raise MFAError("MFA_EXPIRED_USED_OR_UNDELIVERED")
    expect=code_for(secret,challenge_id,account_id,connection_id,session_hash,row[3])
    if not hmac.compare_digest(expect,otp):
        db.execute("UPDATE apex_mt5_mfa SET attempts=attempts+1 WHERE id=?",(challenge_id,))
        raise MFAError("INVALID_CODE")
    count=db.execute("""UPDATE apex_mt5_mfa SET consumed_at=? 
         WHERE id=? AND consumed_at IS NULL AND expires_at>?""",(now,challenge_id,now)).rowcount
    if count!=1:raise MFAError("MFA_REPLAY_BLOCKED")
    return True
