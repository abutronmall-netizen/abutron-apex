#!/usr/bin/python3
"""6207 CRM revision precondition, not broker permission.

Read only except BEGIN IMMEDIATE serialization while evaluating the CRM
precondition. Do not invoke a network/broker order while holding this lock
without a separately reviewed timeout and a real broker authorization adapter.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

CID="d6fc2524ec373b8d1bc278a8be3ec635"
LOGIN="32456207"
LEDGER="abutron_v4_6207_activation_revision"

class CRMRevisionDenied(PermissionError):
    pass

def _status(db: sqlite3.Connection, expected_revision: int, now_epoch: int) -> dict:
    if type(expected_revision) is not int or expected_revision<1:
        raise CRMRevisionDenied("CRM_REVISION_INVALID")
    rows=db.execute(f"""SELECT x.account_reference,x.environment,x.broker,
       x.broker_server,x.status,x.account_id,t.desired_enabled,t.effective_enabled,
       r.revision,r.desired_enabled,r.effective_enabled,r.connection_status,
       r.ack_revision,r.ack_expires_utc
       FROM apex_mt5_connections x
       JOIN apex_trade_controls t ON t.connection_id=x.id
       JOIN {LEDGER} r ON r.connection_id=x.id
       WHERE x.id=?""",(CID,)).fetchall()
    if len(rows)!=1:
        raise CRMRevisionDenied("CRM_BINDING_OR_LEDGER_MISSING")
    (login,env,broker,server,state,owner,desired,effective,
     revision,s_desired,s_effective,s_state,ack,expiry)=rows[0]
    if (login,env,broker,server,state)!=(
        LOGIN,"DEMO","Deriv","Deriv-Demo","CONNECTED"):
        raise CRMRevisionDenied("CRM_NATIVE_DEMO_BINDING_INVALID")
    if (desired,effective,state)!=(s_desired,s_effective,s_state):
        raise CRMRevisionDenied("CRM_FENCE_OR_CURRENT_CONTROL_DIVERGED")
    if revision!=expected_revision:
        raise CRMRevisionDenied("CRM_REVISION_STALE")
    if desired!=1 or effective!=1:
        raise CRMRevisionDenied("CRM_OFF_OR_NOT_EFFECTIVE")
    # ACK must be independently authenticated at installation; a row alone
    # never proves a genuine broker acknowledgement.
    if (ack!=revision or type(expiry) is not int or
        not now_epoch<expiry<=now_epoch+30):
        raise CRMRevisionDenied("CRM_BROKER_ACK_REVISION_OR_TTL_UNPROVEN")
    live=db.execute("""SELECT COUNT(*) FROM apex_mt5_connections x
      JOIN apex_trade_controls t ON t.connection_id=x.id
      WHERE x.environment='LIVE' AND t.effective_enabled=1""").fetchone()[0]
    if live:
        raise CRMRevisionDenied("LIVE_EXECUTION_PRESENT")
    return {"revision":revision,"account_suffix":LOGIN[-4:],
            "customer_id":owner,"crm_precondition":True,
            "broker_order_authorized":False}

def inspect_precondition(db_path: str|Path, expected_revision: int,
                         now_epoch: int) -> dict:
    conn=sqlite3.connect("file:"+str(db_path)+"?mode=ro",
                         uri=True,timeout=0.5)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        try:
            return _status(conn,expected_revision,now_epoch)
        finally: conn.execute("ROLLBACK")
    except sqlite3.Error as e:
        raise CRMRevisionDenied("CRM_LEDGER_UNAVAILABLE") from e
    finally:conn.close()

@contextmanager
def isolated_pre_send_barrier(db_path: str|Path, expected_revision: int,
                              now_epoch: int):
    """Serializable proof for local unit tests; no production order transport.

    Holds BEGIN IMMEDIATE over the caller's tiny local critical section.
    OrderSend is external and requires its own independently certified atomic
    broker/CRM fence; this SQLite context alone cannot guarantee wire delivery.
    """
    conn=sqlite3.connect(str(db_path),timeout=0.25,isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=250")
        conn.execute("BEGIN IMMEDIATE")
        proof=_status(conn,expected_revision,now_epoch)
        try:
            yield proof
        finally:
            conn.execute("ROLLBACK")
    except sqlite3.Error as e:
        raise CRMRevisionDenied("CRM_SEND_REVISION_BARRIER_UNAVAILABLE") from e
    finally:conn.close()
