"""Loopback guardian integration tests: no broker sessions, sockets ephemeral only."""
from datetime import timedelta
from hashlib import sha256
import http.client
import threading

from abutron_replacement.native_v4_guardian_http import (
    LocalGuardianIdentity, make_local_guardian, PROTOCOL, ROUTE,
)
from test_native_v4_off_fence import initialize, START, ACCOUNT, OWNER, NONCE

TOKEN="f"*64


def raw(identity, phase="CLAIM", lease="-", overrides=None):
    values=[PROTOCOL, phase,identity.worker_nonce,identity.signal_id,
            identity.login,identity.server,identity.symbol,identity.side,
            identity.volume,identity.sl,identity.tp,
            str(identity.revision),str(identity.expires_utc),lease]
    for i,v in (overrides or {}).items():
        values[i]=v
    return ("\r\n".join(values)+"\r\n").encode("ascii")


def make(tmp_path):
    act,risk,i,broker,fence=initialize(tmp_path)
    pinned=LocalGuardianIdentity(
        customer_id=OWNER,account_id=ACCOUNT,worker_nonce=NONCE,
        mt5_login="1006207",token_sha256=sha256(TOKEN.encode()).hexdigest())
    # Ephemeral QA-only loopback port.
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    server=make_local_guardian(fence=fence,pinned=pinned,port=port,clock=lambda:START)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    return act,i,broker,fence,server,worker,port


def post(port, body, token=TOKEN, path=ROUTE, method="POST"):
    conn=http.client.HTTPConnection("127.0.0.1",port,timeout=2)
    try:
        conn.request(method,path,body=body,headers={
            "Content-Type":"text/plain",
            "X-Abutron-Worker-Token":token,
        })
        res=conn.getresponse()
        return res.status,res.read().decode("ascii")
    finally:
        conn.close()


def test_loopback_claim_send_and_duplicate_rejected(tmp_path):
    act,i,b,g,server,worker,port=make(tmp_path)
    try:
        status,response=post(port,raw(i))
        assert status==200 and response.startswith("ALLOW|")
        lease=response.split("|",1)[1].strip()
        assert len(lease)==64
        status,result=post(port,raw(i,phase="SEND",lease=lease))
        assert (status,result)==(200,"ALLOW|"+lease+"\n")
        status,result=post(port,raw(i,phase="SEND",lease=lease))
        assert (status,result)==(403,"DENY\n")
        assert b.attempts==["CLAIM","SEND"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_client_off_race_fences_http_send_not_off_status(tmp_path):
    act,i,b,g,server,worker,port=make(tmp_path)
    try:
        status,response=post(port,raw(i))
        assert status==200
        lease=response.split("|",1)[1].strip()
        now=START+timedelta(seconds=2)
        a=act.snapshot(account_id=ACCOUNT,customer_id=OWNER,now=now)
        act.request(account_id=ACCOUNT,customer_id=OWNER,expected_revision=a.revision,
                    desired_on=False,now=now)
        assert post(port,raw(i,phase="SEND",lease=lease))==(403,"DENY\n")
        assert g.off_state(customer_id=OWNER,account_id=ACCOUNT,
                           now=now)=="STOPPING_BROKER_RECONCILIATION_REQUIRED"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_wrong_token_method_path_account_and_phase_denied(tmp_path):
    act,i,b,g,server,worker,port=make(tmp_path)
    try:
        assert post(port,raw(i),token="a"*64)==(403,"DENY\n")
        assert post(port,raw(i),token="")== (403,"DENY\n")
        assert post(port,raw(i),path="/other")== (403,"DENY\n")
        assert post(port,raw(i),method="GET")==(405,"DENY\n")
        assert post(port,raw(i),overrides={4:"1000512"})==(403,"DENY\n")
        assert post(port,raw(i),overrides={6:"GBPUSD"})==(403,"DENY\n")
        assert post(port,raw(i),phase="SEND",lease="0"*64)==(403,"DENY\n")
        assert not b.attempts
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
