#!/usr/bin/python3
"""ABUTRON V4 6207: atomic CRM revision fence, without broker order rights.

Transactional SQLite triggers observe portal, manager, and activation mutations.
This does NOT authorize, acknowledge, or deliver any MT5 order.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

CID = "d6fc2524ec373b8d1bc278a8be3ec635"
LOGIN = "32456207"
TABLE = "abutron_v4_6207_activation_revision"
TRIGGERS = (
    "abutron_v4_6207_ctrl_insert",
    "abutron_v4_6207_ctrl_update",
    "abutron_v4_6207_ctrl_delete",
    "abutron_v4_6207_connection_update",
    "abutron_v4_6207_connection_delete",
)

SCHEMA = f"""
CREATE TABLE {TABLE} (
 connection_id TEXT PRIMARY KEY NOT NULL CHECK(connection_id='{CID}'),
 revision INTEGER NOT NULL CHECK(revision>=1),
 desired_enabled INTEGER NOT NULL CHECK(desired_enabled IN (0,1)),
 effective_enabled INTEGER NOT NULL CHECK(effective_enabled IN (0,1)),
 connection_status TEXT NOT NULL,
 ack_revision INTEGER,
 ack_expires_utc INTEGER,
 updated_utc TEXT NOT NULL,
 last_event TEXT NOT NULL,
 CHECK(ack_revision IS NULL OR ack_revision=revision)
);
CREATE TRIGGER {TRIGGERS[0]} AFTER INSERT ON apex_trade_controls
WHEN NEW.connection_id='{CID}' BEGIN
 UPDATE {TABLE} SET revision=revision+1,
 desired_enabled=NEW.desired_enabled, effective_enabled=NEW.effective_enabled,
 ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONTROL_INSERT',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=NEW.connection_id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;
CREATE TRIGGER {TRIGGERS[1]} AFTER UPDATE ON apex_trade_controls
WHEN NEW.connection_id='{CID}' BEGIN
 UPDATE {TABLE} SET revision=revision+1,
 desired_enabled=NEW.desired_enabled, effective_enabled=NEW.effective_enabled,
 ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONTROL_UPDATE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=NEW.connection_id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;
CREATE TRIGGER {TRIGGERS[2]} AFTER DELETE ON apex_trade_controls
WHEN OLD.connection_id='{CID}' BEGIN
 UPDATE {TABLE} SET revision=revision+1,desired_enabled=0,
 effective_enabled=0, ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONTROL_DELETE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=OLD.connection_id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;
CREATE TRIGGER {TRIGGERS[3]} AFTER UPDATE ON apex_mt5_connections
WHEN NEW.id='{CID}' BEGIN
 UPDATE {TABLE} SET revision=revision+1,
 connection_status=NEW.status,ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONNECTION_UPDATE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=NEW.id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;
CREATE TRIGGER {TRIGGERS[4]} AFTER DELETE ON apex_mt5_connections
WHEN OLD.id='{CID}' BEGIN
 UPDATE {TABLE} SET revision=revision+1,connection_status='DELETED',
 desired_enabled=0,effective_enabled=0,ack_revision=NULL,ack_expires_utc=NULL,
 last_event='CONNECTION_DELETE',updated_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE connection_id=OLD.id;
 SELECT RAISE(ABORT,'V4_REVISION_FENCE_ROW_MISSING') WHERE changes()!=1;
