"""APEX per-client MT5 trading controls.

Only trusted broker workers may provision confirmed connections. A client cannot
turn trading ON until an independently wired execution bridge confirms it.
This module never touches the existing APEX source trading engine.
"""
import re, sqlite3, time
import apex_crm_license_policy as license_policy

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS apex_mt5_connections(
       id TEXT PRIMARY KEY,
       account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
       broker TEXT NOT NULL CHECK(broker IN ('Deriv','IC Markets','FP Markets')),
       environment TEXT NOT NULL CHECK(environment IN ('DEMO','LIVE')),
       account_reference TEXT NOT NULL, broker_server TEXT NOT NULL,
       status TEXT NOT NULL CHECK(status IN ('CONNECTING','CONNECTED','DISCONNECTED','ERROR')),
       broker_verified_at INTEGER, worker_binding TEXT,
       created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
       UNIQUE(account_id,broker,environment,account_reference,broker_server)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS apex_mt5_connections_owner ON apex_mt5_connections(account_id,status)")
    # Separate intent record for real-money accounts. Not an order permission:
    # every existing live order caller still sees desired=0/effective=0.
    db.execute('''CREATE TABLE IF NOT EXISTS apex_live_trading_requests(
       connection_id TEXT PRIMARY KEY REFERENCES apex_mt5_connections(id) ON DELETE CASCADE,
       requested_enabled INTEGER NOT NULL CHECK(requested_enabled IN (0,1)),
       updated_at INTEGER NOT NULL,
       status TEXT NOT NULL
    )''')
    db.execute("""CREATE TABLE IF NOT EXISTS apex_trade_controls(
       connection_id TEXT PRIMARY KEY REFERENCES apex_mt5_connections(id) ON DELETE CASCADE,
       desired_enabled INTEGER NOT NULL DEFAULT 0 CHECK(desired_enabled IN (0,1)),
       effective_enabled INTEGER NOT NULL DEFAULT 0 CHECK(effective_enabled IN (0,1)),
       updated_at INTEGER NOT NULL,
       last_error TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS apex_trade_control_audit(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       account_id TEXT NOT NULL, connection_id TEXT NOT NULL,
       requested_enabled INTEGER NOT NULL CHECK(requested_enabled IN (0,1)),
       outcome TEXT NOT NULL, occurred_at INTEGER NOT NULL
    )""")

def list_controls(handler, connect, user_id):
    with connect() as db:
        linked=db.execute("""SELECT c.id,c.broker,c.environment,c.account_reference,
             c.broker_server,c.status,c.broker_verified_at,c.worker_binding,
             COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),
             COALESCE(l.requested_enabled,0)
             FROM apex_mt5_connections c LEFT JOIN apex_trade_controls t
             ON c.id=t.connection_id
             LEFT JOIN apex_live_trading_requests l ON l.connection_id=c.id
             WHERE c.account_id=? ORDER BY c.created_at DESC""",(user_id,)).fetchall()
        pending=db.execute("""SELECT id,broker,platform,environment,account_reference,broker_server,status
                              FROM broker_link_requests WHERE account_id=?
                              ORDER BY created_at DESC LIMIT 30""",(user_id,)).fetchall()
    records=[]
    for cid,broker,env,reference,server,state,verified,binding,desired,effective,live_intent in linked:
        ready=(state=="CONNECTED" and verified is not None and bool(binding))
        requested=bool(live_intent) if env=="LIVE" else bool(desired)
        is_live_pending=env=="LIVE" and requested and not effective
        records.append(dict(id=cid,broker=broker,platform="MT5",environment=env,
                            account_reference=reference,broker_server=server,connection_status=state,
                            trading_enabled=bool(effective),requested_enabled=requested,
                            crm_switch_effective=bool(effective),
                            broker_execution_verified=None,execution_status="NOT_ATTESTED_BY_CRM",
                            control_available=bool(ready),is_verified=bool(verified),
                            note=("LIVE ON requested. No real-money orders are enabled: a separate verified LIVE broker execution bridge and risk authorization are required." if is_live_pending else
                                  "Trading authorization requested. Orders remain OFF until the native V2 executor confirms account readiness and approved cutover." if desired and not effective else
                                  (f"{broker} {env} connected. CRM switch is ON for this account. A working APEX-to-broker order path, current broker receipts and SL/TP or trailing-stop execution are NOT confirmed by this switch." if effective else f"{broker} {env} connected. Automatic trading is OFF for this account.") if ready else
                                  "Connect and verify this MT5 account before requesting trading.")))
    for rid,broker,platform,env,reference,server,status in pending:
        records.append(dict(id=rid,broker=broker,platform=platform,environment=env,
                            account_reference=reference,broker_server=server,
                            connection_status="NOT_CONNECTED",trading_enabled=False,
                            requested_enabled=False,control_available=False,is_verified=False,
                            note="Broker connection pending. Trading is OFF."))
    return handler.reply(200,{"controls":records,"policy":"Independent per-account CRM control. ON is a request/activation state, NOT proof of a broker-executed order; verify current native receipts separately."})

def change_control(handler, connect, user_id, cid, payload):
    if set(payload)!={"enabled"} or type(payload.get("enabled")) is not bool:
        return handler.reply(422,{"error":"The enabled field must be true or false."})
    enabled=payload["enabled"]
    with connect() as db:
        row=db.execute("""SELECT c.status,c.broker,c.environment,c.broker_verified_at,c.worker_binding,
                     COALESCE(t.effective_enabled,0)
                     FROM apex_mt5_connections c LEFT JOIN apex_trade_controls t
                     ON c.id=t.connection_id WHERE c.id=? AND c.account_id=?""",(cid,user_id)).fetchone()
        if row is None:
            pending=db.execute("SELECT 1 FROM broker_link_requests WHERE id=? AND account_id=?",(cid,user_id)).fetchone()
            if pending:
                return handler.reply(409,{"error":"MT5 account is not connected; trading remains OFF."})
            return handler.reply(404,{"error":"Account connection not found."})
        state,broker,environment,verified,binding,effective=row
        now=int(time.time())
        if enabled:
            if broker not in ("Deriv","FP Markets") or environment not in ("DEMO","LIVE"):
                db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                           (user_id,cid,1,"DENIED_UNSUPPORTED_BROKER",now))
                return handler.reply(403,{"error":"No verified automated execution bridge is available for this broker."})
            if effective:
                return handler.reply(200,{"connection_id":cid,"trading_enabled":True,"requested_enabled":True,"status":"ON_ALREADY"})
            decision=license_policy.connection_decision(db,user_id,cid)
            if environment=="DEMO" and (decision is None or not decision["license_allows_new_entries"]):
                db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                           (user_id,cid,1,"DENIED_CUSTOMER_OR_BROKER_LICENSE",now))
                return handler.reply(403,{"error":"A valid customer license and assigned broker-account seat are required for new trades. Trading remains OFF.",
                                          "reason_codes":decision["reason_codes"] if decision else ["UNKNOWN_CONNECTION"],
                                          "protective_exit_rights_preserved":True})
            # The authenticated customer may request LIVE ON, but such intent
            # lives OUTSIDE apex_trade_controls: no old order-dispatcher may
            # interpret the request as executable permission. This status
            # never claims a real order or grants live trading authority.
            if environment=="LIVE":
                if state!="CONNECTED" or not verified or not binding:
                    db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                               (user_id,cid,1,"DENIED_LIVE_ACCOUNT_NOT_CONNECTED",now))
                    return handler.reply(409,{"error":"Authenticate this LIVE MT5 account before requesting trading."})
                db.execute('''INSERT INTO apex_live_trading_requests(connection_id,requested_enabled,updated_at,status)
                    VALUES(?,1,?,'AWAITING_VERIFIED_LIVE_ORDER_BRIDGE')
                    ON CONFLICT(connection_id) DO UPDATE SET requested_enabled=1,updated_at=excluded.updated_at,status=excluded.status''',
                    (cid,now))
                db.execute('''INSERT INTO apex_trade_controls(connection_id,desired_enabled,effective_enabled,updated_at,last_error)
                    VALUES(?,0,0,?,'LIVE_NATIVE_ORDER_BRIDGE_NOT_AUTHORIZED')
                    ON CONFLICT(connection_id) DO UPDATE SET
                    desired_enabled=0,effective_enabled=0,updated_at=excluded.updated_at,last_error=excluded.last_error''',
                    (cid,now))
                db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                           (user_id,cid,1,"CUSTOMER_REQUESTED_LIVE_ACTIVATION_PENDING_BROKER_BRIDGE",now))
                return handler.reply(202,{"connection_id":cid,"requested_enabled":True,
                    "trading_enabled":False,"status":"PENDING_VERIFIED_LIVE_BRIDGE",
                    "message":"LIVE trading request saved. Real-money trading remains OFF until a verified LIVE order bridge, broker authorization, valid licensing and risk controls are active."})
            # The authenticated customer can REQUEST DEMO activation. Only the
            # independent broker worker may later acknowledge effective ON.
            # Neither this endpoint nor an administrator can manufacture a broker ACK.
            if state!="CONNECTED" or not verified or not binding:
                db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                           (user_id,cid,1,"DENIED_NOT_CONNECTED",now))
                return handler.reply(409,{"error":"MT5 is not connected; trading stays OFF."})
            db.execute("INSERT INTO apex_trade_controls(connection_id,desired_enabled,effective_enabled,updated_at,last_error) VALUES(?,1,0,?,'PENDING_NATIVE_V2_BROKER_ACK') ON CONFLICT(connection_id) DO UPDATE SET desired_enabled=1,effective_enabled=0,updated_at=excluded.updated_at,last_error='PENDING_NATIVE_V2_BROKER_ACK'",(cid,now))
            db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                       (user_id,cid,1,"CUSTOMER_REQUESTED_DEMO_ACTIVATION_PENDING_BROKER_ACK",now))
            return handler.reply(202,{"connection_id":cid,"requested_enabled":True,
                      "trading_enabled":False,"status":"PENDING_NATIVE_V2_EXECUTION_ACK",
                      "message":"Your DEMO trading request is recorded. Automatic orders remain OFF until independent broker and cutover checks acknowledge activation."})
        if environment=="LIVE":
            # This must work even while LIVE activation is pending, and
            # revokes both any future issuer intent and legacy control flags.
            db.execute('''INSERT INTO apex_live_trading_requests(connection_id,requested_enabled,updated_at,status)
              VALUES(?,0,?,'CUSTOMER_OFF')
              ON CONFLICT(connection_id) DO UPDATE SET
              requested_enabled=0,updated_at=excluded.updated_at,status='CUSTOMER_OFF' ''',(cid,now))
            db.execute('''INSERT INTO apex_trade_controls(connection_id,desired_enabled,effective_enabled,updated_at,last_error)
              VALUES(?,0,0,?,NULL)
              ON CONFLICT(connection_id) DO UPDATE SET
              desired_enabled=0,effective_enabled=0,updated_at=excluded.updated_at,last_error=NULL''',(cid,now))
            db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                       (user_id,cid,0,"LIVE_OFF_CONFIRMED_NO_NATIVE_ORDER_PERMISSION",now))
            return handler.reply(200,{"connection_id":cid,"requested_enabled":False,
                 "trading_enabled":False,"status":"LIVE_OFF","message":"LIVE trading request OFF. No new real-money order permission is enabled."})
        if effective:
            # Immediately revoke permission for all new orders: the APEX
            # dispatcher requires desired_enabled=1 AND effective_enabled=1.
            # The native account acknowledgement worker will confirm effective OFF.
            db.execute("""UPDATE apex_trade_controls SET desired_enabled=0,
                last_error='STOP_REQUESTED_AWAITING_NATIVE_ACK',updated_at=?
                WHERE connection_id=?""",(now,cid))
            db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                       (user_id,cid,0,"CUSTOMER_REQUESTED_STOP_PENDING_NATIVE_ACK",now))
            return handler.reply(202,{"connection_id":cid,"requested_enabled":False,
                "trading_enabled":True,"status":"STOP_PENDING_NATIVE_ACK",
                "message":"New entry requests denied immediately; native worker confirming OFF."})
        db.execute("INSERT INTO apex_trade_controls(connection_id,desired_enabled,effective_enabled,updated_at,last_error) VALUES(?,0,0,?,NULL) ON CONFLICT(connection_id) DO UPDATE SET desired_enabled=0,effective_enabled=0,updated_at=excluded.updated_at,last_error=NULL",(cid,now))
        db.execute("INSERT INTO apex_trade_control_audit(account_id,connection_id,requested_enabled,outcome,occurred_at) VALUES(?,?,?,?,?)",
                   (user_id,cid,0,"OFF_CONFIRMED_NO_ACTIVE_EXECUTION",now))
        return handler.reply(200,{"connection_id":cid,"trading_enabled":False,"status":"OFF"})
