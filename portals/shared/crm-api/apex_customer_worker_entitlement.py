"""APEX customer broker new-entry server-to-server admission. NO broker orders.

Only the signed, freshly authenticated worker may request a decision.
No signed request, no independently verified MT5 connection, no paid/trial seat,
or no confirmed account-specific execution control => DENY.
"""
from __future__ import annotations
import base64,binascii,datetime as dt,json,re,sqlite3,time
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import apex_crm_license_policy as policy
import apex_pricing
import apex_crm_subscriptions as subscriptions

PUBLIC_KEY=Path("/etc/abutron/apex-customer-worker-public.b64")
PATH="/account/api/client/worker/entry-check"
FIELDS=frozenset(("timestamp","nonce","account_id","connection_id","broker","platform",
                  "environment","account_reference","broker_server","worker_binding"))
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS apex_customer_worker_nonces(
        nonce TEXT PRIMARY KEY,checked_at INTEGER NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS apex_customer_worker_nonces_date ON apex_customer_worker_nonces(checked_at)")
def verify(headers,payload,now=None):
    if set(payload)!=FIELDS:raise ValueError("INVALID_SIGNED_FIELDS")
    now=int(time.time() if now is None else now)
    timestamp=payload.get("timestamp")
    if type(timestamp) is not int or abs(timestamp-now)>35:raise ValueError("STALE_TIMESTAMP")
    nonce=payload.get("nonce")
    if not isinstance(nonce,str) or not re.fullmatch(r"[a-f0-9]{32}",nonce):raise ValueError("INVALID_NONCE")
    for field in ("account_id","connection_id","broker","platform","environment","account_reference","broker_server","worker_binding"):
        if not isinstance(payload.get(field),str) or not 1<=len(payload[field])<=110:
            raise ValueError("INVALID_IDENTITY_FIELD")
    if not re.fullmatch(r"[a-f0-9]{32}",payload["connection_id"]):raise ValueError("BAD_CONNECTION_ID")
    if not re.fullmatch(r"[a-zA-Z0-9-]{8,80}",payload["account_id"]):raise ValueError("BAD_CLIENT_ID")
    if payload["platform"]!="MT5" or payload["environment"]!="DEMO":raise ValueError("CUSTOMER_DEMO_MT5_ONLY")
    if payload["broker"] not in ("Deriv","IC Markets","FP Markets"):raise ValueError("BROKER_NOT_APPROVED")
    if not PUBLIC_KEY.is_file():raise ValueError("WORKER_PUBLIC_KEY_UNAVAILABLE")
    key_data=base64.b64decode(PUBLIC_KEY.read_text().strip(),validate=True)
    signature=headers.get("X-APEX-Worker-Signature","")
    if len(signature)>128:raise ValueError("BAD_SIGNATURE")
    try:
        signature_bytes=base64.b64decode(signature,validate=True)
        if len(signature_bytes)!=64:raise ValueError("BAD_SIGNATURE")
        Ed25519PublicKey.from_public_bytes(key_data).verify(signature_bytes,canonical(payload))
    except (InvalidSignature,ValueError,TypeError,binascii.Error) as exc:
        raise ValueError("INVALID_WORKER_SIGNATURE") from exc
def evaluate(c,payload):
    aid=payload["account_id"];cid=payload["connection_id"]
    # A SUPERADMIN who also owns a verified paid customer seat is subject to
    # exactly the same per-account entitlement and effective execution gates.
    # Administrator role alone never grants trading authorization.
    record=c.execute("""SELECT account_id,broker,environment,account_reference,broker_server,
       status,broker_verified_at,worker_binding FROM apex_mt5_connections WHERE id=?""",(cid,)).fetchone()
    if record is None:return False,["CUSTOMER_CONNECTION_NOT_FOUND"],"none"
    actual=dict(zip(("account_id","broker","environment","account_reference","broker_server",
                     "status","broker_verified_at","worker_binding"),record))
    for field in ("account_id","broker","environment","account_reference","broker_server","worker_binding"):
        if payload[field]!=actual[field]:return False,["SIGNED_BROKER_IDENTITY_MISMATCH"],"none"
    decision=policy.connection_decision(c,aid,cid)
    if decision is None:return False,["CONNECTION_POLICY_NOT_FOUND"],"none"
    reasons=list(decision["reason_codes"])
    basis=decision["license_basis"]
    if basis=="paid":
        license_rec=c.execute("SELECT plan,seats FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone()
        subscription=subscriptions.current(c,aid)
        if not license_rec or license_rec[1]!=apex_pricing.SEATS.get(license_rec[0],-1):
            reasons.append("PAID_LICENSE_SEAT_LIMIT_INVALID")
        if not subscription:reasons.append("PAID_SUBSCRIPTION_NOT_RECORDED")
        elif (subscription["plan"]!=license_rec[0] if license_rec else True) or (
            subscription["currency"]!="ZAR" or subscription["billing_interval"]!="monthly"
            or subscription["amount_minor"]!=apex_pricing.PRICES.get(subscription["plan"])):
            reasons.append("SUBSCRIPTION_PLAN_OR_PRICE_MISMATCH")
        elif subscription["status"]!="active":reasons.append("PAID_SUBSCRIPTION_INACTIVE")
        elif not subscription["renewal_on"] or subscription["renewal_on"]<dt.date.today().isoformat():
            reasons.append("PAID_SUBSCRIPTION_RENEWAL_OVERDUE")
    if not decision["new_entries_allowed"] or not decision["broker_worker_connected"]:
        if not reasons:reasons.append("ENTRY_POLICY_NOT_APPROVED")
    return not reasons,reasons,basis
def handle(handler,connect,payload):
    try:
        verify(handler.headers,payload)
    except (ValueError,OSError,TypeError,binascii.Error) as e:
        return handler.reply(401,{"schema":"apex.customer.entry.v1","allowed":False,
                    "reason_codes":[str(e)[:64]],"protective_exit_rights_preserved":True})
    try:
        with connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM apex_customer_worker_nonces WHERE checked_at<?",(int(time.time())-180,))
            try:
                c.execute("INSERT INTO apex_customer_worker_nonces(nonce,checked_at) VALUES(?,?)",
                          (payload["nonce"],int(time.time())))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return handler.reply(409,{"schema":"apex.customer.entry.v1","allowed":False,
                      "reason_codes":["NONCE_ALREADY_USED"],"protective_exit_rights_preserved":True})
            allowed,reasons,basis=evaluate(c,payload)
            c.execute("""INSERT INTO apex_crm_license_decision_audit
                (account_id,connection_id,action,decision,reason,evaluated_at) VALUES(?,?,?,?,?,?)""",
                (payload["account_id"],payload["connection_id"],"NEW_ENTRY",
                 "ALLOW" if allowed else "DENY",",".join(reasons)[:300],
                 dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()))
            c.execute("COMMIT")
        return handler.reply(200,{"schema":"apex.customer.entry.v1","allowed":allowed,
          "nonce":payload["nonce"],"connection_id":payload["connection_id"],
          "license_basis":basis,"reason_codes":reasons,"max_age_seconds":8,
          "protective_exit_rights_preserved":True,
          "live_trading_enabled":False})
    except (sqlite3.Error,KeyError,ValueError,TypeError):
        return handler.reply(503,{"schema":"apex.customer.entry.v1","allowed":False,
                 "reason_codes":["ENTITLEMENT_SERVICE_UNAVAILABLE"],
                 "protective_exit_rights_preserved":True})
