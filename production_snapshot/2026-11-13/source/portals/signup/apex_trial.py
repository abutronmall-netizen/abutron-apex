"""APEX 24-hour one-use trial + manual license purchase workflow.

Trial starts only when first eligible DEMO broker account is broker-confirmed.
A pending MT5 registration or cTrader OAuth request never starts the clock.
No payment provider, automatic charging, broker authorization or live execution.
"""
import datetime as dt
import secrets
import time
import apex_pricing
import apex_crm_subscriptions as subscriptions

SECONDS=86400
PLANS=("Starter","Professional","Enterprise")
def iso(epoch):
    return dt.datetime.fromtimestamp(epoch,dt.timezone.utc).replace(microsecond=0).isoformat()
def superadmin(c,account_id):
    # Never infer owner from broker number or from an unauthenticated request.
    table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='apex_admin_roles'").fetchone()
    return bool(table and c.execute(
        "SELECT 1 FROM apex_admin_roles WHERE account_id=? AND role='SUPERADMIN'",(account_id,)).fetchone())
def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS apex_trial_entitlements(
        account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        started_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
        CHECK(expires_at=started_at+86400))""")
    c.execute("""CREATE TABLE IF NOT EXISTS apex_trial_seats(
        account_id TEXT PRIMARY KEY REFERENCES apex_trial_entitlements(account_id) ON DELETE CASCADE,
        broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
        platform TEXT NOT NULL CHECK(platform IN ('MT5','cTrader')),
        environment TEXT NOT NULL CHECK(environment='DEMO'),
        account_reference TEXT NOT NULL,broker_server TEXT NOT NULL,
        allocated_at INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS apex_license_purchase_requests(
        id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        requested_plan TEXT NOT NULL CHECK(requested_plan IN ('Starter','Professional','Enterprise')),
        requested_seats INTEGER NOT NULL CHECK(requested_seats BETWEEN 1 AND 500),
        client_note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL CHECK(status IN ('requested','contacted','activated','cancelled')),
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        activation_at TEXT,activated_by TEXT,external_payment_reference TEXT,
        quoted_amount_minor INTEGER,quoted_currency TEXT,quoted_interval TEXT)""")
    fields={col[1] for col in c.execute("PRAGMA table_info(apex_license_purchase_requests)")}
    for column,kind in (("quoted_amount_minor","INTEGER"),("quoted_currency","TEXT"),("quoted_interval","TEXT")):
        if column not in fields:
            c.execute("ALTER TABLE apex_license_purchase_requests ADD COLUMN "+column+" "+kind)
    c.execute("CREATE INDEX IF NOT EXISTS apex_purchase_requests_by_account ON apex_license_purchase_requests(account_id,created_at)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS apex_one_open_license_request ON apex_license_purchase_requests(account_id) WHERE status IN ('requested','contacted')")
    # Defense in depth: even a broker worker marking the owner account CONNECTED
    # cannot issue free trials or consume customer-license seats.
    # CRM init calls this after admin role schema exists, including at boot.
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='apex_admin_roles'").fetchone():
        c.execute("""CREATE TRIGGER IF NOT EXISTS apex_trial_owner_exclusion
          BEFORE INSERT ON apex_trial_entitlements
          WHEN EXISTS (SELECT 1 FROM apex_admin_roles
                       WHERE account_id=NEW.account_id AND role='SUPERADMIN')
          BEGIN SELECT RAISE(IGNORE); END""")
        c.execute("""CREATE TRIGGER IF NOT EXISTS apex_trial_owner_seat_exclusion
          BEFORE INSERT ON apex_trial_seats
          WHEN EXISTS (SELECT 1 FROM apex_admin_roles
                       WHERE account_id=NEW.account_id AND role='SUPERADMIN')
          BEGIN SELECT RAISE(IGNORE); END""")
    # On fresh signup DBs, apex_mt5_connections may not yet exist; when the
    # client service initializes, it creates the table and attaches triggers.
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='apex_mt5_connections'").fetchone():
        for event,clause in (
           ("insert","AFTER INSERT ON apex_mt5_connections"),
           ("update","AFTER UPDATE OF status,broker_verified_at,worker_binding ON apex_mt5_connections"),
        ):
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS apex_trial_mt5_verified_{event}
              {clause}
              WHEN NEW.status='CONNECTED' AND NEW.environment='DEMO'
                 AND NEW.broker_verified_at IS NOT NULL
                 AND length(trim(COALESCE(NEW.worker_binding,'')))>0
                 AND EXISTS (
                   SELECT 1 FROM accounts a JOIN account_email_verification v
                   ON v.account_id=a.id WHERE a.id=NEW.account_id AND a.status='approved')
              BEGIN
                INSERT OR IGNORE INTO apex_trial_entitlements(account_id,started_at,expires_at)
                SELECT NEW.account_id,CAST(strftime('%s','now') AS INTEGER),
                       CAST(strftime('%s','now') AS INTEGER)+86400
                WHERE NOT EXISTS (
                  SELECT 1 FROM apex_crm_licenses WHERE account_id=NEW.account_id);
                INSERT OR IGNORE INTO apex_trial_seats(
                  account_id,broker,platform,environment,account_reference,broker_server,allocated_at)
                SELECT NEW.account_id,NEW.broker,'MT5',NEW.environment,
                       NEW.account_reference,NEW.broker_server,CAST(strftime('%s','now') AS INTEGER)
                FROM apex_trial_entitlements t WHERE t.account_id=NEW.account_id
                  AND t.expires_at>CAST(strftime('%s','now') AS INTEGER)
                  AND NOT EXISTS (
                   SELECT 1 FROM apex_crm_licenses WHERE account_id=NEW.account_id);
              END""")

