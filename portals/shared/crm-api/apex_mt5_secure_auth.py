"""APEX customer DEMO MT5 login with session-bound email MFA and isolated native verifier.

Never stores or logs broker passwords. Separates identity proof from persistent
trading connectivity. A successful proof does not grant live trading or orders.
"""
from __future__ import annotations
import hashlib, json, re, secrets, socket, time, uuid
import apex_mt5_mfa as mfa

SOCKET="/run/apex-mt5-private/verify.sock"
BROKER_SERVERS={"Deriv":{"Deriv-Demo"},"IC Markets":{"ICMarketsSC-Demo"},
                "FP Markets":{"FPMarketsSC-Demo Server"}}

def session_hash(handler):
    from http.cookies import SimpleCookie, CookieError
    jar=SimpleCookie()
    try:jar.load(handler.headers.get("Cookie","") or "")
    except CookieError:return None
    item=jar.get("apex_client")
    token=item.value if item else ""
    return hashlib.sha256(token.encode()).hexdigest() if re.fullmatch(r"[a-f0-9]{64}",token) else None

def begin(handler,connect,account_id,connection_id,payload):
    if payload!={}:return handler.reply(422,{"error":"No extra fields allowed."})
    if not verifier_probe():
        return handler.reply(503,{"error":"MT5 broker verification is temporarily unavailable while the isolated native terminal is being repaired. Enrollment remains available; no broker credentials were requested."})
    digest=session_hash(handler)
    if not digest:return handler.reply(401,{"error":"Sign in again."})
    with connect() as c:
        try:
            c.execute("BEGIN IMMEDIATE")
            result=mfa.begin(c,account_id,connection_id,digest)
            c.execute("COMMIT")
            return handler.reply(201,{"challenge_id":result["challenge_id"],
                 "expires_at":result["expires_at"],
                 "message":"A one-time MT5 authorization code has been queued to your verified APEX email. Enter the code and your MT5 password in the secure form. No trading is activated."})
        except mfa.MFAError as e:
            c.execute("ROLLBACK")
            return handler.reply(409,{"error":"MT5 authentication unavailable for this account or server.","code":str(e)})
        except Exception:
            c.execute("ROLLBACK")
            raise

def verifier_probe():
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(SOCKET)
            sock.sendall(b'{"op":"ping"}\n')
            result=json.loads(sock.recv(1200))
        return bool(result.get("schema")=="APEX_MT5_PRIVATE_DEMO_V1" and
                    result.get("ok") is True and result.get("verify_enabled") is True
                    and result.get("trading_authorized") is False)
    except (OSError,ValueError,TypeError):return False

def native_verify(account_id,broker,server,login,password):
    owner=str(uuid.UUID(hex=account_id,version=4))
    # Password goes through a PRIVATE UNIX socket to a disposable Wine/MT5
    # verifier subprocess. Never written into the CRM or an HTTP response.
    packet={"op":"verify","owner_id":owner,"broker":broker,"server":server,
            "login":login,"password":password,"mode":"DEMO"}
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(103)
            sock.connect(SOCKET)
            sock.sendall(json.dumps(packet,separators=(",",":")).encode()+b"\n")
            buffer=b""
            while not buffer.endswith(b"\n") and len(buffer)<1800:
                chunk=sock.recv(1800-len(buffer))
                if not chunk:break
                buffer+=chunk
        data=json.loads(buffer)
        valid=(data.get("schema")=="APEX_MT5_PRIVATE_DEMO_V1" and
               data.get("ok") is True and data.get("broker_authenticated") is True
               and data.get("trading_authorized") is False)
        allowed=frozenset((
            "NONE","BROKER_AUTH_REJECTED","VERIFIER_METAEDITOR_UPDATE",
            "VERIFIER_RUNTIME_CONFLICT","BROKER_AUTH_SEEN_PROOF_MISSING",
            "VERIFIER_STARTUP_FAILED","VERIFIER_TIMEOUT",
            "VERIFIER_SECURITY_DENIED","NATIVE_PROOF_MISSING",
            "NATIVE_VERIFICATION_INCONCLUSIVE"
        ))
        reason=data.get("failure_category")
        if valid:return True,"NONE"
        if isinstance(reason,str) and reason in allowed and reason!="NONE":
            return False,reason
        return False,"GATEWAY_OR_NATIVE_ERROR"
    except (OSError,ValueError,TypeError):return False,"GATEWAY_UNAVAILABLE"
    finally:
        packet.clear()
        
