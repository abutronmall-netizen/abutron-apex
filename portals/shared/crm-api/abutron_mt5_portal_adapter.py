"""ABUTRON client portal -> local private MT5 manager. Credentials are never persisted."""
import socket,json,re
PATH="/run/abutron-client-mt5-manager/manager.sock"
CID=re.compile(r"^[a-f0-9]{32}$")
LOGIN=re.compile(r"^[0-9]{4,20}$")
SERVER_MODES={("Deriv","Deriv-Demo"):"DEMO",("Deriv","DerivBVI-Server-02"):"LIVE",("Deriv","DerivSVG-Server"):"LIVE",("IC Markets","ICMarketsSC-Demo"):"DEMO",
 ("FP Markets","FPMarketsSC-Demo"):"DEMO",("FP Markets","FPMarketsSC-Demo Server"):"DEMO",
 ("FP Markets","FPMarketsLtd-Demo2"):"DEMO",("FP Markets","FPMarketsSC-Live"):"LIVE",
 ("FP Markets","FPMarketsLtd-Live2"):"LIVE"}
SERVERS=set(SERVER_MODES)
def rpc(obj,timeout=30):
 data=json.dumps(obj,separators=(",",":")).encode()+b"\n"
 if len(data)>2047:raise ValueError("MT5 request exceeds secure limit")
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
  sock.settimeout(timeout);sock.connect(PATH);sock.sendall(data)
  b=b""
  while not b.endswith(b"\n") and len(b)<4096:
   part=sock.recv(4096-len(b))
   if not part:break
   b+=part
 doc=json.loads(b)
 if not isinstance(doc,dict):raise ValueError("Invalid MT5 manager response")
 return doc
def probe():
 base={"private_gateway_ready":False,"customer_password_login_enabled":False,
       "persistent_client_sessions_ready":False,"live_mt5_login_enabled":False,
       "trading_authorized":False}
 try:
  x=rpc({"op":"probe"},timeout=2)
  if x.get("ok") is True and x.get("trading_authorized") is False:
   return {key:x.get(key,default) for key,default in base.items()}
 except (OSError,ValueError,TypeError,KeyError):pass
 return base
def connect(handler,db_connect,owner,payload):
 keys={"broker","environment","account_reference","broker_server","password","connection_id"}
 if set(payload)!=keys:
  return handler.reply(422,{"error":"Broker, MT5 username, password and server required."})
 broker=payload.get("broker");server=payload.get("broker_server")
 env=payload.get("environment");login=payload.get("account_reference")
 password=payload.get("password");cid=payload.get("connection_id")
 if not (isinstance(broker,str) and isinstance(server,str) and isinstance(login,str)
   and isinstance(password,str) and env==SERVER_MODES.get((broker,server)) and (broker,server) in SERVERS
   and LOGIN.fullmatch(login) and 1<=len(password)<=160 and
   not any(ord(c)<32 for c in password)):
  return handler.reply(422,{"error":"Valid MT5 login, password, matching account mode and exact broker server required."})
 if cid is not None and (not isinstance(cid,str) or not CID.fullmatch(cid)):
  return handler.reply(422,{"error":"Invalid selected MT5 account."})
 if not CID.fullmatch(owner):return handler.reply(403,{"error":"Client session invalid."})
 with db_connect() as c:
  old=c.execute("""SELECT id FROM apex_mt5_connections WHERE account_id=? AND broker=?
   AND environment=? AND account_reference=? AND broker_server=?""",
   (owner,broker,env,login,server)).fetchone()
  if cid is not None and (not old or cid!=old[0]):
   return handler.reply(409,{"error":"Selected MT5 account does not match these credentials."})
  cid=old[0] if old else None
 try:
  reply=rpc({"op":"connect","owner":owner,"connection_id":cid,"broker":broker,
             "server":server,"login":login,"password":password,"mode":env},timeout=30)
 except (OSError,ValueError,TypeError):
  return handler.reply(503,{"error":"Dedicated MT5 connection manager unavailable. No trading enabled."})
 status=reply.get("status",503)
 if not isinstance(status,int) or status<200 or status>599:status=503
 return handler.reply(status,reply if reply.get("ok") else {"error":reply.get("message","MT5 terminal unavailable.")})
def status(handler,owner,cid):
 if not CID.fullmatch(cid):return handler.reply(404,{"error":"Account not found."})
 try:x=rpc({"op":"status","owner":owner,"connection_id":cid},timeout=4)
 except (OSError,ValueError,TypeError):
  return handler.reply(503,{"error":"MT5 connection manager unavailable.","connection_status":"NOT_CONNECTED"})
 return handler.reply(x.get("status",503),x if x.get("ok") else {"error":x.get("message","Unavailable.")})
def disconnect(handler,owner,cid):
 if not CID.fullmatch(cid):return handler.reply(404,{"error":"Account not found."})
 try:x=rpc({"op":"disconnect","owner":owner,"connection_id":cid},timeout=30)
 except (OSError,ValueError,TypeError):
  return handler.reply(503,{"error":"Could not confirm MT5 terminal shutdown."})
 return handler.reply(x.get("status",503),x if x.get("ok") else {"error":x.get("message","Disconnect failed.")})
