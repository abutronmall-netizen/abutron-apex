"""ABUTRON DEMO MT5 direct broker verification. No OTP or persistent credential storage.
Authenticated customer session + same-origin POST are required by server.py.
Never sets a customer connection to CONNECTED without a persistent isolated worker.
"""
import re,sqlite3,time
import apex_mt5_secure_auth as native

APPROVED_DEMO={"Deriv":{"Deriv-Demo"},
               "IC Markets":{"ICMarketsSC-Demo"},
               "FP Markets":{"FPMarketsSC-Demo Server"}}
MESSAGES={
 "BROKER_AUTH_REJECTED":"The broker rejected the account credentials or server. Check the MT5 login, password, and exact DEMO server.",
 "VERIFIER_METAEDITOR_UPDATE":"The isolated MT5 verification terminal requires a MetaEditor update. The password has NOT been proven wrong.",
 "VERIFIER_RUNTIME_CONFLICT":"The isolated MT5 verification terminal has a runtime conflict. The password has NOT been proven wrong.",
 "BROKER_AUTH_SEEN_PROOF_MISSING":"MT5 broker authorization appeared successful, but the verifier could not complete account identity proof.",
 "VERIFIER_STARTUP_FAILED":"The isolated MT5 terminal failed to start. This does not mean the password is wrong.",
 "VERIFIER_TIMEOUT":"The broker verifier timed out. No account was connected.",
 "VERIFIER_SECURITY_DENIED":"The verifier's security checks prevented MT5 authentication.",
 "NATIVE_PROOF_MISSING":"MT5 did not produce the required broker account identity proof.",
 "NATIVE_VERIFICATION_INCONCLUSIVE":"The MT5 verification result was inconclusive.",
 "GATEWAY_OR_NATIVE_ERROR":"The broker verification gateway returned an unsupported result.",
 "GATEWAY_UNAVAILABLE":"The isolated MT5 verification gateway is unavailable."
}
def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS apex_mt5_direct_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL,
        connection_id TEXT NOT NULL,created_at INTEGER NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS apex_mt5_direct_attempts_rate ON apex_mt5_direct_attempts(account_id,created_at)")

def connect(handler,db_connect,account_id,connection_id,payload):
    if not isinstance(payload,dict) or set(payload)!={"password"}:
        return handler.reply(422,{"error":"Enter the MT5 broker password in the secure field."})
    password=payload["password"]
    if not isinstance(password,str) or not 1<=len(password)<=160 or any(ord(ch)<32 for ch in password):
        return handler.reply(422,{"error":"Enter a valid MT5 broker password."})
    if not re.fullmatch("[a-f0-9]{32}",connection_id):
        return handler.reply(404,{"error":"MT5 account not found."})
    if not native.session_hash(handler):
        return handler.reply(401,{"error":"Your ABUTRON client session expired. Sign in again."})
    if not native.verifier_probe():
        return handler.reply(503,{"error":"The isolated MT5 broker terminal is currently unavailable. No password was sent, and the account remains pending. Email-code verification is no longer required.",
            "reason_code":"NATIVE_VERIFIER_OFFLINE"})
    now=int(time.time())
    with db_connect() as db:
        try:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT broker,environment,broker_server,account_reference,status
                FROM apex_mt5_connections WHERE account_id=? AND id=?""",
                (account_id,connection_id)).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                return handler.reply(404,{"error":"This MT5 account does not belong to the signed-in client."})
            broker,environment,server,login,status=row
            if status!="CONNECTING" or environment!="DEMO" or server not in APPROVED_DEMO.get(broker,set()):
                db.execute("ROLLBACK")
                return handler.reply(409,{"error":"Only enrolled DEMO accounts with an approved broker server can use this verifier."})
            if not re.fullmatch("[0-9]{4,20}",login):
                db.execute("ROLLBACK")
                return handler.reply(409,{"error":"The enrolled MT5 account number is invalid."})
            db.execute("DELETE FROM apex_mt5_direct_attempts WHERE created_at<?",(now-86400,))
            window=db.execute("SELECT COUNT(*) FROM apex_mt5_direct_attempts WHERE account_id=? AND created_at>?",
                              (account_id,now-900)).fetchone()[0]
            daily=db.execute("SELECT COUNT(*) FROM apex_mt5_direct_attempts WHERE account_id=? AND created_at>?",
                             (account_id,now-86400)).fetchone()[0]
            if window>=5 or daily>=15:
                db.execute("ROLLBACK")
                return handler.reply(429,{"error":"Too many broker login attempts. Please try again later.","reason_code":"RATE_LIMIT"})
            db.execute("INSERT INTO apex_mt5_direct_attempts(account_id,connection_id,created_at) VALUES(?,?,?)",
                       (account_id,connection_id,now))
            db.execute("COMMIT")
        except sqlite3.Error:
            db.execute("ROLLBACK")
            return handler.reply(503,{"error":"Account verification service unavailable."})
    # Password is never stored or logged; only sent to the isolated UNIX socket.
    verified,diagnostic=native.native_verify(account_id,broker,server,login,password)
    password=None
    with db_connect() as db:
        try:
            db.execute("BEGIN IMMEDIATE")
            current=db.execute("SELECT status FROM apex_mt5_connections WHERE id=? AND account_id=?",
                               (connection_id,account_id)).fetchone()
            if current is None or current[0]!="CONNECTING":
                db.execute("ROLLBACK")
                return handler.reply(409,{"error":"The MT5 enrollment changed while verifying. No connection was established."})
            safe=diagnostic if diagnostic in MESSAGES or diagnostic=="NONE" else "NATIVE_VERIFICATION_INCONCLUSIVE"
            db.execute("""INSERT INTO apex_mt5_connection_events
              (connection_id,account_id,event,occurred_at,detail) VALUES(?,?,?,?,?)""",
              (connection_id,account_id,
               "NATIVE_DEMO_IDENTITY_PROVED" if verified else "NATIVE_DEMO_IDENTITY_NOT_PROVED",
               int(time.time()),"direct_broker_verification" if verified else safe))
            db.execute("COMMIT")
        except sqlite3.Error:
            db.execute("ROLLBACK")
            return handler.reply(503,{"error":"Unable to save verification result. Connection remains pending."})
    return handler.reply(200 if verified else 409,{
      "broker_identity_verified":bool(verified),"persistent_connection":False,
      "connection_status":"CONNECTING","trading_enabled":False,
      "reason_code":"NONE" if verified else safe,
      "message":("MT5 broker login verified. A persistent customer broker session has not yet been established; trading is OFF."
         if verified else MESSAGES.get(safe,"Broker verification failed.")+" Trading remains OFF.")
    })
