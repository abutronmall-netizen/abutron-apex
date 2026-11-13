"""Abutron staged SQLite multi-process MT5 enrollment gate. Never collects passwords.
The DB holds keyed HMAC owner/IP and challenge digests, not logins, passwords,
account numbers or contact details. Integration with customer JWT/MFA is mandatory
and NOT present here. Public enrollment must remain HTTP 423.
"""
from __future__ import annotations
import hashlib,hmac,ipaddress,os,pathlib,secrets,sqlite3,stat,time,uuid
from contextlib import contextmanager

class EnrollmentBlocked(Exception):pass

class SharedEnrollmentGate:
    def __init__(self,storage: str,key: bytes):
        if type(key) is not bytes or len(key)!=32:
            raise EnrollmentBlocked("DEDICATED_32_BYTE_KEY_REQUIRED")
        root=pathlib.Path(storage)
        info=root.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid():
            raise EnrollmentBlocked("PRIVATE_OWNER_DIRECTORY_REQUIRED")
        self.path=root/"rate-limits.sqlite3"
        if self.path.is_symlink():
            raise EnrollmentBlocked("UNSAFE_DATABASE_PATH")
        if self.path.exists():
            st=self.path.lstat()
            if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o600 or st.st_uid!=os.getuid():
                raise EnrollmentBlocked("OWNER_PRIVATE_DATABASE_REQUIRED")
        else:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            os.close(fd)
        self.key=key
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (subject TEXT NOT NULL, at INTEGER NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_attempts_scope ON attempts(subject,at)")
            db.execute("CREATE TABLE IF NOT EXISTS challenge (digest TEXT PRIMARY KEY,owner TEXT NOT NULL, expires INTEGER NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_challenge_exp ON challenge(expires)")
    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()
    def _hash(self,label,value):
        return hmac.new(self.key,("abutron-mt5-gate-v1|"+label+"|"+value).encode(),hashlib.sha256).hexdigest()
    @staticmethod
    def _owner(uid):
        try:
            u=uuid.UUID(uid)
            if u.version!=4 or str(u)!=uid:raise ValueError()
        except (TypeError,AttributeError,ValueError):
            raise EnrollmentBlocked("ATTESTED_OWNER_UUID_REQUIRED") from None
        return uid
    @staticmethod
    def _client_ip(source):
        try:return str(ipaddress.ip_address(source))
        except (TypeError,ValueError):raise EnrollmentBlocked("SERVER_VALIDATED_CLIENT_IP_REQUIRED") from None
    @staticmethod
    def _clock(now):
        n=int(time.time()) if now is None else now
        if type(n) is not int or n<=0:raise EnrollmentBlocked("INVALID_CLOCK")
        return n
    def issue_challenge(self,owner_id,now=None):
        owner=self._hash("owner",self._owner(owner_id))
        t=self._clock(now)
        token=secrets.token_urlsafe(32)
        digest=self._hash("challenge",token)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("DELETE FROM challenge WHERE expires < ?",(t,))
                active=db.execute("SELECT COUNT(*) FROM challenge WHERE owner=?",(owner,)).fetchone()[0]
                if active>=5:raise EnrollmentBlocked("TOO_MANY_OUTSTANDING_CHALLENGES")
                db.execute("INSERT INTO challenge(digest,owner,expires) VALUES(?,?,?)",(digest,owner,t+300))
                db.execute("COMMIT")
            except BaseException:db.execute("ROLLBACK");raise
        return token
    def consume(self,owner_id,server_validated_client_ip,challenge,now=None):
        """Reserve one verified enrollment attempt *before* any broker call.
        Caller must establish strong owner auth+MFA+CSRF before invoking.
        Each challenge can be consumed once. A failed broker login still counts.
        """
        owner=self._hash("owner",self._owner(owner_id))
        remote=self._hash("network",self._client_ip(server_validated_client_ip))
        if type(challenge) is not str or len(challenge)<32 or len(challenge)>128:
            raise EnrollmentBlocked("INVALID_CHALLENGE")
        digest=self._hash("challenge",challenge)
        t=self._clock(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT owner,expires FROM challenge WHERE digest=?",(digest,)).fetchone()
                if row is None or not hmac.compare_digest(row[0],owner) or row[1]<t:
                    raise EnrollmentBlocked("EXPIRED_REPLAYED_OR_WRONG_OWNER")
                db.execute("DELETE FROM challenge WHERE digest=?",(digest,))
                db.execute("DELETE FROM attempts WHERE at<?",(t-900,))
                n_owner=db.execute("SELECT COUNT(*) FROM attempts WHERE subject=? AND at>?",("O:"+owner,t-900)).fetchone()[0]
                n_net=db.execute("SELECT COUNT(*) FROM attempts WHERE subject=? AND at>?",("I:"+remote,t-900)).fetchone()[0]
                if n_owner>=3 or n_net>=12:
                    raise EnrollmentBlocked("SHARED_THROTTLE_ACTIVE")
                db.execute("INSERT INTO attempts(subject,at) VALUES(?,?)",("O:"+owner,t))
                db.execute("INSERT INTO attempts(subject,at) VALUES(?,?)",("I:"+remote,t))
                db.execute("COMMIT")
                return {"reserved":True,"broker_verified":False,"password_collected":False,
                        "can_execute_orders":False,"enrollment_publicly_enabled":False}
            except EnrollmentBlocked:
                # Challenge consumption must persist even for a rate-limited attempt.
                db.execute("COMMIT")
                raise
            except BaseException:
                db.execute("ROLLBACK")
                raise
