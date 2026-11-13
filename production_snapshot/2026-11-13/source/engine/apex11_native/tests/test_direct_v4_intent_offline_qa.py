"""Root-owned QA, no live service, no actual broker orders."""
import http.client
import runpy
import sqlite3
import tempfile
import threading
import time

MODULE=runpy.run_path("/usr/local/sbin/abutron-v4-crm-direct-intent-6207.candidate",
                      run_name="QA_OFFLINE")
NOW=int(time.time())
SIGNAL="a"*64
NONCE="b"*32
LOGIN="32456207"
SYMBOL="Volatility 75 Index.0"
REV=55
EXPIRES=NOW+9
DIGEST=MODULE["direct_digest_fields"](
    nonce=NONCE,signal=SIGNAL,login=LOGIN,server="Deriv-Demo",
    symbol=SYMBOL,side="BUY",lots="0.15",sl="100",tp="120",
    revision=REV,expiry=EXPIRES)
Q=dict(signal=SIGNAL,nonce=NONCE,revision=REV,digest=DIGEST,expiry=EXPIRES,phase="CLAIM")

with tempfile.TemporaryDirectory() as tmp:
    db=tmp+"/direct-qa.sqlite3"
    MODULE["direct_migrate"](db)
    with sqlite3.connect(db,isolation_level=None) as c:
        c.execute("BEGIN IMMEDIATE")
        try: MODULE["direct_require_in_transaction"](c,Q,NOW)
        except MODULE["Denied"]:pass
        else:raise AssertionError("unauthorized CLAIM accepted")
        c.rollback()
        c.execute("BEGIN IMMEDIATE")
        c.execute("""INSERT INTO abutron_v4_6207_direct_intents VALUES
            (?,?,?,?,? ,?,'APPROVED',?,?)""",
            (SIGNAL,MODULE["DIRECT_CID"],NONCE,REV,DIGEST,EXPIRES,NOW,NOW))
        c.commit()
        c.execute("BEGIN IMMEDIATE")
        MODULE["direct_require_in_transaction"](c,Q,NOW)
        MODULE["direct_advance_in_transaction"](c,Q,NOW)
        c.commit()
        try:MODULE["direct_require_in_transaction"](c,Q,NOW)
        except MODULE["Denied"]:pass
        else:raise AssertionError("duplicate CLAIM accepted")
        Q["phase"]="SEND"
        c.execute("BEGIN IMMEDIATE")
        MODULE["direct_require_in_transaction"](c,Q,NOW)
        MODULE["direct_advance_in_transaction"](c,Q,NOW)
        c.commit()
        try:MODULE["direct_require_in_transaction"](c,Q,NOW)
        except MODULE["Denied"]:pass
        else:raise AssertionError("duplicate SEND accepted")
        Q["phase"]="CLAIM"
        Q["revision"]=REV+1
        try:MODULE["direct_require_in_transaction"](c,Q,NOW)
        except MODULE["Denied"]:pass
        else:raise AssertionError("revision forgery accepted")
        print("ATOMIC_ROOT_INTENT_MISSING_CLAIM_SEND_REPLAY_REVISION_QA_PASS")

    # Start an ephemeral QA-only server to validate direct HTTP paths.
    def allow_status():
        return {"schema":"abutron.v4.broker_crm.readonly.admission.v1",
          "state":"BLOCKED","production_release_certified":False,
          "order_authorized":False,"orders_submitted":0,
          "client_switches_modified":False,"read_only_evidence_only":True,
          "broker":"Deriv","environment":"DEMO","account_suffix":"6207",
          "checks":{**{k:True for k in MODULE["REQUIRED"]},"client_effective_on":False},
          "metrics":{"crm_revision":REV,"crm_broker_ack_recorded":False}}
    def deny_direct(body):
        raise MODULE["Denied"]("NO_ROOT_APPROVED_INTENT")
    server=MODULE["ThreadedHTTPServer"](
       ("127.0.0.1",0),MODULE["make_handler"](
          allow_status,b"0"*32,guard_transact=deny_direct,direct_transact=deny_direct))
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:
        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
        conn.request("GET","/v4/direct/status")
        r=conn.getresponse()
        assert (r.status,r.read().decode())==(200,f"STATUS|{REV}\n")
        conn.close()
        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
        conn.request("POST","/v4/direct/authorize",
            b"NO_APPROVED_INTENT",{"Content-Type":"text/plain"})
        r=conn.getresponse()
        assert r.status==403,r.status
        r.read();conn.close()
        print("TOKENLESS_STATUS_AND_MISSING_APPROVAL_HTTP_QA_PASS")
    finally:
        server.shutdown();server.server_close();t.join(timeout=3)