def finish(handler,connect,account_id,connection_id,payload):
    if set(payload)!={"challenge_id","code","password"}:
        return handler.reply(422,{"error":"Authorization code and MT5 password are required."})
    code=payload.get("code");password=payload.get("password")
    challenge_id=payload.get("challenge_id")
    if not (isinstance(code,str) and re.fullmatch(r"[0-9]{8}",code)
         and isinstance(password,str) and 1<=len(password)<=160
         and not any(ord(char)<32 for char in password)):
        return handler.reply(422,{"error":"Enter a valid eight-digit email code and broker MT5 password."})
    digest=session_hash(handler)
    if not digest:return handler.reply(401,{"error":"Sign in again."})
    if not verifier_probe():
        return handler.reply(503,{"error":"Secure MT5 broker authentication gateway is unavailable. No password was submitted."})
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("""SELECT broker,environment,broker_server,account_reference,status
            FROM apex_mt5_connections WHERE id=? AND account_id=?""",
            (connection_id,account_id)).fetchone()
        if (not row or row[1]!="DEMO" or row[4]!="CONNECTING" or
                row[2] not in BROKER_SERVERS.get(row[0],())):
            c.execute("ROLLBACK")
            return handler.reply(409,{"error":"This account is not eligible for DEMO MT5 authentication."})
        try:
            mfa.verify_once(c,account_id,connection_id,digest,challenge_id,code,
                            secret=mfa._secret())
        except (mfa.MFAError,OSError,TypeError,ValueError):
            # Preserve invalid-attempt audit increments if present.
            c.execute("COMMIT")
            return handler.reply(403,{"error":"The one-time email code is invalid, expired, already used, or not delivered."})
        c.execute("COMMIT")
    broker,_,server,login,_=row
    passed,diagnostic=native_verify(account_id,broker,server,login,password)
    # No account details, MT5 credentials or broker logs are returned or persisted.
    messages={
      "BROKER_AUTH_REJECTED":"The broker rejected this MT5 login. Check the login, password and exact DEMO server.",
      "VERIFIER_METAEDITOR_UPDATE":"ABUTRON MT5 verifier requires a MetaEditor update; credentials are not proven incorrect.",
      "VERIFIER_RUNTIME_CONFLICT":"ABUTRON MT5 verifier encountered a runtime conflict; credentials are not proven incorrect.",
      "BROKER_AUTH_SEEN_PROOF_MISSING":"The broker login appeared accepted, but the required MT5 proof script did not complete.",
      "VERIFIER_STARTUP_FAILED":"ABUTRON isolated MT5 verifier could not start; this does not prove a bad password.",
      "VERIFIER_TIMEOUT":"The MT5 verification attempt timed out; no account was connected.",
      "VERIFIER_SECURITY_DENIED":"MT5 security verification could not run. No account was connected.",
      "NATIVE_PROOF_MISSING":"Native MT5 account proof was not produced; the broker session is not verified.",
      "NATIVE_VERIFICATION_INCONCLUSIVE":"MT5 verification was inconclusive; no account was connected.",
      "GATEWAY_OR_NATIVE_ERROR":"The private MT5 verification service returned an unsupported result.",
      "GATEWAY_UNAVAILABLE":"The isolated MT5 gateway was unavailable; no account was connected."
    }
    failure_message=messages.get(diagnostic,"MT5 broker login not verified.")
    # A one-shot identity proof does NOT establish a persistent trading
    # connection. Never set status=CONNECTED or worker_binding without one.
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        current=c.execute("""SELECT status FROM apex_mt5_connections
                    WHERE id=? AND account_id=?""",(connection_id,account_id)).fetchone()
        if not current or current[0]!="CONNECTING":
            c.execute("ROLLBACK")
            return handler.reply(409,{"error":"Connection was removed or changed; no authorization applied."})
        c.execute("""INSERT INTO apex_mt5_connection_events
           (connection_id,account_id,event,occurred_at,detail) VALUES(?,?,?,?,?)""",
           (connection_id,account_id,"NATIVE_DEMO_IDENTITY_PROVED" if passed else
            "NATIVE_DEMO_IDENTITY_NOT_PROVED",int(time.time()),
            "no_persistent_session" if passed else diagnostic[:80]))
        c.execute("COMMIT")
    return handler.reply(200 if passed else 409,{
        "broker_identity_verified":passed,"persistent_connection":False,
        "connection_status":"CONNECTING","trading_enabled":False,
        "reason_code":"NONE" if passed else diagnostic,
        "message":("Broker MT5 login verified. Persistent customer MT5 session is not connected yet; automatic trading remains OFF."
                   if passed else failure_message+" No trading was enabled.")})
