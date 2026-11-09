"""APEX client license policy authority (business database, no broker-order methods).

New entries require valid customer license, unrevoked status, matching assigned
account seat and a verified broker-bound trading control.
Existing protective exits never depend on license or subscription state, but
still require a separate authenticated, account-bound broker worker.
"""
from datetime import datetime,timezone,date
import re
import sqlite3
import time
import apex_trial

def stamp():return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_license_revocations(
       account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
       revoked_at TEXT NOT NULL, revoked_by TEXT NOT NULL,
       reason TEXT NOT NULL, cleared_at TEXT, cleared_by TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_license_decision_audit(
       id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, connection_id TEXT,
       action TEXT NOT NULL, decision TEXT NOT NULL,
       reason TEXT NOT NULL, evaluated_at TEXT NOT NULL
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS apex_crm_license_decision_recent ON apex_crm_license_decision_audit(evaluated_at)")
def revoked(c,aid):
    x=c.execute("SELECT revoked_at,reason,cleared_at FROM apex_crm_license_revocations WHERE account_id=?",(aid,)).fetchone()
    if not x or x[2] is not None:return None
    return {"revoked_at":x[0],"reason":x[1]}

def account_decision(c,aid,broker,platform,environment,reference,server,connection_state=None,broker_verified=False,worker_binding=None,trading_active=False):
    """Read-only account-scoped decision; do not turn a CRM record into broker execution."""
    today=date.today().isoformat()
    user=c.execute("SELECT status FROM accounts WHERE id=?",(aid,)).fetchone()
    master=c.execute("SELECT plan,status,expires_on,seats FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone()
    seat=c.execute("""SELECT state,expires_on FROM apex_crm_account_licenses
          WHERE account_id=? AND broker=? AND platform=? AND environment=?
            AND account_reference=? AND broker_server=?""",(aid,broker,platform,environment,reference,server)).fetchone()
    is_revoked=revoked(c,aid) is not None
    reasons=[]
    if not user or user[0]!="approved":reasons.append("CLIENT_ACCESS_NOT_ACTIVE")
    trial_info=apex_trial.trial(c,aid)
    # Trials never override paused, expired or revoked paid licenses.
    if master:
        if master[1]!="active":reasons.append("CUSTOMER_LICENSE_"+master[1].upper())
        elif master[2] and master[2]<today:reasons.append("CUSTOMER_LICENSE_EXPIRED")
        if not seat:reasons.append("BROKER_ACCOUNT_LICENSE_MISSING")
        elif seat[0]!="assigned":reasons.append("BROKER_ACCOUNT_LICENSE_PAUSED")
        elif seat[1] and seat[1]<today:reasons.append("BROKER_ACCOUNT_LICENSE_EXPIRED")
    elif trial_info["status"]=="active":
        if not apex_trial.matching_seat(c,aid,broker,platform,environment,reference,server):
            reasons.append("TRIAL_DEMO_ACCOUNT_SEAT_MISSING_OR_NOT_ELIGIBLE")
    elif trial_info["status"]=="expired":
        reasons.append("TRIAL_EXPIRED_BUY_LICENSE")
    else:
        reasons.append("TRIAL_NOT_STARTED")
    if is_revoked:reasons.append("CUSTOMER_LICENSE_REVOKED")
    license_ok=not reasons
    connection_ok=connection_state=="CONNECTED" and bool(broker_verified) and bool(worker_binding)
    if not connection_ok:reasons.append("VERIFIED_BROKER_WORKER_NOT_CONNECTED")
    if not trading_active:reasons.append("ACCOUNT_EXECUTION_NOT_ACTIVE")
    return {
        "license_allows_new_entries":license_ok,
        "license_basis":"paid" if master else ("trial" if trial_info["status"]=="active" else "none"),
        "trial":trial_info,
        "new_entries_allowed":license_ok and connection_ok and bool(trading_active),
        "reason_codes":reasons,
        # A revoked/expired license does not authorize new entries, but
        # must never remove the ability to manage an existing open position.
        "protective_exit_rights_preserved":True,
        "protective_actions":["CLOSE_EXISTING","REDUCE_EXISTING","UPDATE_PROTECTIVE_SL_TP","CANCEL_PENDING"],
        "protective_actions_require_broker_authorization":True,
        "broker_worker_connected":connection_ok,
        "payment_provider_connected":False,
        "trading_engine_enforcement_connected":False
    }

def connection_decision(c,aid,cid):
    row=c.execute("""SELECT broker,environment,account_reference,broker_server,status,
              broker_verified_at,worker_binding FROM apex_mt5_connections
              WHERE account_id=? AND id=?""",(aid,cid)).fetchone()
    if not row:return None
    trade=c.execute("SELECT COALESCE(effective_enabled,0) FROM apex_trade_controls WHERE connection_id=?",(cid,)).fetchone()
    broker,env,ref,server,state,verified,binding=row
    decision=account_decision(c,aid,broker,"MT5",env,ref,server,state,verified is not None,binding,
                              bool(trade and trade[0]))
    decision.update({"connection_id":cid,"broker":broker,"platform":"MT5","environment":env,
                     "account_reference_masked":"••••"+ref[-4:],
                     "connection_status":state})
    return decision

def list_client(c,aid):
    rows=c.execute("""SELECT id FROM apex_mt5_connections WHERE account_id=? ORDER BY created_at DESC LIMIT 50""",(aid,)).fetchall()
    decisions=[connection_decision(c,aid,x[0]) for x in rows]
    lic=c.execute("SELECT plan,status,expires_on,seats FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone()
    seat_count=c.execute("""SELECT count(*) FROM apex_crm_account_licenses
       WHERE account_id=? AND state='assigned' AND (expires_on IS NULL OR expires_on>=date('now'))""",(aid,)).fetchone()[0]
    return {
        "customer_license": None if not lic else {"plan":lic[0],"status":lic[1],"expires_on":lic[2],
                      "seat_limit":lic[3],"allocated_seats":seat_count},
        "revocation":revoked(c,aid),
        "trial":apex_trial.trial(c,aid),
        "purchase_requests":apex_trial.requests(c,aid),
        "account_decisions":decisions,
        "entry_policy":"NEW_ENTRIES_DENIED_UNLESS_ALL_ACCOUNT_GATES_PASS",
        "exit_policy":"LICENSE_EXPIRY_OR_REVOCATION_DOES_NOT_CANCEL_EXISTING_PROTECTIVE_EXITS",
        "actual_broker_worker_enforcement":"NOT_CONNECTED",
        "payment_provider_connected":False
    }

def action(c,actor,payload,audit):
    aid=payload.get("account_id");action=payload.get("action")
    if not isinstance(aid,str) or not re.fullmatch("[a-z0-9-]{8,80}",aid):
        raise ValueError("Valid client account ID required.")
    if action not in ("revoke","restore"):
        raise ValueError("Choose Revoke or Restore.")
    if aid==actor:raise ValueError("Owner cannot revoke their own administrator license.")
    if not c.execute("SELECT 1 FROM accounts WHERE id=?",(aid,)).fetchone():
        raise ValueError("Client does not exist.")
    if not c.execute("SELECT 1 FROM apex_crm_licenses WHERE account_id=?",(aid,)).fetchone():
        raise ValueError("Create a customer license before managing revocation.")
    record=revoked(c,aid)
    now=stamp()
    if action=="revoke":
        reason=payload.get("reason","")
        if not isinstance(reason,str) or not 5<=len(reason.strip())<=500:
            raise ValueError("A revocation reason of 5–500 characters is required.")
        if record:raise ValueError("License already revoked.")
        c.execute("""INSERT INTO apex_crm_license_revocations
            (account_id,revoked_at,revoked_by,reason,cleared_at,cleared_by)
            VALUES(?,?,?, ?,NULL,NULL)
            ON CONFLICT(account_id) DO UPDATE SET revoked_at=excluded.revoked_at,
            revoked_by=excluded.revoked_by,reason=excluded.reason,cleared_at=NULL,cleared_by=NULL""",
            (aid,now,actor,reason.strip()))
        audit(c,actor,aid,"LICENSE_REVOKED",reason.strip()[:200])
        return {"status":"revoked","new_entries_license_permitted":False,
                "existing_protective_exits_unchanged":True}
    if not record:raise ValueError("License has no active revocation.")
    c.execute("UPDATE apex_crm_license_revocations SET cleared_at=?,cleared_by=? WHERE account_id=?",
              (now,actor,aid))
    audit(c,actor,aid,"LICENSE_REVOCATION_CLEARED")
    return {"status":"restored","new_entries_license_permitted":"subject_to_all_other_gates",
            "existing_protective_exits_unchanged":True}
