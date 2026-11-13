"""Offline synthetic CRM transaction tests for direct V4; no broker orders."""
import runpy, sqlite3, tempfile, time
M=runpy.run_path("/usr/local/sbin/abutron-v4-crm-direct-intent-6207.candidate",run_name="QA")
now=int(time.time())
cid=M["DIRECT_CID"];owner="a"*32;signal="b"*64;nonce="c"*32
expires=now+9
digest=M["direct_digest_fields"](nonce=nonce,signal=signal,
  login="32456207",server="Deriv-Demo",symbol="Volatility 75 Index.0",
  side="BUY",lots="0.15",sl="100",tp="120",revision=10,expiry=expires)
def request(phase,lease="-",revision=10):
  return ("\r\n".join(["ABUTRON_V4_LOCAL_GUARD_V1",phase,nonce,signal,
      "32456207","Deriv-Demo","Volatility 75 Index.0","BUY",
      "0.15","100","120",str(revision),str(expires),lease])+"\r\n").encode("ascii")

with tempfile.TemporaryDirectory() as d:
 db=d+"/crm.sqlite3"
 c=sqlite3.connect(db)
 c.executescript("""
 CREATE TABLE accounts (id TEXT PRIMARY KEY,status TEXT);
 CREATE TABLE apex_mt5_connections (
  id TEXT PRIMARY KEY, account_id TEXT, broker TEXT, environment TEXT,
  account_reference TEXT, broker_server TEXT,status TEXT);
 CREATE TABLE apex_trade_controls (
  connection_id TEXT PRIMARY KEY,desired_enabled INTEGER,effective_enabled INTEGER);
 CREATE TABLE abutron_v4_6207_activation_revision (
  connection_id TEXT PRIMARY KEY,revision INTEGER,desired_enabled INTEGER,
  effective_enabled INTEGER,connection_status TEXT,ack_revision INTEGER,
  ack_expires_utc INTEGER);
 CREATE TABLE apex_crm_licenses (
  account_id TEXT PRIMARY KEY,plan TEXT,status TEXT,seats INTEGER);
 CREATE TABLE apex_admin_roles (
  account_id TEXT PRIMARY KEY,role TEXT,email_verified_at TEXT);
 """)
 c.execute("INSERT INTO accounts VALUES (?,?)",(owner,"approved"))
 c.execute("INSERT INTO apex_mt5_connections VALUES (?,?,?,?,?,?,?)",
    (cid,owner,"Deriv","DEMO","32456207","Deriv-Demo","CONNECTED"))
 c.execute("INSERT INTO apex_trade_controls VALUES (?,?,?)",(cid,1,1))
 c.execute("INSERT INTO abutron_v4_6207_activation_revision VALUES (?,?,?,?,?,?,?)",
    (cid,10,1,1,"CONNECTED",10,now+60))
 c.execute("INSERT INTO apex_crm_licenses VALUES (?,?,?,?)",(owner,"Enterprise","active",3))
 c.execute("INSERT INTO apex_admin_roles VALUES (?,?,?)",(owner,"SUPERADMIN","2026-11-09"))
 c.commit();c.close()
 M["direct_migrate"](db)
 M["migrate"](db)
 def denied(payload,check=lambda q,n: True):
  try:M["transact"](payload,db=db,now=now,check=check,direct_intent=True)
  except (M["Denied"],sqlite3.Error):return True
  return False
 assert denied(request("CLAIM"))
 print("NO_APPROVAL_CANNOT_CLAIM_PASS")
 c=sqlite3.connect(db)
 c.execute("""INSERT INTO abutron_v4_6207_direct_intents VALUES
   (?,?,?,?,? ,?,'APPROVED',?,?)""",(signal,cid,nonce,10,digest,expires,now,now))
 c.commit();c.close()
 assert denied(request("CLAIM",revision=11))
 print("WRONG_REVISION_CANNOT_CLAIM_PASS")
 claim=M["transact"](request("CLAIM"),db=db,now=now,check=lambda q,n: True,direct_intent=True)
 assert claim.startswith("ALLOW|")
 lease=claim[6:].strip()
 assert len(lease)==64
 assert denied(request("CLAIM"))
 print("DUPLICATE_CLAIM_REJECTED_PASS")
 c=sqlite3.connect(db)
 c.execute("UPDATE apex_trade_controls SET desired_enabled=0,effective_enabled=0 WHERE connection_id=?",(cid,))
 c.execute("UPDATE abutron_v4_6207_activation_revision SET revision=11,desired_enabled=0,effective_enabled=0,ack_revision=NULL WHERE connection_id=?",(cid,))
 c.commit();c.close()
 assert denied(request("SEND",lease=lease))
 print("CLIENT_OFF_BETWEEN_CLAIM_SEND_DENIED_PASS")
 c=sqlite3.connect(db)
 assert c.execute("select status from abutron_v4_6207_send_lease where signal_id=?",(signal,)).fetchone()[0]=="CLAIMED"
 assert c.execute("select state from abutron_v4_6207_direct_intents where signal_id=?",(signal,)).fetchone()[0]=="CLAIMED"
 print("OFF_REVOCATION_PRESERVES_UNCERTAIN_ORDER_LEASE_PASS")
