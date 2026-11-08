"""Atomic DEMO-only V4 MT5 request file transport, with no V3 fallback.

The existing installed EA accepts APEX_NATIVE_ADAPTIVE_ORDER_V3 without CRM
activation revision. This port requires a separate *native-EA-produced* V4
capability heartbeat and writes to ABUTRON_APEX_V4.req so the V3 EA cannot
consume an unapproved order. It is not enough to create a capability text file:
trusted supervisor MUST prove native EA binary identity and broker session.
No V4 EA has yet been verified installed on production localhost.

The native V4 EA must re-read current CRM revision, kill switch, account
identity, OrderCheck, OrderCalcProfit and available stop risk immediately
before calling OrderSend and include revision in its authenticated receipt.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import os
import re
import stat
import time
from typing import Callable

from .exclusive_native_writer import DemoNativeRequest, BrokerExecutionEvidence
from .production_contracts import FeedRefused, HEX32

V4_CAPABILITY_PREFIX="ABUTRON_APEX_NATIVE_V4_CAPABILITY_"
V4_CAPABILITY_MAGIC="APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4"
V4_REQUEST_NAME="ABUTRON_APEX_V4.req"
V3_REQUEST_NAME="APEX_NATIVE_ORDER_V1.req"
V4_PROTOCOL="APEX_NATIVE_ACCOUNT_BOUND_ORDER_V4"
_HASH64=re.compile(r"^[a-f0-9]{64}$")


def _read_protected(path: Path, expected_uid: int, max_size: int = 2048) -> list[str]:
    if path.is_symlink():
        raise FeedRefused("NATIVE_CAPABILITY_SYMLINK")
    before=path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_size<1 or
            before.st_size>max_size or before.st_mode&0o022 or
            before.st_uid!=expected_uid):
        raise FeedRefused("NATIVE_CAPABILITY_UNSAFE")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        first=os.fstat(fd)
        data=os.read(fd,max_size+1)
        second=os.fstat(fd)
    finally:
        os.close(fd)
    keys=("st_dev","st_ino","st_size","st_mtime_ns")
    if tuple(getattr(first,k) for k in keys)!=tuple(getattr(second,k) for k in keys):
        raise FeedRefused("NATIVE_CAPABILITY_RACED")
    if first.st_ino!=before.st_ino or len(data)!=before.st_size:
        raise FeedRefused("NATIVE_CAPABILITY_CHANGED")
    try:
        return data.decode("utf-8-sig").splitlines()
    except UnicodeError:
        raise FeedRefused("NATIVE_CAPABILITY_ENCODING_INVALID") from None


def _decimal(s: str) -> Decimal:
    try:
        if not isinstance(s,str) or len(s)>32:
            raise ValueError
        d=Decimal(s)
    except (ValueError,InvalidOperation):
        raise FeedRefused("V4_NATIVE_PRICE_OR_VOLUME_INVALID") from None
    if not d.is_finite() or d<=0:
        raise FeedRefused("V4_NATIVE_PRICE_OR_VOLUME_INVALID")
    return d


class NativeV4FilePort:
    """A single account's MT5 MQL5/Files folder, provisioned by trusted worker.

    No path supplied over HTTP. Never replaces an existing request; uses
    atomic hard-link publication after fsync. Transport success is NOT a fill.
    """

    def __init__(self, *, account_id: str, account_login: str,
                 files_dir: Path, worker_uid: int,
                 clock: Callable[[],float] = time.time):
        if not isinstance(account_id,str) or not HEX32.fullmatch(account_id):
            raise ValueError("NATIVE_FILE_PORT_ACCOUNT_ID_INVALID")
        if (not isinstance(account_login,str) or not account_login.isascii()
                or not account_login.isdecimal() or not account_login.endswith("6207")):
            raise ValueError("NATIVE_FILE_PORT_6207_LOGIN_INVALID")
        if type(worker_uid) is not int or worker_uid<=0:
            raise ValueError("NATIVE_FILE_PORT_WORKER_UID_UNVERIFIED")
        self.worker_uid=worker_uid
        self.account_id=account_id
        self.account_login=account_login
        self.files_dir=Path(files_dir)
        self.clock=clock

    def _dirs(self) -> tuple[Path,Path]:
        root=self.files_dir
        folder=root/"ABUTRON"
        receipts=folder/"receipts"
        for path in (root,folder,receipts):
            st=path.lstat()
            if (not stat.S_ISDIR(st.st_mode) or path.is_symlink()
                    or st.st_mode & 0o022 or st.st_uid != self.worker_uid):
                raise FeedRefused("NATIVE_MQL5_ORDER_FOLDER_UNSAFE")
        return folder,receipts

    def _capability(self, request: DemoNativeRequest):
        if (request.account_id!=self.account_id or
                request.mt5_login!=self.account_login or
                request.broker!="deriv" or request.server!="Deriv-Demo" or
                request.side not in ("BUY","SELL") or
                not isinstance(request.worker_nonce,str) or
                not HEX32.fullmatch(request.worker_nonce)):
            raise FeedRefused("NATIVE_V4_ACCOUNT_OR_NONCE_MISMATCH")
        lines=_read_protected(self.files_dir/(
            V4_CAPABILITY_PREFIX+request.worker_nonce+".txt"),self.worker_uid)
        # This proves only that the *worker-protected filesystem* has a recent
        # capability record. Independent binary/session attestation is mandatory.
        expected=[V4_CAPABILITY_MAGIC,request.worker_nonce,request.mt5_login,
                  "Deriv-Demo","DEMO",str(request.activation_revision)]
        if (len(lines)!=10 or lines[:6]!=expected or
                lines[7:]!=["0.10","OFF_REVISION_CHECK_AT_CONSUME","LIVE_FORBIDDEN"]):
            raise FeedRefused("V4_NATIVE_REVISION_FENCE_CAPABILITY_INVALID")
        try:
            produced=int(lines[6])
        except (ValueError,TypeError):
            raise FeedRefused("V4_NATIVE_CAPABILITY_CLOCK_INVALID") from None
        if not -2<=self.clock()-produced<=12:
            raise FeedRefused("V4_NATIVE_CAPABILITY_STALE")

    def assert_ready(self, request: DemoNativeRequest,
                     evidence: BrokerExecutionEvidence) -> None:
        if (evidence.native_ea_protocol!=4 or
                not evidence.revision_fenced_by_native_ea or
                not evidence.native_ea_heartbeat_fresh or
                request.activation_revision!=evidence.effective_activation_revision or
                request.signal_id!=evidence.proposal.signal_id):
            raise FeedRefused("REVISION_FENCED_V4_EA_NOT_ATTESTED")
        if not _HASH64.fullmatch(request.signal_id) or (
            type(request.activation_revision) is not int or
            request.activation_revision<1):
            raise FeedRefused("V4_SIGNAL_OR_REVISION_INVALID")
        now=self.clock()
        if not now+1<request.expires_at_utc<=now+15:
            raise FeedRefused("V4_REQUEST_EXPIRED_OR_UNBOUNDED")
        vol=_decimal(request.volume_lots)
        entry=Decimal(str(evidence.native.price))
        stop=_decimal(request.stop_price)
        take=_decimal(request.take_price)
        if (evidence.proposal.symbol != request.symbol or vol <= 0):
            raise FeedRefused("V4_INSTRUMENT_OR_LOT_MISMATCH")
        if request.side=="BUY" and not(stop<entry<take):
            raise FeedRefused("V4_BUY_SL_TP_INVALID")
        if request.side=="SELL" and not(take<entry<stop):
            raise FeedRefused("V4_SELL_SL_TP_INVALID")
        folder,receipts=self._dirs()
        if (folder/V4_REQUEST_NAME).exists() or (folder/V3_REQUEST_NAME).exists():
            raise FeedRefused("NATIVE_V3_OR_V4_REQUEST_ALREADY_PENDING")
        if (receipts/(request.signal_id+".txt")).exists():
            raise FeedRefused("BROKER_RECEIPT_ALREADY_EXISTS")
        self._capability(request)

    def queue_once(self, request: DemoNativeRequest,
                   evidence: BrokerExecutionEvidence) -> None:
        self.assert_ready(request,evidence)
        folder,_=self._dirs()
        # Deliberately different filename and magic from installed V3 EA.
        # No guessed "AUTO" volume: native V4 EA must verify exact explicit
        # reserved lot size and stop geometry using OrderCheck/CalcProfit.
        lines=[V4_PROTOCOL,request.worker_nonce,request.signal_id,
               request.mt5_login,request.server,request.symbol,request.side,
               request.volume_lots,request.stop_price,request.take_price,
               str(request.activation_revision),str(request.expires_at_utc),
               "SEND_DEMO_ONLY"]
        # MQL5 FileReadString(FILE_TXT) uses CRLF record delimiters.\n        # Explicit CRLF prevents a 13-field V4 request being misparsed.\n        content=("\r\n".join(lines)+"\r\n").encode("ascii")
        dirfd=os.open(folder,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)
                      |getattr(os,"O_NOFOLLOW",0))
        name=".abutron-apex11-"+request.signal_id+".tmp"
        try:
            fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_WRONLY
                       |getattr(os,"O_NOFOLLOW",0),0o600,dir_fd=dirfd)
            try:
                if os.geteuid()==0:
                    os.fchown(fd,self.worker_uid,os.fstat(dirfd).st_gid)
                elif os.fstat(fd).st_uid != self.worker_uid:
                    raise FeedRefused("V4_REQUEST_OWNER_UID_UNVERIFIED")
                with os.fdopen(fd,"wb") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.link(name,V4_REQUEST_NAME,src_dir_fd=dirfd,
                            dst_dir_fd=dirfd,follow_symlinks=False)
                except FileExistsError:
                    raise FeedRefused("V4_NATIVE_REQUEST_ALREADY_PRESENT") from None
                os.fsync(dirfd)
            finally:
                os.unlink(name,dir_fd=dirfd)
        finally:
            os.close(dirfd)
