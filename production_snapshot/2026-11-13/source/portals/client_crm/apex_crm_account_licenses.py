"""APEX CRM per-broker-account license allocations, business records only.

NO order execution, broker auth, billing provider, or live entitlement enforcement.
Natural-key allocation survives pending->connected change without granting execution.
"""
import datetime as dt
import sqlite3
import apex_crm_license_policy as policy

def stamp():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def today():
    return dt.date.today().isoformat()
def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_account_licenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
        platform TEXT NOT NULL CHECK(platform IN ('MT5','cTrader')),
        environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
        account_reference TEXT NOT NULL, broker_server TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('assigned','paused')),
        expires_on TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(account_id,broker,platform,environment,account_reference,broker_server)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS apex_crm_account_licenses_owner ON apex_crm_account_licenses(account_id,state)")
def list_for(c, account_id=None):
    where="WHERE e.account_id=?" if account_id else ""
    params=(account_id,) if account_id else ()
    query="""SELECT e.id,e.account_id,a.full_name,a.email,e.broker,e.platform,
        e.environment,e.account_reference,e.broker_server,e.state,e.expires_on,
        e.created_at,e.updated_at,
        l.plan customer_plan,l.status customer_license_state,l.expires_on customer_license_expiry,
        CASE WHEN EXISTS (
          SELECT 1 FROM apex_mt5_connections v WHERE v.account_id=e.account_id
            AND v.broker=e.broker AND e.platform='MT5' AND v.environment=e.environment
            AND v.account_reference=e.account_reference AND v.broker_server=e.broker_server
            AND v.status='CONNECTED') THEN 'CONNECTED'
         WHEN EXISTS (
          SELECT 1 FROM broker_link_requests r WHERE r.account_id=e.account_id
            AND r.broker=e.broker AND r.platform=e.platform AND r.environment=e.environment
            AND r.account_reference=e.account_reference AND r.broker_server=e.broker_server
         ) THEN 'PENDING' ELSE 'UNLINKED' END broker_connection_status
        FROM apex_crm_account_licenses e JOIN accounts a ON a.id=e.account_id
        LEFT JOIN apex_crm_licenses l ON l.account_id=e.account_id
    """+where+" ORDER BY e.updated_at DESC LIMIT 250"
    cur=c.execute(query,params);cols=[x[0] for x in cur.description]
    result=[dict(zip(cols,row)) for row in cur.fetchall()]
    for entry in result:
        master_ok=not policy.revoked(c,entry['account_id']) and entry["customer_license_state"]=="active" and (
            not entry["customer_license_expiry"] or entry["customer_license_expiry"]>=today())
        own_ok=entry["state"]=="assigned" and (
            not entry["expires_on"] or entry["expires_on"]>=today())
        entry["crm_entitlement_valid"]=bool(master_ok and own_ok)
        entry["trading_engine_enforced"]=False
        entry["broker_trading_enabled_by_crm"]=False
    return result

def apply(c,actor,payload, audit):
    aid=payload.get("account_id")
    if not isinstance(aid,str) or not (8<=len(aid)<=80):
        raise ValueError("Select a valid customer.")
    state=payload.get("state")
    if state not in ("assigned","paused"):
        raise ValueError("Choose Assigned or Paused.")
    expiry=payload.get("expires_on")
    if expiry in ("",None): expiry=None
    else:
        if not isinstance(expiry,str) or len(expiry)!=10:
            raise ValueError("Expiry date must use YYYY-MM-DD.")
        try: dt.date.fromisoformat(expiry)
        except ValueError: raise ValueError("Invalid expiry date.")
    target=payload.get("source_type")
    source_id=payload.get("source_id")
    if target not in ("request","connection") or not isinstance(source_id,str) or len(source_id)!=32 or any(c not in "0123456789abcdef" for c in source_id):
        raise ValueError("Select a registered broker account.")
    if target=="request":
        broker_row=c.execute("""SELECT broker,platform,environment,account_reference,broker_server
             FROM broker_link_requests WHERE id=? AND account_id=?""",(source_id,aid)).fetchone()
    else:
        broker_row=c.execute("""SELECT broker,'MT5',environment,account_reference,broker_server
             FROM apex_mt5_connections WHERE id=? AND account_id=?""",(source_id,aid)).fetchone()
    if broker_row is None:raise ValueError("Account is not registered to this customer.")
    if state=="assigned":
        if policy.revoked(c,aid):raise ValueError("Customer license has been revoked.")
        master=c.execute("SELECT status,seats,expires_on FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone()
        if not master or master[0]!="active" or (master[2] and master[2]<today()):
            raise ValueError("Assign an active, unexpired customer license before allocating broker seats.")
        b,p,e,r,s=broker_row
        used=c.execute("""SELECT count(*) FROM apex_crm_account_licenses
            WHERE account_id=? AND state='assigned' AND (expires_on IS NULL OR expires_on>=date('now'))
             AND NOT (broker=? AND platform=? AND environment=? AND account_reference=? AND broker_server=?)""",
            (aid,b,p,e,r,s)).fetchone()[0]
        if used>=master[1]:raise ValueError("Customer license seat limit reached.")
    when=stamp()
    c.execute("""INSERT INTO apex_crm_account_licenses(account_id,broker,platform,environment,
        account_reference,broker_server,state,expires_on,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(account_id,broker,platform,environment,account_reference,broker_server)
        DO UPDATE SET state=excluded.state,expires_on=excluded.expires_on,updated_at=excluded.updated_at""",
        (aid,*broker_row,state,expiry,when,when))
    audit(c,actor,aid,"ACCOUNT_LICENSE_UPDATED",broker_row[0]+"/"+broker_row[1]+"/"+broker_row[2]+" "+state)
    return {"saved":True,"state":state,"effective_trading_permission":False,
            "payment_provider_connected":False,"customer_license_seat_enforced_in_crm":True}

def pause_existing(c,actor,payload,audit):
    """Pause existing license allocation by database ID, even if the broker request was removed."""
    aid=payload.get("account_id")
    ident=payload.get("allocation_id")
    if not isinstance(aid,str) or not (8<=len(aid)<=80):
        raise ValueError("Select a valid client.")
    if type(ident) is not int or not 1<=ident<=2147483647:
        raise ValueError("Select a valid broker-account license allocation.")
    row=c.execute("""SELECT broker,platform,environment,state
        FROM apex_crm_account_licenses WHERE id=? AND account_id=?""",(ident,aid)).fetchone()
    if row is None:raise LookupError("Broker-account license allocation not found.")
    if row[3]=="paused":return {"saved":True,"state":"paused","unchanged":True,"trading_permissions_changed":False}
    c.execute("UPDATE apex_crm_account_licenses SET state='paused',updated_at=? WHERE id=? AND account_id=?",
              (stamp(),ident,aid))
    audit(c,actor,aid,"ACCOUNT_LICENSE_PAUSED",row[0]+"/"+row[1]+"/"+row[2])
    return {"saved":True,"state":"paused","trading_permissions_changed":False}