END;
"""


def snapshot(db: sqlite3.Connection) -> dict:
    c = db.execute("""SELECT x.id,x.account_reference,x.broker_server,
      x.environment,x.status,t.desired_enabled,t.effective_enabled
      FROM apex_mt5_connections x JOIN apex_trade_controls t
      ON t.connection_id=x.id WHERE x.id=?""", (CID,)).fetchall()
    if len(c) != 1:
        raise RuntimeError("BROKER_ACCOUNT_NOT_UNIQUE")
    row = c[0]
    if row[:5] != (CID, LOGIN, "Deriv-Demo", "DEMO", "CONNECTED"):
        raise RuntimeError("WRONG_ACCOUNT_ENVIRONMENT_OR_STATE")
    if row[5:] != (1, 0):
        raise RuntimeError("CURRENT_ACTIVATION_CHANGED_STOP")
    live = db.execute("""SELECT COUNT(*) FROM apex_mt5_connections x
       JOIN apex_trade_controls t ON t.connection_id=x.id
       WHERE x.environment='LIVE' AND t.effective_enabled=1""").fetchone()[0]
    if live != 0:
        raise RuntimeError("LIVE_EXECUTION_PRESENT")
    return {"connection_id_suffix": CID[-4:], "desired": row[5],
            "effective": row[6], "status": row[4], "live_effective_count": live}


def migrate(db_path: str) -> dict:
    db = sqlite3.connect(db_path, isolation_level=None, timeout=12)
    try:
        db.execute("PRAGMA busy_timeout=12000")
        db.execute("BEGIN IMMEDIATE")
        try:
            before = snapshot(db)
            existing = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name=?",
                                  (TABLE,)).fetchone()[0]
            if existing:
                raise RuntimeError("REVISION_FENCE_ALREADY_EXISTS")
            # The one transaction contains schema, triggers, and initial state.
            # sqlite3.executescript implicitly commits: avoid it.
            db.execute(SCHEMA.split("CREATE TRIGGER")[0].strip())
            row = db.execute("""SELECT t.desired_enabled,t.effective_enabled,x.status
                FROM apex_trade_controls t JOIN apex_mt5_connections x
                ON x.id=t.connection_id WHERE t.connection_id=?""",(CID,)).fetchone()
            db.execute(f"""INSERT INTO {TABLE}
                (connection_id,revision,desired_enabled,effective_enabled,
                 connection_status,ack_revision,ack_expires_utc,updated_utc,last_event)
                VALUES (?,?,?,?,?,NULL,NULL,?,'MIGRATION_INITIAL_OBSERVATION')""",
                (CID, 1, row[0], row[1], row[2],
                 time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())))
            # Triggers cannot be naively semicolon-split. Each is an explicit statement.
            for sql in trigger_statements():
                db.execute(sql)
            after = snapshot(db)
            assert before == after
            record = db.execute(f"SELECT revision,desired_enabled,effective_enabled,ack_revision FROM {TABLE} WHERE connection_id=?", (CID,)).fetchone()
            assert record == (1,1,0,None)
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            db.execute("COMMIT")
            return {"status":"CRM_REVISION_FENCE_INSTALLED","revision":record[0],
                    "desired":record[1],"effective":record[2],
                    "triggers":len(TRIGGERS),"order_authorization":False}
        except BaseException:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()


def trigger_statements() -> list[str]:
    """Split the static SQL at CREATE TRIGGER boundaries, not semicolons."""
    chunks=SCHEMA.split("CREATE TRIGGER ")
    assert len(chunks)==len(TRIGGERS)+1
    return ["CREATE TRIGGER "+chunk.strip() for chunk in chunks[1:]]



def rollback_unactivated(db_path: str) -> dict:
    """Undo ONLY a still-unused revision installation, never an active ACK."""
    db=sqlite3.connect(db_path,isolation_level=None,timeout=12)
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            row=db.execute(f"""SELECT revision,desired_enabled,effective_enabled,
                      ack_revision,ack_expires_utc FROM {TABLE}
                      WHERE connection_id=?""",(CID,)).fetchone()
            if row!=(1,1,0,None,None):
                raise RuntimeError("REVISION_FENCE_ACTIVE_OR_CHANGED_ROLLBACK_DENIED")
            if snapshot(db)["effective"]!=0:
                raise RuntimeError("EXTERNAL_EFFECTIVE_EXECUTION_CHANGED")
            for trigger in TRIGGERS:
                db.execute("DROP TRIGGER "+trigger)
            db.execute("DROP TABLE "+TABLE)
            assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            db.execute("COMMIT")
            return {"status":"UNUSED_REVISION_FENCE_ROLLED_BACK","triggers_removed":len(TRIGGERS)}
        except BaseException:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()

def read_fence(db_path: str) -> dict:
    with sqlite3.connect("file:"+db_path+"?mode=ro",uri=True,timeout=6) as db:
        db.execute("PRAGMA query_only=ON")
        c=db.execute(f"""SELECT revision,desired_enabled,effective_enabled,
            connection_status,ack_revision,ack_expires_utc,last_event
            FROM {TABLE} WHERE connection_id=?""",(CID,)).fetchone()
        if c is None:
            raise RuntimeError("REVISION_FENCE_MISSING")
        real=db.execute("""SELECT t.desired_enabled,t.effective_enabled,x.status
            FROM apex_trade_controls t JOIN apex_mt5_connections x
            ON t.connection_id=x.id WHERE t.connection_id=?""",(CID,)).fetchone()
    if not real or (c[1],c[2],c[3])!=real:
        raise RuntimeError("FENCE_AND_CRM_STATE_DIVERGED")
    return {"revision":c[0],"desired":c[1],"effective":c[2],
            "connection_status":c[3],"ack_revision":c[4],
            "ack_expires_utc":c[5],"last_event":c[6],
            "order_authorization":False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",default="/var/lib/apex-signup/accounts.sqlite3")
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply",action="store_true")
    g.add_argument("--inspect",action="store_true")
    g.add_argument("--rollback-unused",action="store_true")
    a=p.parse_args()
    action = migrate if a.apply else rollback_unactivated if a.rollback_unused else read_fence
    print(json.dumps(action(a.database),sort_keys=True))
if __name__=="__main__":
    main()
