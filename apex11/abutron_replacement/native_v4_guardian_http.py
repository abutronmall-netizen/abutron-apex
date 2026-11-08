"""Loopback-only native V4 authorization transport for a privileged MT5/CRM guard.

The server CANNOT be started without an injected real NativeBrokerAuthority.
It never sends orders, updates switches or enables LIVE; it only grants a
short-lived CLAIM and a separate durable SEND lease. Peer authentication uses
a per-worker 256-bit token SHA256 digest; never log or check in the secret.
The process must be owned by the trusted supervisor with a protected SQLite
activation database and root-owned per-worker secret configuration.

IMPORTANT: 127.0.0.1 is not a security boundary against a compromised local
worker. A production installation must additionally isolate Wine/MT5 workers,
verify the exact EA and broker worker nonce and protect against port spoofing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from typing import Callable

from .native_v4_off_fence import NativeV4OffFence, NativeOrderIdentity
from .production_contracts import FeedRefused

TOKEN = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[0-9a-f]{32}$")
PROTOCOL = "ABUTRON_V4_LOCAL_GUARD_V1"
ROUTE = "/v4/guard"


@dataclass(frozen=True)
class LocalGuardianIdentity:
    customer_id: str
    account_id: str
    worker_nonce: str
    mt5_login: str
    token_sha256: str

    def validate(self) -> None:
        if (not all(type(v) is str and ID.fullmatch(v)
                    for v in (self.customer_id,self.account_id,self.worker_nonce))
            or type(self.mt5_login) is not str or
                not self.mt5_login.isascii() or not self.mt5_login.isdecimal()
            or not self.mt5_login.endswith("6207")
            or type(self.token_sha256) is not str or
                not TOKEN.fullmatch(self.token_sha256)):
            raise ValueError("GUARDIAN_TRUSTED_CONFIG_INVALID")


def parse_request(body: bytes, *, pinned: LocalGuardianIdentity,
                  now: datetime) -> tuple[str, NativeOrderIdentity, str]:
    if (type(body) is not bytes or len(body)>2048 or len(body)<50 or
            b"\x00" in body or not body.endswith(b"\n")):
        raise FeedRefused("LOCAL_GUARD_REQUEST_INVALID")
    try:
        lines=body.decode("ascii").splitlines()
    except UnicodeError:
        raise FeedRefused("LOCAL_GUARD_NON_ASCII_REQUEST") from None
    # Exact, fixed 14-line message: version, phase, nonce, signal, login,
    # server, symbol, side, volume, SL, TP, revision, expiry, lease.
    if len(lines)!=14 or lines[0]!=PROTOCOL or lines[1] not in ("CLAIM","SEND"):
        raise FeedRefused("LOCAL_GUARD_PROTOCOL_INVALID")
    _,phase,nonce,signal,login,server,symbol,side,volume,sl,tp,rev,expiry,lease=lines
    if nonce!=pinned.worker_nonce or login!=pinned.mt5_login:
        raise FeedRefused("LOCAL_GUARD_NATIVE_WORKER_IDENTITY_MISMATCH")
    if not rev.isdecimal() or not expiry.isdecimal():
        raise FeedRefused("LOCAL_GUARD_REVISION_OR_EXPIRY_INVALID")
    if (phase=="CLAIM" and lease!="-") or (phase=="SEND" and not TOKEN.fullmatch(lease)):
        raise FeedRefused("LOCAL_GUARD_LEASE_PHASE_INVALID")
    i=NativeOrderIdentity(
        customer_id=pinned.customer_id,account_id=pinned.account_id,
        signal_id=signal,worker_nonce=nonce,login=login,broker="deriv",
        server=server,environment="DEMO",symbol=symbol,side=side,
        volume=volume,sl=sl,tp=tp,revision=int(rev),expires_utc=int(expiry))
    i.validate(now)
    return phase,i,lease


def make_local_guardian(*, fence: NativeV4OffFence,
                        pinned: LocalGuardianIdentity,
                        port: int=19743,
                        clock: Callable[[],datetime] = lambda: datetime.now(timezone.utc)
                        ) -> ThreadingHTTPServer:
    """Never expose this handler on 0.0.0.0 or user-supplied hostnames."""
    pinned.validate()
    if type(port) is not int or port<1024 or port>65535:
        raise ValueError("LOCAL_GUARD_PORT_INVALID")
    expected=bytes.fromhex(pinned.token_sha256)

    class Handler(BaseHTTPRequestHandler):
        protocol_version="HTTP/1.0"

        def log_message(self, format, *args):
            # No worker token, account id, signal, or P/L in HTTP logs.
            pass

        def _deny(self, status=403):
            self.send_response(status)
            self.send_header("Content-Type","text/plain")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length","5")
            self.end_headers()
            self.wfile.write(b"DENY\n")

        def _authorized(self) -> bool:
            secret=self.headers.get("X-Abutron-Worker-Token","")
            return (self.client_address[0]=="127.0.0.1" and
                    type(secret) is str and TOKEN.fullmatch(secret) is not None and
                    hmac.compare_digest(sha256(secret.encode("ascii")).digest(),expected))

        def do_GET(self):
            if self.path!="/v4/status":
                self._deny(405)
                return
            if not self._authorized():
                self._deny(403)
                return
            attest=getattr(fence.authority,"attest_session",None)
            if not callable(attest):
                self._deny(403)
                return
            try:
                revision=attest(customer_id=pinned.customer_id,
                    account_id=pinned.account_id,
                    worker_nonce=pinned.worker_nonce,
                    mt5_login=pinned.mt5_login,now=clock())
                if type(revision) is not int or revision<1:
                    raise FeedRefused("NATIVE_STATUS_REVISION_NOT_ATTESTED")
                response=("STATUS|"+str(revision)+"\n").encode("ascii")
            except (FeedRefused,ValueError,PermissionError,OSError,TypeError):
                self._deny(403)
                return
            self.send_response(200)
            self.send_header("Content-Type","text/plain")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def do_POST(self):
            if self.path!=ROUTE or not self._authorized():
                self._deny(403)
                return
            length=self.headers.get("Content-Length","")
            if not length.isdecimal() or not 50<=int(length)<=2048:
                self._deny(413)
                return
            try:
                now=clock()
                phase,i,lease=parse_request(
                    self.rfile.read(int(length)),pinned=pinned,now=now)
                if phase=="CLAIM":
                    outcome=fence.claim(identity=i,now=now)
                else:
                    outcome=fence.send(identity=i,lease_id=lease,now=now)
                response=("ALLOW|"+outcome.lease_id+"\n").encode("ascii")
            except (FeedRefused, ValueError, PermissionError, OSError,
                    TypeError, KeyError):
                self._deny(403)
                return
            self.send_response(200)
            self.send_header("Content-Type","text/plain")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    return ThreadingHTTPServer(("127.0.0.1",port),Handler)
