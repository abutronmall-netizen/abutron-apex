"""APEX email verification, password recovery and transactional outbox.
No reviewers, MT5 credentials, trading rights, or API keys are stored here.
"""
import hashlib, hmac, secrets, time, re
from pathlib import Path

SECRET = Path("/var/lib/apex-signup/ip_hmac_secret")
BASE = "https://abutronfx.online"
PURPOSES = ("verify", "reset")
TOKEN_RE = re.compile(r"^([a-f0-9]{32})\.([a-f0-9]{64})$")

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS account_email_verification(
        account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        verified_at INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS email_challenges(
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset')),
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        consumed_at INTEGER)""")
    db.execute("CREATE INDEX IF NOT EXISTS email_challenges_lookup ON email_challenges(account_id,purpose,created_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS email_outbox(
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        challenge_id TEXT REFERENCES email_challenges(id),
        purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset','welcome','broker_notice','security')),
        state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','sending','sent','failed')),
        attempts INTEGER NOT NULL DEFAULT 0, next_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL, sent_at INTEGER, provider_message_id TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS email_outbox_queue ON email_outbox(state,next_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS resend_webhook_events(
        svix_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,
        provider_message_id TEXT,received_at INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS account_email_delivery(
        job_id TEXT PRIMARY KEY REFERENCES email_outbox(id) ON DELETE CASCADE,
        last_event TEXT NOT NULL,updated_at INTEGER NOT NULL)""")

def token_for(challenge_id, account_id, purpose, expiry):
    data = f"{challenge_id}|{account_id}|{purpose}|{expiry}".encode()
    signature = hmac.new(SECRET.read_bytes(),data,hashlib.sha256).hexdigest()
    return challenge_id+"."+signature

def verified(db, account_id):
    return db.execute("SELECT 1 FROM account_email_verification WHERE account_id=?",
                      (account_id,)).fetchone() is not None

def enqueue(db, account_id, purpose, now=None, limit=True):
    """Called in caller-owned transaction. Never send mail while holding DB lock."""
    now = now or int(time.time())
    if purpose not in PURPOSES:
        raise ValueError("Invalid challenge purpose")
    if purpose == "verify" and verified(db,account_id):
        return False
    if limit:
        count = db.execute("""SELECT COUNT(*) FROM email_challenges
           WHERE account_id=? AND purpose=? AND created_at>?""",
           (account_id,purpose,now-3600)).fetchone()[0]
        if count >= 3:
            return False
    db.execute("""UPDATE email_challenges SET consumed_at=?
       WHERE account_id=? AND purpose=? AND consumed_at IS NULL""",
       (now,account_id,purpose))
    cid = secrets.token_hex(16)
    ttl = 3600 if purpose == "verify" else 1800
    db.execute("""INSERT INTO email_challenges(id,account_id,purpose,created_at,expires_at)
                  VALUES(?,?,?,?,?)""",(cid,account_id,purpose,now,now+ttl))
    db.execute("""INSERT INTO email_outbox(id,account_id,challenge_id,purpose,next_at,created_at)
                  VALUES(?,?,?,?,?,?)""",
                  (secrets.token_hex(16),account_id,cid,purpose,now,now))
    return True

def notice(db, account_id, purpose, now=None):
    if purpose not in ("welcome","broker_notice","security"):
        raise ValueError("Invalid notice")
    now = now or int(time.time())
    db.execute("""INSERT INTO email_outbox(id,account_id,purpose,next_at,created_at)
                  VALUES(?,?,?,?,?)""",(secrets.token_hex(16),account_id,purpose,now,now))

def consume(db, presented, purpose, password_hasher=None, new_password=None):
    """Transaction must be held by caller. Atomic one-use token and account mutation."""
    matched = TOKEN_RE.fullmatch(presented if isinstance(presented,str) else "")
    if not matched or purpose not in PURPOSES:
        return False
    cid, signature = matched.groups()
    item = db.execute("""SELECT account_id,purpose,expires_at,consumed_at
                         FROM email_challenges WHERE id=?""",(cid,)).fetchone()
    if not item or item[1] != purpose or item[3] is not None or item[2] < int(time.time()):
        return False
    expected = token_for(cid,item[0],purpose,item[2]).split(".")[1]
    if not hmac.compare_digest(signature,expected):
        return False
    now = int(time.time())
    changed=db.execute("""UPDATE email_challenges SET consumed_at=?
       WHERE id=? AND consumed_at IS NULL""",(now,cid)).rowcount
    if changed != 1:
        return False
    aid=item[0]
    if purpose=="verify":
        db.execute("INSERT OR IGNORE INTO account_email_verification(account_id,verified_at) VALUES(?,?)",(aid,now))
        db.execute("""UPDATE accounts SET status='approved'
            WHERE id=? AND status='pending_review'""",(aid,))
        notice(db,aid,"welcome",now)
    else:
        if password_hasher is None or new_password is None:
            raise ValueError("Password reset missing secured hash")
        db.execute("UPDATE accounts SET password_hash=? WHERE id=?",
                   (password_hasher(new_password),aid))
        db.execute("DELETE FROM client_sessions WHERE account_id=?",(aid,))
        db.execute("""UPDATE email_challenges SET consumed_at=?
           WHERE account_id=? AND purpose='reset' AND consumed_at IS NULL""",(now,aid))
        notice(db,aid,"security",now)
    return True
