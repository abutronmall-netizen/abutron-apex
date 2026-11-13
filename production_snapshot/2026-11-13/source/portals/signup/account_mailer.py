#!/usr/bin/env python3
"""Send APEX account emails via existing Resend credentials. No broker secrets."""
import json, os, sqlite3, sys, time, urllib.request, urllib.error
sys.path.insert(0, "/opt/apex-signup")
import account_flow

DB = "/var/lib/apex-signup/accounts.sqlite3"
def connect():
    c=sqlite3.connect(DB,timeout=12,isolation_level=None)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=12000")
    return c

def main():
    key=os.environ.get("ABUTRON_RESEND_API_KEY","").strip().strip('"').strip("'")
    sender=os.environ.get("ABUTRON_VERIFICATION_FROM_EMAIL","").strip().strip('"').strip("'")
    base=os.environ.get("ABUTRON_PUBLIC_BASE_URL","https://abutronfx.online").rstrip("/")
    if not key or not sender.endswith("@abutronfx.online") or base!="https://abutronfx.online":
        raise RuntimeError("Existing verified Resend configuration is incomplete")
    now=int(time.time())
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("""UPDATE email_outbox SET state='queued',next_at=?
                     WHERE state='sending' AND next_at<?""",(now,now-120))
        row=c.execute("""SELECT j.id,j.account_id,j.challenge_id,j.purpose,j.attempts,
                            a.email,ch.expires_at,ch.consumed_at
                          FROM email_outbox j JOIN accounts a ON a.id=j.account_id
                          LEFT JOIN email_challenges ch ON ch.id=j.challenge_id
                          WHERE j.state='queued' AND j.next_at<=?
                          ORDER BY j.created_at LIMIT 1""",(now,)).fetchone()
        if not row:
            c.execute("COMMIT")
            print("APEX_EMAIL_QUEUE_EMPTY")
            return
        jid,aid,cid,purpose,attempts,email,expiry,consumed=row
        if cid and (consumed is not None or expiry<=now):
            c.execute("UPDATE email_outbox SET state='failed' WHERE id=?",(jid,))
            c.execute("COMMIT")
            print("APEX_EMAIL_CHALLENGE_EXPIRED")
            return
        c.execute("""UPDATE email_outbox SET state='sending', attempts=attempts+1,
                     next_at=? WHERE id=?""",(now,jid))
        c.execute("COMMIT")
    if purpose in ("verify","reset"):
        token=account_flow.token_for(cid,aid,purpose,expiry)
        if purpose=="verify":
            payload={"from":sender,"to":[email],"subject":"Verify your ABUTRON account",
                "template":{"id":"abutron-account-verification","variables":{
                  "VERIFY_URL":base+"/account/verify/#token="+token}}}
        else:
            link=base+"/account/reset/#token="+token
            payload={"from":sender,"to":[email],"subject":"Reset your ABUTRON password",
                "text":"A password reset was requested for your ABUTRON account. Open the secure link below within 30 minutes:\\n\\n"+
                      link+"\\n\\nIf this was not you, ignore this message. Never share your password or the link."}
    elif purpose=="welcome":
        payload={"from":sender,"to":[email],"subject":"Welcome to ABUTRON",
          "template":{"id":"abutron-welcome","variables":{"PORTAL_URL":base+"/account/client/"}}}
    elif purpose=="broker_notice":
        payload={"from":sender,"to":[email],"subject":"ABUTRON MT5 account update",
          "text":"An ABUTRON broker account connection was added, removed, or updated. "
                 "Sign in to review your account connections: "+base+"/account/client/\n\n"
                 "If you did not initiate this change, reset your APEX password and contact support. "
                 "Never share your MT5 password, credentials, or verification codes."}
    else:
        payload={"from":sender,"to":[email],"subject":"ABUTRON account security notification",
          "template":{"id":"abutron-security-alert","variables":{"SECURITY_URL":base+"/account/client/"}}}
    req=urllib.request.Request("https://api.resend.com/emails",
        data=json.dumps(payload).encode(),method="POST",
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json",
                 "User-Agent":"APEX-Transactional/1.0","Idempotency-Key":"apex-"+jid})
    accepted=False; message_id=""
    try:
        with urllib.request.urlopen(req,timeout=13) as response:
            accepted=response.status in (200,201,202)
            if accepted:
                body=json.loads(response.read(4096))
                message_id=str(body.get("id",""))[:100]
    except urllib.error.HTTPError as exc:
        # Never log recipient, payload, bearer credentials or provider response body.
        print("APEX_EMAIL_PROVIDER_HTTP_STATUS",exc.code)
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        print("APEX_EMAIL_PROVIDER_ERROR_TYPE",type(exc).__name__)
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if accepted:
            c.execute("""UPDATE email_outbox SET state='sent',sent_at=?,provider_message_id=?
                          WHERE id=?""",(int(time.time()),message_id,jid))
            print("APEX_EMAIL_PROVIDER_ACCEPTED",purpose)
        else:
            failed = (attempts+1)>=4 or (cid and expiry<=int(time.time())+25)
            c.execute("""UPDATE email_outbox SET state=?,next_at=?
                         WHERE id=?""",("failed" if failed else "queued",
                          int(time.time())+min(240,30*(2**attempts)),jid))
            print("APEX_EMAIL_SEND_RETRY" if not failed else "APEX_EMAIL_FAILED")
        c.execute("COMMIT")

if __name__=="__main__":
    main()
