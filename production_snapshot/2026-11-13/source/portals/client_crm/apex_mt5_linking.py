"""APEX MT5 connection lifecycle: user-owned records only, no fake broker sessions.

Account enrollment is not broker authentication. Broker CONNECTED status can
only be applied by a separately authenticated, isolated MT5 worker in future.
Never switch the existing shared MT5 terminal from public API requests.
"""
import re
import secrets
import sqlite3
import time
import account_flow
import abutron_mt5_portal_adapter

MT5_LOGIN = re.compile(r"^[0-9]{4,20}$")
MT5_SERVER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.:-]{2,99}$")
CONNECTION_ID = re.compile(r"^[a-f0-9]{32}$")
VALID_BROKERS = {"Deriv", "IC Markets", "FP Markets"}

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS apex_mt5_connection_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      connection_id TEXT NOT NULL REFERENCES apex_mt5_connections(id),
      account_id TEXT NOT NULL, event TEXT NOT NULL,
      occurred_at INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS apex_mt5_event_connection ON apex_mt5_connection_events(connection_id,occurred_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS apex_mt5_link_attempts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id TEXT NOT NULL, created_at INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS apex_mt5_link_attempts_account ON apex_mt5_link_attempts(account_id,created_at)")

def get_connections(handler, connect, account_id):
    with connect() as db:
        rows = db.execute("""SELECT c.id,c.broker,c.environment,c.account_reference,c.broker_server,
            c.status,c.broker_verified_at,c.worker_binding,c.updated_at,
            COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0),
            (SELECT MAX(e.occurred_at) FROM apex_mt5_connection_events e
             WHERE e.connection_id=c.id AND e.event='NATIVE_DEMO_IDENTITY_PROVED')
            FROM apex_mt5_connections c LEFT JOIN apex_trade_controls t ON t.connection_id=c.id
            WHERE c.account_id=? ORDER BY c.created_at DESC LIMIT 50""",(account_id,)).fetchall()
    result=[]
    for rid,broker,env,reference,server,status,verified,binding,updated,desired,effective,login_proved in rows:
        if status=="CONNECTED":
            try:
                proof=abutron_mt5_portal_adapter.rpc({"op":"status","owner":account_id,
                    "connection_id":rid},timeout=2)
                if proof.get("persistent_broker_session") is not True:
                    status="ERROR";verified=None;binding=None;effective=0
            except (OSError,ValueError,TypeError):
                status="ERROR";verified=None;binding=None;effective=0
        result.append({"id":rid,"broker":broker,"platform":"MT5","environment":env,
             "account_reference_masked":"••••"+reference[-4:],"broker_server":server,
             "connection_status":status,"broker_verified":bool(status=="CONNECTED" and verified is not None and binding),
             "trading_enabled":bool(effective),"requested_enabled":bool(desired),
             "crm_switch_effective":bool(effective),"broker_execution_verified":None,
             "execution_status":"NOT_ATTESTED_BY_CRM",
             "updated_at":updated,
             "last_native_login_proof_at":login_proved,
             "persistent_broker_session":bool(status=="CONNECTED" and verified is not None and binding)})
    return handler.reply(200,{"connections":result})

def start(handler, connect, account_id, payload):
    if set(payload)!={"broker","environment","account_reference","broker_server","understand_not_connected"}:
        return handler.reply(422,{"error":"MT5 broker, environment, login ID, server and acknowledgement required."})
    broker=payload["broker"]
    env=payload["environment"]
    login=payload["account_reference"]
    server=payload["broker_server"]
    if not (isinstance(broker,str) and broker in VALID_BROKERS
            and env in ("DEMO","LIVE") and isinstance(login,str)
            and MT5_LOGIN.fullmatch(login) and isinstance(server,str)
            and MT5_SERVER.fullmatch(server) and payload["understand_not_connected"] is True):
        return handler.reply(422,{"error":"Enter a valid MT5 login ID and exact broker server. No passwords accepted here."})
    now=int(time.time())
    cid=secrets.token_hex(16)
    with connect() as db:
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM apex_mt5_link_attempts WHERE created_at<?",(now-86400,))
            attempts=db.execute("SELECT COUNT(*) FROM apex_mt5_link_attempts WHERE account_id=? AND created_at>?",
                                (account_id,now-3600)).fetchone()[0]
            count=db.execute("SELECT COUNT(*) FROM apex_mt5_connections WHERE account_id=? AND status!='DISCONNECTED'",
                             (account_id,)).fetchone()[0]
            if attempts>=8 or count>=15:
                db.execute("ROLLBACK")
                return handler.reply(429,{"error":"Maximum account linking attempts reached. Try again later."})
            existing=db.execute("""SELECT id,status FROM apex_mt5_connections
                 WHERE account_id=? AND broker=? AND environment=? AND account_reference=? AND broker_server=?""",
                 (account_id,broker,env,login,server)).fetchone()
            if existing and existing[1]!="DISCONNECTED":
                db.execute("ROLLBACK")
                return handler.reply(409,{"error":"This MT5 account is already enrolled.","connection_id":existing[0]})
            db.execute("INSERT INTO apex_mt5_link_attempts(account_id,created_at) VALUES(?,?)",(account_id,now))
            if existing:
                cid=existing[0]
                db.execute("""UPDATE apex_mt5_connections SET status='CONNECTING',
                    broker_verified_at=NULL,worker_binding=NULL,updated_at=? WHERE id=? AND account_id=?""",
                    (now,cid,account_id))
                db.execute("DELETE FROM apex_trade_controls WHERE connection_id=?",(cid,))
            else:
                db.execute("""INSERT INTO apex_mt5_connections
                 (id,account_id,broker,environment,account_reference,broker_server,
                  status,broker_verified_at,worker_binding,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,'CONNECTING',NULL,NULL,?,?)""",
                 (cid,account_id,broker,env,login,server,now,now))
            db.execute("""INSERT INTO apex_mt5_connection_events
             (connection_id,account_id,event,occurred_at,detail) VALUES(?,?,?,?,'')""",
             (cid,account_id,"CLIENT_LINK_INITIATED",now))
            account_flow.notice(db,account_id,"broker_notice",now)
            db.execute("COMMIT")
        except (sqlite3.IntegrityError,sqlite3.OperationalError):
            db.execute("ROLLBACK")
            return handler.reply(503,{"error":"MT5 enrollment could not be saved."})
    return handler.reply(201,{"connection_id":cid,"connection_status":"CONNECTING",
        "trading_enabled":False,"broker_authenticated":False,
        "next_step":"Secure MT5 account authorization via isolated broker worker.",
        "message":"MT5 account enrolled. Broker authentication is not yet complete; trading stays OFF."})

def status(handler, connect, account_id, cid):
    if not CONNECTION_ID.fullmatch(cid):
        return handler.reply(404,{"error":"Connection not found."})
    with connect() as db:
        row=db.execute("""SELECT status,broker_verified_at,worker_binding,updated_at
                          FROM apex_mt5_connections WHERE account_id=? AND id=?""",
                       (account_id,cid)).fetchone()
    if not row:return handler.reply(404,{"error":"Connection not found."})
    state,verified,binding,when=row
    return handler.reply(200,{"connection_id":cid,"connection_status":state,
          "broker_authenticated":bool(verified and binding and state=="CONNECTED"),
          "updated_at":when,"trading_enabled":False if not (verified and binding) else None})

def disconnect(handler, connect, account_id, cid):
    if not CONNECTION_ID.fullmatch(cid):
        return handler.reply(404,{"error":"Connection not found."})
    now=int(time.time())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("""SELECT c.status,COALESCE(t.effective_enabled,0)
            FROM apex_mt5_connections c LEFT JOIN apex_trade_controls t ON t.connection_id=c.id
            WHERE c.account_id=? AND c.id=?""",(account_id,cid)).fetchone()
        if row is None:
            db.execute("ROLLBACK")
            return handler.reply(404,{"error":"Connection not found."})
        if row[1] or row[0]=="CONNECTED":
            db.execute("ROLLBACK")
            return handler.reply(409,{"error":"Active broker sessions must first be stopped and revoked by the execution gateway."})
        db.execute("""UPDATE apex_mt5_connections SET status='DISCONNECTED',
            broker_verified_at=NULL,worker_binding=NULL,updated_at=?
            WHERE account_id=? AND id=?""",(now,account_id,cid))
        db.execute("""INSERT INTO apex_trade_controls(connection_id,desired_enabled,effective_enabled,updated_at)
            VALUES(?,0,0,?) ON CONFLICT(connection_id) DO UPDATE SET
            desired_enabled=0,effective_enabled=0,updated_at=excluded.updated_at""",(cid,now))
        db.execute("""INSERT INTO apex_mt5_connection_events
            (connection_id,account_id,event,occurred_at,detail)
            VALUES(?,?,?,?,'')""",(cid,account_id,"CLIENT_UNLINKED",now))
        account_flow.notice(db,account_id,"broker_notice",now)
        db.execute("COMMIT")
    return handler.reply(200,{"connection_status":"DISCONNECTED","trading_enabled":False})