def trial(c,aid,now=None):
    if superadmin(c,aid):
        return {"status":"owner_exempt","started_at":None,"expires_at":None,
                "seconds_remaining":0,"buy_license_required":False,"one_time_trial":False,
                "owner_operator_account":True}
    now=int(time.time()) if now is None else int(now)
    rec=c.execute("SELECT started_at,expires_at FROM apex_trial_entitlements WHERE account_id=?",(aid,)).fetchone()
    if not rec:
        return {"status":"not_started","started_at":None,"expires_at":None,"seconds_remaining":0,
                "buy_license_required":False,"one_time_trial":True}
    seat=c.execute("SELECT broker,platform,environment,account_reference,broker_server FROM apex_trial_seats WHERE account_id=?",(aid,)).fetchone()
    active=now<rec[1]
    return {"status":"active" if active else "expired","started_at":iso(rec[0]),
            "expires_at":iso(rec[1]),"seconds_remaining":max(0,rec[1]-now),
            "buy_license_required":not active,"one_time_trial":True,
            "trial_broker_account":None if not seat else {"broker":seat[0],"platform":seat[1],
              "environment":seat[2],"account_reference_masked":"••••"+seat[3][-4:],
              "broker_server":seat[4]}}
def matching_seat(c,aid,broker,platform,env,ref,server,now=None):
    t=trial(c,aid,now)
    if t["status"]!="active" or env!="DEMO":return False
    row=c.execute("""SELECT 1 FROM apex_trial_seats WHERE account_id=? AND broker=? AND platform=?
                      AND environment=? AND account_reference=? AND broker_server=?""",
                  (aid,broker,platform,env,ref,server)).fetchone()
    return bool(row)
def requests(c,aid=None):
    q="""SELECT p.id,p.account_id,a.full_name,a.email,p.requested_plan,p.requested_seats,
          p.client_note,p.status,p.created_at,p.updated_at,p.activation_at,
          p.quoted_amount_minor,p.quoted_currency,p.quoted_interval
          FROM apex_license_purchase_requests p JOIN accounts a ON a.id=p.account_id"""
    parms=(aid,) if aid else ()
    if aid:q+=" WHERE p.account_id=?"
    q+=" ORDER BY p.created_at DESC LIMIT 200"
    cur=c.execute(q,parms);cols=[x[0] for x in cur.description]
    return [dict(zip(cols,x)) for x in cur.fetchall()]
