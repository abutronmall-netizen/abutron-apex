"""APEX Resend webhook: Svix signature verification, dedupe and delivery ledger."""
import base64, hashlib, hmac, json, re, sqlite3, time
from pathlib import Path
from account_flow import BASE

SECRET=Path("/var/lib/apex-signup/resend_webhook_secret")
EVENTS={"email.sent","email.delivered","email.delivery_delayed","email.bounced",
        "email.complained","email.failed","email.suppressed"}

def handle(h):
    if not SECRET.is_file():
        return h.send_json(503,{"error":"Webhook not configured"})
    try:
        n=int(h.headers.get("Content-Length","0"))
        if not 0<n<=65536:raise ValueError("size")
        raw=h.rfile.read(n)
        sid=h.headers.get("svix-id","")
        stamp=h.headers.get("svix-timestamp","")
        signatures=h.headers.get("svix-signature","")
        if len(sid)>160 or not re.fullmatch(r"[a-zA-Z0-9_\-]{5,160}",sid):
            raise ValueError("id")
        if not re.fullmatch(r"[0-9]{10,11}",stamp) or abs(time.time()-int(stamp))>300:
            raise ValueError("timestamp")
        secret=SECRET.read_text().strip()
        if not secret.startswith("whsec_"):raise ValueError("secret")
        key=base64.b64decode(secret[6:]+"===")
        expected=base64.b64encode(hmac.new(key,
            sid.encode()+b"."+stamp.encode()+b"."+raw,hashlib.sha256).digest()).decode()
        if not any(sig.startswith("v1,") and hmac.compare_digest(sig[3:],expected)
                   for sig in signatures.split()):
            raise ValueError("signature")
        event=json.loads(raw)
        if not isinstance(event,dict):raise ValueError("json")
        typ=event.get("type")
        if typ not in EVENTS:raise ValueError("event")
        data=event.get("data")
        if not isinstance(data,dict):data={}
        email_id=str(data.get("email_id",""))[:128]
    except (ValueError,TypeError,UnicodeDecodeError,json.JSONDecodeError):
        return h.send_json(401,{"error":"Invalid webhook signature or payload"})
    # No email address, content, bearer token or recovery link stored in event ledger.
    import registration
    with registration.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        inserted=db.execute("""INSERT OR IGNORE INTO resend_webhook_events
                     (svix_id,event_type,provider_message_id,received_at)
                     VALUES(?,?,?,?)""",(sid,typ,email_id,int(time.time()))).rowcount
        if inserted and email_id:
            row=db.execute("""SELECT id FROM email_outbox WHERE provider_message_id=?""",
                            (email_id,)).fetchone()
            if row:
                db.execute("""INSERT INTO account_email_delivery(job_id,last_event,updated_at)
                      VALUES(?,?,?) ON CONFLICT(job_id) DO UPDATE SET
                      last_event=excluded.last_event,updated_at=excluded.updated_at""",
                      (row[0],typ,int(time.time())))
        db.execute("COMMIT")
    return h.send_json(200,{"status":"received"})
