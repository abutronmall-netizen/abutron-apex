"""APEX CRM: administrative business records, no broker execution or credential storage.
All routes are behind existing password + 8-digit email MFA Superadmin session.
"""
import datetime as dt
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit, parse_qs
import apex_crm_account_licenses as account_licenses
import apex_crm_subscriptions as subscriptions
import apex_crm_license_policy as license_policy
import apex_trial
import apex_pricing

db_connect=None
BROKERS=(("Deriv","MT5"),("IC Markets","MT5"),("IC Markets","cTrader"),
         ("FP Markets","MT5"),("FP Markets","cTrader"))
ISO_DATE=re.compile(r"^\d{4}-\d{2}-\d{2}$")
IDENT=re.compile(r"^[a-zA-Z0-9-]{8,80}$")
BASE="/account/api/client/admin/crm/"

def utc(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def configure(connect): 
    global db_connect
    db_connect=connect
def init():
    if db_connect is None: raise RuntimeError("CRM database not configured")
    with db_connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_profiles(
         account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
         segment TEXT NOT NULL DEFAULT 'standard' CHECK(segment IN ('standard','vip','business')),
         tags TEXT NOT NULL DEFAULT '', internal_notes TEXT NOT NULL DEFAULT '',
         previously_active INTEGER NOT NULL DEFAULT 0 CHECK(previously_active IN (0,1)),
         updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_licenses(
         account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
         license_code TEXT NOT NULL UNIQUE, plan TEXT NOT NULL CHECK(plan IN ('Starter','Professional','Enterprise')),
         status TEXT NOT NULL CHECK(status IN ('active','paused','expired')),
         seats INTEGER NOT NULL DEFAULT 1 CHECK(seats BETWEEN 1 AND 500),
         expires_on TEXT, internal_notes TEXT NOT NULL DEFAULT '',
         created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_subscriptions(
         account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
         plan TEXT NOT NULL, currency TEXT NOT NULL CHECK(currency IN ('USD','ZAR','EUR','GBP')),
         amount_minor INTEGER NOT NULL CHECK(amount_minor BETWEEN 0 AND 100000000),
         billing_interval TEXT NOT NULL CHECK(billing_interval IN ('monthly','quarterly','annual','one_time')),
         status TEXT NOT NULL CHECK(status IN ('trial','active','paused','cancelled')),
         renewal_on TEXT, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_broker_catalog(
         broker TEXT NOT NULL, platform TEXT NOT NULL, accepting_requests INTEGER NOT NULL DEFAULT 1
         CHECK(accepting_requests IN (0,1)),
         notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
         PRIMARY KEY(broker,platform))""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_tickets(
         id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
         subject TEXT NOT NULL, priority TEXT NOT NULL CHECK(priority IN ('low','normal','high')),
         status TEXT NOT NULL CHECK(status IN ('open','in_progress','resolved')),
         internal_notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_audit(
         id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL, subject_id TEXT,
         action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', happened_at TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS apex_crm_tickets_status ON apex_crm_tickets(status,created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS apex_crm_audit_recent ON apex_crm_audit(happened_at)")
        account_licenses.init(c)
        subscriptions.init(c)
        license_policy.init(c)
        apex_trial.init(c)
        for broker,platform in BROKERS:
            c.execute("""INSERT OR IGNORE INTO apex_crm_broker_catalog
             (broker,platform,accepting_requests,notes,updated_at) VALUES(?,?,1,'',?)""",(broker,platform,utc()))

def accepting_requests(c,broker,platform):
    row=c.execute("SELECT accepting_requests FROM apex_crm_broker_catalog WHERE broker=? AND platform=?",
                  (broker,platform)).fetchone()
    return bool(row and row[0])

def string(x,name,maxlen=255,required=False):
    if not isinstance(x,str):raise ValueError(name+" must be text.")
    x=x.strip()
    if len(x)>maxlen or (required and not x):raise ValueError("Invalid "+name+".")
    return x
def enum(x,name,choices):
    if x not in choices:raise ValueError("Invalid "+name+".")
    return x
def date(x):
    if x is None or x=="":return None
    if not isinstance(x,str) or not ISO_DATE.fullmatch(x):raise ValueError("Date must be YYYY-MM-DD.")
    try:dt.date.fromisoformat(x)
    except ValueError:raise ValueError("Invalid calendar date.")
    return x
def ident(x):
    if not isinstance(x,str) or not IDENT.fullmatch(x):raise ValueError("Invalid record identifier.")
    return x
def audit(c,actor,subject,action,detail=""):
    c.execute("INSERT INTO apex_crm_audit(actor_id,subject_id,action,detail,happened_at) VALUES(?,?,?,?,?)",
              (actor,subject,action,detail[:255],utc()))
def exists(c,aid):
    if not c.execute("SELECT 1 FROM accounts WHERE id=?",(aid,)).fetchone():
        raise LookupError("Client not found.")
def rows(c,sql,params=()):
    cur=c.execute(sql,params)
    names=[d[0] for d in cur.description]
    return [dict(zip(names,r)) for r in cur.fetchall()]
def respond(handler,payload,code=200):return handler.reply(code,payload)
def client_license(aid):
    with db_connect() as c:
        row=c.execute("""SELECT plan,status,expires_on,seats FROM apex_crm_licenses WHERE account_id=?""",(aid,)).fetchone()
    if not row:
        with db_connect() as c:
            t=apex_trial.trial(c,aid)
            seat=c.execute("SELECT count(*) FROM apex_trial_seats WHERE account_id=?",(aid,)).fetchone()[0]
        return {"plan":"1-Day Trial" if t["status"]!="not_started" else None,
                "status":"trial_active" if t["status"]=="active" else ("trial_expired" if t["status"]=="expired" else "not_assigned"),
                "expires_at":t["expires_at"],"seconds_remaining":t["seconds_remaining"],
                "seats":1 if t["status"]!="not_started" else 0,"assigned_broker_accounts":seat,
                "buy_license_required":t["buy_license_required"],
                "enforced_by_trading_engine":False,"payment_provider_connected":False}
    plan,status,expires,seats=row
    with db_connect() as c:
        if license_policy.revoked(c,aid):status="revoked"
    if status=="active" and expires and expires<dt.date.today().isoformat():status="expired"
    with db_connect() as c:
        count=c.execute("""SELECT count(*) FROM apex_crm_account_licenses
           WHERE account_id=? AND state='assigned' AND (expires_on IS NULL OR expires_on>=date('now'))""",
           (aid,)).fetchone()[0]
    return {"plan":plan,"status":status,"expires_on":expires,"seats":seats,
            "assigned_broker_accounts":count,"enforced_by_trading_engine":False,
            "payment_provider_connected":False}

def client_subscription(aid):
    with db_connect() as c:
        return subscriptions.public(c,aid)

def get(handler,actor):
    url=urlsplit(handler.path); route=url.path.removeprefix(BASE)
    args=parse_qs(url.query,keep_blank_values=False)
    with db_connect() as c:
        if route=="summary":
            counts=dict(c.execute("SELECT status,count(*) FROM accounts GROUP BY status").fetchall())
            request_count=c.execute("SELECT count(*) FROM broker_link_requests").fetchone()[0]
            connections=c.execute("SELECT count(*) FROM apex_mt5_connections WHERE status='CONNECTED'").fetchone()[0]
            demo_connections=c.execute("""SELECT count(*) FROM apex_mt5_connections
                 WHERE status='CONNECTED' AND broker='Deriv' AND environment='DEMO'
                 AND worker_binding LIKE 'abutron-client-mt5-%'""").fetchone()[0]
            enabled_accounts=c.execute("""SELECT count(*) FROM apex_mt5_connections m
                 JOIN apex_trade_controls t ON t.connection_id=m.id
                 WHERE m.status='CONNECTED' AND t.effective_enabled=1""").fetchone()[0]
            licenses=c.execute("""SELECT count(*) FROM apex_crm_licenses l
               WHERE l.status='active' AND (l.expires_on IS NULL OR l.expires_on>=date('now'))
               AND NOT EXISTS (SELECT 1 FROM apex_crm_license_revocations r
                  WHERE r.account_id=l.account_id AND r.cleared_at IS NULL)""").fetchone()[0]
            subs=c.execute("SELECT count(*) FROM apex_crm_subscriptions WHERE status='active'").fetchone()[0]
            tickets=c.execute("SELECT count(*) FROM apex_crm_tickets WHERE status!='resolved'").fetchone()[0]
            activities=rows(c,"SELECT action,detail,happened_at FROM apex_crm_audit ORDER BY id DESC LIMIT 12")
            return respond(handler,{"client_count":sum(counts.values()),"client_states":counts,
              "broker_requests":request_count,"connected_accounts":connections,
              "connected_deriv_demo_accounts":demo_connections,
              "automatic_trading_enabled_accounts":enabled_accounts,
              "broker_status_source":"Connected records maintained by authenticated MT5 worker manager",
              "active_license_records":licenses,
              "active_subscription_records":subs,"open_tickets":tickets,"recent_activity":activities,
              "trading_engine_connected":False,"payments_gateway_connected":False,
              "active_trials":c.execute("SELECT count(*) FROM apex_trial_entitlements WHERE expires_at>?",(int(time.time()),)).fetchone()[0],
              "expired_trials":c.execute("SELECT count(*) FROM apex_trial_entitlements WHERE expires_at<=?",(int(time.time()),)).fetchone()[0],
              "purchase_requests_pending":c.execute("SELECT count(*) FROM apex_license_purchase_requests WHERE status IN ('requested','contacted')").fetchone()[0],
              "assigned_broker_account_licenses":c.execute(
                "SELECT count(*) FROM apex_crm_account_licenses WHERE state='assigned'").fetchone()[0],
              **subscriptions.indicators(c)})
        if route=="clients":
            q=(args.get("q",[""])[0] or "").strip()[:100]
            status=args.get("status",["all"])[0]
            if status not in ("all","approved","pending_review","disabled","rejected"):
                raise ValueError("Unknown client filter.")
            where=[]; params=[]
            if q:
                where.append("(a.full_name LIKE ? OR a.email LIKE ?)")
                params.extend(["%"+q+"%","%"+q+"%"])
            if status!="all":
                where.append("a.status=?");params.append(status)
            predicate=("WHERE "+" AND ".join(where)) if where else ""
            query="""SELECT a.id,a.full_name,a.email,a.country,a.status,a.created_at,
                     COALESCE(p.segment,'standard') AS segment,
                     l.plan AS license_plan,l.status AS license_status,
                     s.status AS subscription_status,
                     (SELECT count(*) FROM broker_link_requests b WHERE b.account_id=a.id) AS broker_requests
                     FROM accounts a LEFT JOIN apex_crm_profiles p ON p.account_id=a.id
                     LEFT JOIN apex_crm_licenses l ON l.account_id=a.id
                     LEFT JOIN apex_crm_subscriptions s ON s.account_id=a.id """
            results=rows(c,query+predicate+" ORDER BY a.created_at DESC LIMIT 200",params)
            return respond(handler,{"clients":results,"limit":200})
        if route=="client":
            aid=ident(args.get("id",[""])[0])
            record=rows(c,"""SELECT id,full_name,email,country,status,created_at
                  FROM accounts WHERE id=?""",(aid,))
            if not record:return handler.reply(404,{"error":"Client not found."})
            profile=rows(c,"SELECT segment,tags,internal_notes,previously_active,updated_at FROM apex_crm_profiles WHERE account_id=?",(aid,))
            license_=rows(c,"SELECT license_code,plan,status,seats,expires_on,internal_notes,created_at,updated_at FROM apex_crm_licenses WHERE account_id=?",(aid,))
            subscription=rows(c,"SELECT plan,currency,amount_minor,billing_interval,status,renewal_on,updated_at FROM apex_crm_subscriptions WHERE account_id=?",(aid,))
            requests=rows(c,"""SELECT id,broker,platform,environment,account_reference,broker_server,status,created_at
                             FROM broker_link_requests WHERE account_id=? ORDER BY created_at DESC""",(aid,))
            connections=rows(c,"""SELECT x.id,x.broker,x.environment,x.account_reference,x.broker_server,x.status,
                                 COALESCE(t.desired_enabled,0) desired_enabled,
                                 COALESCE(t.effective_enabled,0) effective_enabled
                                 FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
                                 WHERE x.account_id=?""",(aid,))
            tickets=rows(c,"SELECT id,subject,priority,status,created_at FROM apex_crm_tickets WHERE account_id=? ORDER BY created_at DESC",(aid,))
            return respond(handler,{"client":record[0],"profile":profile[0] if profile else None,
                "license":license_[0] if license_ else None,
                "subscription":subscription[0] if subscription else None,
                "broker_requests":requests,"broker_connections":connections,"tickets":tickets,
                "account_licenses":account_licenses.list_for(c,aid),
                "license_policy":license_policy.list_client(c,aid),
                "subscription_history":subscriptions.history(c,aid),
                "pricing":apex_pricing.catalog(),
                "trial":apex_trial.trial(c,aid),
                "purchase_requests":apex_trial.requests(c,aid)})
        if route=="brokers":
            catalog=rows(c,"""SELECT bc.broker,bc.platform,bc.accepting_requests,bc.notes,bc.updated_at,
               (SELECT count(*) FROM broker_link_requests r WHERE r.broker=bc.broker AND r.platform=bc.platform) request_count
               FROM apex_crm_broker_catalog bc ORDER BY bc.broker,bc.platform""")
            pending=rows(c,"""SELECT r.id,r.account_id,a.full_name,a.email,r.broker,r.platform,r.environment,
                           r.account_reference,r.broker_server,r.status,r.created_at
                           FROM broker_link_requests r JOIN accounts a ON a.id=r.account_id
                           ORDER BY r.created_at DESC LIMIT 150""")
            connected=rows(c,"""SELECT x.id,x.account_id,a.email,x.broker,'MT5' platform,x.environment,
             x.account_reference,x.broker_server,x.status,COALESCE(t.effective_enabled,0) AS trading_enabled
             FROM apex_mt5_connections x JOIN accounts a ON a.id=x.account_id
             LEFT JOIN apex_trade_controls t ON t.connection_id=x.id ORDER BY x.updated_at DESC LIMIT 150""")
            return respond(handler,{"catalog":catalog,"requests":pending,"connections":connected})
        if route=="pricing":
            return respond(handler,{"plans":apex_pricing.catalog(),"payment_provider_connected":False})
        if route=="purchase-requests":
            return respond(handler,{"requests":apex_trial.requests(c),
                                    "payment_provider_connected":False})
        if route=="account-licenses":
            aid=ident(args.get("id",[""])[0]) if args.get("id") else None
            return respond(handler,{"account_licenses":account_licenses.list_for(c,aid),
                                    "payment_provider_connected":False,
                                    "trading_engine_enforced":False})
        if route=="licenses":
            return respond(handler,{"account_licenses":account_licenses.list_for(c),
                                     "revocations":rows(c,"SELECT account_id,revoked_at,reason FROM apex_crm_license_revocations WHERE cleared_at IS NULL"),
                                     "licenses":rows(c,"""SELECT l.account_id,a.full_name,a.email,l.license_code,l.plan,l.status,
             l.seats,l.expires_on,l.updated_at FROM apex_crm_licenses l JOIN accounts a ON a.id=l.account_id
             ORDER BY l.updated_at DESC LIMIT 200"""),"enforced_by_trading_engine":False})
        if route=="subscriptions":
            subs=rows(c,"""SELECT s.account_id,a.full_name,a.email,
             s.plan,s.currency,s.amount_minor,s.billing_interval,s.status,s.renewal_on,s.updated_at
             FROM apex_crm_subscriptions s JOIN accounts a ON a.id=s.account_id ORDER BY s.updated_at DESC LIMIT 200""")
            for rec in subs:
                rec["renewal_state"]=subscriptions.due_state(rec["status"],rec["renewal_on"])
            return respond(handler,{"subscriptions":subs,
               "pricing":apex_pricing.catalog(),
               "renewal_indicators":subscriptions.indicators(c),
               "recent_changes":subscriptions.history(c)[:25],
               "payment_collection_connected":False})
        if route=="subscription-history":
            aid=ident(args["id"][0]) if args.get("id") else None
            return respond(handler,{"history":subscriptions.history(c,aid),
                                    "payment_collection_connected":False})
        if route=="tickets":
            return respond(handler,{"tickets":rows(c,"""SELECT t.id,t.account_id,a.full_name,a.email,t.subject,t.priority,
            t.status,t.internal_notes,t.created_at,t.updated_at FROM apex_crm_tickets t
            JOIN accounts a ON a.id=t.account_id ORDER BY t.updated_at DESC LIMIT 200""")})
        if route=="activity":
            return respond(handler,{"activity":rows(c,"""SELECT a.action,a.detail,a.happened_at,
            COALESCE(c.email,a.subject_id,'System') subject FROM apex_crm_audit a
            LEFT JOIN accounts c ON c.id=a.subject_id ORDER BY a.id DESC LIMIT 200""")})
    return handler.reply(404,{"error":"Unknown CRM route."})

def post(handler,actor,payload):
    route=urlsplit(handler.path).path.removeprefix(BASE)
    if not isinstance(payload,dict):raise ValueError("Invalid data.")
    aid=payload.get("account_id")
    with db_connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if route=="client/update":
            aid=ident(aid);exists(c,aid)
            name=payload.get("full_name")
            if name is not None:
                name=string(name,"client name",120,True)
                c.execute("UPDATE accounts SET full_name=? WHERE id=?",(name,aid))
            if "segment" in payload or "tags" in payload or "internal_notes" in payload:
                old=c.execute("SELECT segment,tags,internal_notes,previously_active FROM apex_crm_profiles WHERE account_id=?",(aid,)).fetchone() or ("standard","","",0)
                segment=enum(payload.get("segment",old[0]),"segment",("standard","vip","business"))
                tags=string(payload.get("tags",old[1]),"tags",240)
                notes=string(payload.get("internal_notes",old[2]),"internal notes",4000)
                c.execute("""INSERT INTO apex_crm_profiles(account_id,segment,tags,internal_notes,previously_active,updated_at)
                 VALUES(?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET
                 segment=excluded.segment,tags=excluded.tags,internal_notes=excluded.internal_notes,updated_at=excluded.updated_at""",
                 (aid,segment,tags,notes,old[3],utc()))
            if "account_action" in payload:
                action=enum(payload["account_action"],"account action",("suspend","reactivate"))
                if aid==actor:raise ValueError("Cannot suspend or reactivate your own Superadmin identity.")
                current=c.execute("SELECT status FROM accounts WHERE id=?",(aid,)).fetchone()[0]
                if action=="suspend":
                    if current!="approved":raise ValueError("Only active clients can be suspended.")
                    c.execute("UPDATE accounts SET status='disabled' WHERE id=?",(aid,))
                    c.execute("""INSERT INTO apex_crm_profiles(account_id,previously_active,updated_at)
                     VALUES(?,1,?) ON CONFLICT(account_id) DO UPDATE SET previously_active=1,updated_at=excluded.updated_at""",(aid,utc()))
                    c.execute("DELETE FROM client_sessions WHERE account_id=?",(aid,))
                    c.execute("DELETE FROM apex_admin_sessions WHERE account_id=?",(aid,))
                else:
                    old=c.execute("SELECT previously_active FROM apex_crm_profiles WHERE account_id=?",(aid,)).fetchone()
                    if current!="disabled" or not old or old[0]!=1:
                        raise ValueError("Only previously active, CRM-suspended clients can be reactivated.")
                    c.execute("UPDATE accounts SET status='approved' WHERE id=?",(aid,))
                    c.execute("UPDATE apex_crm_profiles SET previously_active=0,updated_at=? WHERE account_id=?",(utc(),aid))
                audit(c,actor,aid,"CLIENT_"+action.upper())
            else:audit(c,actor,aid,"CLIENT_PROFILE_UPDATED")
            c.execute("COMMIT")
            return respond(handler,{"saved":True,"account_id":aid})
        if route=="license/save":
            aid=ident(aid);exists(c,aid)
            plan=enum(payload.get("plan"),"license plan",("Starter","Professional","Enterprise"))
            status=enum(payload.get("status"),"license status",("active","paused","expired"))
            seats=apex_pricing.quote(plan)["included_broker_accounts"]
            if "seats" in payload and (type(payload["seats"]) is not int or payload["seats"]!=seats):
                raise ValueError("The "+plan+" plan includes exactly "+str(seats)+" broker-account seat(s).")
            expires=date(payload.get("expires_on"))
            notes=string(payload.get("internal_notes",""),"internal notes",1000)
            # Do not silently under-allocate already assigned broker seats.
            assigned=c.execute("""SELECT count(*) FROM apex_crm_account_licenses WHERE account_id=?
                AND state='assigned' AND (expires_on IS NULL OR expires_on>=date('now'))""",(aid,)).fetchone()[0]
            if seats<assigned:raise ValueError("The license has more assigned broker accounts than this seat limit.")
            old=c.execute("SELECT license_code,created_at FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone()
            code,created=(old if old else ("APX-"+secrets.token_hex(12).upper(),utc()))
            c.execute("""INSERT INTO apex_crm_licenses(account_id,license_code,plan,status,seats,expires_on,internal_notes,created_at,updated_at)
             VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET plan=excluded.plan,status=excluded.status,
             seats=excluded.seats,expires_on=excluded.expires_on,internal_notes=excluded.internal_notes,updated_at=excluded.updated_at""",
             (aid,code,plan,status,seats,expires,notes,created,utc()))
            audit(c,actor,aid,"LICENSE_SAVED",plan+" "+status);c.execute("COMMIT")
            return respond(handler,{"saved":True,"license_code":code,"enforced_by_trading_engine":False})
        if route=="purchase-request/manage":
            result=apex_trial.admin_change(c,actor,payload,audit)
            c.execute("COMMIT")
            return respond(handler,result)
        if route=="license/revocation":
            result=license_policy.action(c,actor,payload,audit)
            c.execute("COMMIT")
            return respond(handler,result)
        if route=="account-license/save":
            result=account_licenses.apply(c,actor,payload,audit)
            c.execute("COMMIT")
            return respond(handler,result)
        if route=="subscription/save":
            aid=ident(aid);exists(c,aid)
            previous=subscriptions.current(c,aid)
            plan=enum(payload.get("plan"),"subscription plan",tuple(apex_pricing.PRICES))
            offer=apex_pricing.quote(plan)
            currency=offer["currency"];amount=offer["amount_minor"];interval=offer["billing_interval"]
            for key,expected in (("currency",currency),("amount_minor",amount),("billing_interval",interval)):
                if key in payload and (type(payload[key])!=type(expected) or payload[key]!=expected):
                    raise ValueError("Subscription price must match the official monthly ZAR plan price.")
            status=enum(payload.get("status"),"subscription status",("trial","active","paused","cancelled"))
            renewal=date(payload.get("renewal_on"))
            if interval=="one_time" and renewal:raise ValueError("One-time subscriptions do not renew.")
            c.execute("""INSERT INTO apex_crm_subscriptions(account_id,plan,currency,amount_minor,billing_interval,status,renewal_on,updated_at)
             VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET plan=excluded.plan,currency=excluded.currency,
             amount_minor=excluded.amount_minor,billing_interval=excluded.billing_interval,status=excluded.status,
             renewal_on=excluded.renewal_on,updated_at=excluded.updated_at""",
             (aid,plan,currency,amount,interval,status,renewal,utc()))
            subscriptions.save_event(c,aid,actor,"UPDATED" if previous else "CREATED",
                previous,subscriptions.current(c,aid))
            audit(c,actor,aid,"SUBSCRIPTION_SAVED",plan+" "+status);c.execute("COMMIT")
            return respond(handler,{"saved":True,"payment_collection_connected":False})
        if route=="subscription/renew":
            aid=ident(aid);exists(c,aid)
            result=subscriptions.renew(c,actor,aid,payload.get("renewal_on"),
                payload.get("expected_renewal_on"),payload.get("reason",""),audit)
            c.execute("COMMIT")
            return respond(handler,result)
        if route=="broker/catalog/update":
            broker=payload.get("broker");platform=payload.get("platform")
            if (broker,platform) not in BROKERS:raise ValueError("Unsupported broker or platform.")
            accepting=payload.get("accepting_requests")
            if type(accepting) is not bool:raise ValueError("Accepting requests must be true or false.")
            notes=string(payload.get("notes",""),"broker notes",800)
            c.execute("""UPDATE apex_crm_broker_catalog SET accepting_requests=?,notes=?,updated_at=?
                         WHERE broker=? AND platform=?""",(int(accepting),notes,utc(),broker,platform))
            audit(c,actor,None,"BROKER_INTAKE_UPDATED",broker+"/"+platform+" "+("open" if accepting else "closed"))
            c.execute("COMMIT")
            return respond(handler,{"saved":True,"execution_affected":False})
        if route=="broker/request/remove":
            request_id=ident(payload.get("request_id"))
            old=c.execute("SELECT account_id,broker,platform FROM broker_link_requests WHERE id=?",(request_id,)).fetchone()
            if not old:raise LookupError("Broker request not found.")
            c.execute("DELETE FROM broker_link_requests WHERE id=?",(request_id,))
            audit(c,actor,old[0],"BROKER_REQUEST_REMOVED",old[1]+" "+old[2])
            c.execute("COMMIT")
            return respond(handler,{"removed":True,"execution_affected":False})
        if route=="ticket/create":
            aid=ident(aid);exists(c,aid)
            subject=string(payload.get("subject",""),"subject",150,True)
            priority=enum(payload.get("priority","normal"),"priority",("low","normal","high"))
            notes=string(payload.get("internal_notes",""),"internal notes",2000)
            tid=secrets.token_hex(16);when=utc()
            c.execute("""INSERT INTO apex_crm_tickets(id,account_id,subject,priority,status,internal_notes,created_at,updated_at)
            VALUES(?,?,?,?,'open',?,?,?)""",(tid,aid,subject,priority,notes,when,when))
            audit(c,actor,aid,"TICKET_CREATED",subject);c.execute("COMMIT")
            return respond(handler,{"created":True,"id":tid},201)
        if route=="ticket/update":
            tid=ident(payload.get("ticket_id"))
            status=enum(payload.get("status"),"ticket status",("open","in_progress","resolved"))
            notes=string(payload.get("internal_notes",""),"internal notes",2000)
            row=c.execute("SELECT account_id FROM apex_crm_tickets WHERE id=?",(tid,)).fetchone()
            if not row:raise LookupError("Ticket not found.")
            c.execute("UPDATE apex_crm_tickets SET status=?,internal_notes=?,updated_at=? WHERE id=?",
                      (status,notes,utc(),tid))
            audit(c,actor,row[0],"TICKET_UPDATED",status);c.execute("COMMIT")
            return respond(handler,{"saved":True})
        raise LookupError("Unknown CRM route.")