def create_request(c,aid,payload,now=None):
    plan=payload.get("plan")
    note=payload.get("note","")
    if plan not in PLANS:raise ValueError("Select a license plan.")
    price=apex_pricing.quote(plan)
    seats=price["included_broker_accounts"]
    if "seats" in payload and (type(payload["seats"]) is not int or payload["seats"]!=seats):
        raise ValueError("This plan includes exactly "+str(seats)+" broker account(s). Extra seats are not available.") 
    if payload.get("acknowledge_broker_deposit") is not True:
        raise ValueError("Confirm that your license fee does not include trading equity and broker deposits are separate.")
    if not isinstance(note,str) or len(note)>500:raise ValueError("Note must be at most 500 characters.")
    state=c.execute("SELECT status FROM accounts WHERE id=?",(aid,)).fetchone()
    if not state or state[0]!="approved" or not c.execute(
      "SELECT 1 FROM account_email_verification WHERE account_id=?",(aid,)).fetchone():
        raise ValueError("Verify your email before requesting a license.")
    if superadmin(c,aid):
        raise ValueError("Superadmin operator account is not a customer subscription.")
    # Do not automatically issue a second, paid entitlement or invoice.
    open_req=c.execute("""SELECT 1 FROM apex_license_purchase_requests WHERE account_id=?
           AND status IN ('requested','contacted')""",(aid,)).fetchone()
    if open_req:raise ValueError("A license request is already open. Contact ABUTRON support.")
    rid=secrets.token_hex(16)
    now=iso(int(time.time()) if now is None else int(now))
    c.execute("""INSERT INTO apex_license_purchase_requests
              (id,account_id,requested_plan,requested_seats,client_note,status,created_at,updated_at,
               quoted_amount_minor,quoted_currency,quoted_interval)
              VALUES(?,?,?,?,?,'requested',?,?,?,?,?)""",
              (rid,aid,plan,seats,note.strip(),now,now,
               price["amount_minor"],price["currency"],price["billing_interval"]))
    return {"request_id":rid,"status":"requested","price_quote":price,"payment_collection_enabled":False,
            "license_automatically_issued":False,
            "message":"Request received for "+plan+" with "+str(seats)+" included broker-account seat(s). "
                      "License fees do NOT include trading capital or account equity. "
                      "For LIVE trading, fund your broker account directly with an approved broker. "
                      "License activation follows separately confirmed payment."}
def admin_change(c,actor,payload,audit):
    rid=payload.get("request_id")
    action=payload.get("action")
    if not isinstance(rid,str) or len(rid)!=32 or any(ch not in "0123456789abcdef" for ch in rid):
        raise ValueError("Invalid request ID.")
    if action not in ("contacted","cancel","activate"):raise ValueError("Invalid request action.")
    row=c.execute("""SELECT account_id,requested_plan,requested_seats,status
         FROM apex_license_purchase_requests WHERE id=?""",(rid,)).fetchone()
    if not row:raise ValueError("License request not found.")
    aid,plan,seats,old=row
    expected_seats=apex_pricing.quote(plan)["included_broker_accounts"]
    if seats!=expected_seats:raise ValueError("Request seat allowance does not match the official plan. Cancel and re-request.")
    if old not in ("requested","contacted"):raise ValueError("This request is already closed.")
    now=iso(int(time.time()))
    if action=="contacted":
        c.execute("UPDATE apex_license_purchase_requests SET status='contacted',updated_at=? WHERE id=?",(now,rid))
        audit(c,actor,aid,"LICENSE_REQUEST_CONTACTED",plan)
        return {"status":"contacted","license_active":False}
    if action=="cancel":
        c.execute("UPDATE apex_license_purchase_requests SET status='cancelled',updated_at=? WHERE id=?",(now,rid))
        audit(c,actor,aid,"LICENSE_REQUEST_CANCELLED",plan)
        return {"status":"cancelled","license_active":False}
    # Payment is performed outside APEX. Enforce explicit administrative attestation.
    if payload.get("external_payment_confirmed") is not True:
        raise ValueError("Confirm external payment was received before activating a paid license.")
    ref=payload.get("external_payment_reference","")
    if not isinstance(ref,str) or not 3<=len(ref.strip())<=100:
        raise ValueError("Enter a valid external payment reference.")
    expiry=payload.get("expires_on")
    if not isinstance(expiry,str) or len(expiry)!=10:
        raise ValueError("Paid license expiry date required (YYYY-MM-DD).")
    try:expiration=dt.date.fromisoformat(expiry)
    except ValueError:raise ValueError("Invalid paid license expiry date.")
    if expiration<=dt.datetime.now(dt.timezone.utc).date():
        raise ValueError("Paid license expiry must be in the future.")
    status=c.execute("SELECT status FROM accounts WHERE id=?",(aid,)).fetchone()
    if not status or status[0]!="approved":raise ValueError("Customer access is not active.")
    # Existing license must not be overwritten without explicit account management.
    existing=c.execute("SELECT 1 FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone()
    if existing:raise ValueError("Customer already has a license. Edit it in CRM instead of overwriting.")
    code="APX-"+secrets.token_hex(12).upper()
    c.execute("""INSERT INTO apex_crm_licenses
          (account_id,license_code,plan,status,seats,expires_on,internal_notes,created_at,updated_at)
          VALUES(?,?,?,'active',?,?,?, ?,?)""",
          (aid,code,plan,seats,expiry,"External payment attested by Superadmin; reference recorded in purchase request.",now,now))
    # Carry over the customer's original trial broker account (one seat only) where
    # it still belongs to them. Does not imply broker authentication or trading ON.
    trial_seat=c.execute("""SELECT broker,platform,environment,account_reference,broker_server
       FROM apex_trial_seats WHERE account_id=?""",(aid,)).fetchone()
    if trial_seat and seats>=1:
        broker,platform,env,ref,server=trial_seat
        registered=c.execute("""SELECT 1 FROM broker_link_requests WHERE account_id=? AND broker=?
          AND platform=? AND environment=? AND account_reference=? AND broker_server=?""",
          (aid,broker,platform,env,ref,server)).fetchone()
        if not registered and platform=="MT5":
            registered=c.execute("""SELECT 1 FROM apex_mt5_connections WHERE account_id=? AND broker=?
              AND environment=? AND account_reference=? AND broker_server=? AND status!='DISCONNECTED'""",
              (aid,broker,env,ref,server)).fetchone()
        if registered:
            c.execute("""INSERT OR IGNORE INTO apex_crm_account_licenses
               (account_id,broker,platform,environment,account_reference,broker_server,state,expires_on,created_at,updated_at)
               VALUES(?,?,?,?,?,?,'assigned',?,?,?)""",
               (aid,broker,platform,env,ref,server,expiry,now,now))
    # Once Superadmin has attested external receipt, also create the matching
    # CRM monthly subscription record in the same DB transaction (no charging).
    old_subscription=subscriptions.current(c,aid)
    price=apex_pricing.quote(plan)
    c.execute("""INSERT INTO apex_crm_subscriptions
       (account_id,plan,currency,amount_minor,billing_interval,status,renewal_on,updated_at)
       VALUES(?,?,?,?,?,'active',?,?)
       ON CONFLICT(account_id) DO UPDATE SET
       plan=excluded.plan,currency=excluded.currency,amount_minor=excluded.amount_minor,
       billing_interval=excluded.billing_interval,status=excluded.status,
       renewal_on=excluded.renewal_on,updated_at=excluded.updated_at""",
       (aid,plan,price["currency"],price["amount_minor"],price["billing_interval"],expiry,now))
    subscriptions.save_event(c,aid,actor,"MANUAL_PAYMENT_ATTESTED",
                              old_subscription,subscriptions.current(c,aid),
                              "Outside-APEX payment confirmed by Superadmin; request "+rid[-8:])
    audit(c,actor,aid,"PAID_SUBSCRIPTION_CREATED_OR_UPDATED",plan+" "+price["currency"])
    c.execute("""UPDATE apex_license_purchase_requests SET status='activated',updated_at=?,
                  activation_at=?,activated_by=?,external_payment_reference=? WHERE id=?""",
              (now,now,actor,ref.strip(),rid))
    audit(c,actor,aid,"LICENSE_PAYMENT_CONFIRMED_AND_ACTIVATED",plan+" / request "+rid[-8:])
    return {"status":"activated","license_code":code,"license_active":True,"subscription_recorded":True,
            "price_quote":apex_pricing.quote(plan),"payment_attested_by_admin":True,
            "payment_processor_connected":False,"broker_trading_enabled":False}
