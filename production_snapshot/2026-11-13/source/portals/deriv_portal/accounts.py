"""Local APEX Deriv DEMO account profiles.

Metadata only. No passwords, tokens, balances or trading instructions are stored.
A saved profile is not evidence of a live broker connection.
"""
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone

DB = Path("/home/apexmt5/bridge-runtime/apex_deriv_accounts.sqlite3")
MAX_ACCOUNTS = 20

def validate(login, server, name=""):
    if not isinstance(login, str) or not re.fullmatch(r"[0-9]{4,15}", login):
        raise ValueError("MT5 login must be 4–15 digits")
    if not isinstance(server, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}", server):
        raise ValueError("Invalid MT5 server")
    if "deriv" not in server.lower() or "demo" not in server.lower():
        raise ValueError("Deriv DEMO servers only")
    if not isinstance(name, str) or len(name) > 48 or any(ord(c) < 32 for c in name):
        raise ValueError("Invalid account label")
    return login, server, name.strip() or ("Deriv DEMO · " + login[-4:])

def open_db():
    DB.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=5)
    if DB.exists():
        os.chmod(DB, 0o600)
    conn.execute("""CREATE TABLE IF NOT EXISTS profiles(
        login TEXT NOT NULL, server TEXT NOT NULL,
        label TEXT NOT NULL, requested_at TEXT,
        PRIMARY KEY(login,server)
    )""")
    conn.commit()
    return conn

def list_profiles():
    with open_db() as conn:
        rows = conn.execute(
            "SELECT login,server,label,requested_at FROM profiles ORDER BY label COLLATE NOCASE, login"
        ).fetchall()
    return [
        {"login": login, "server": server, "label": label,
         "login_requested_at": requested_at, "connected": False,
         "verified": False, "orders_enabled": False}
        for login,server,label,requested_at in rows
    ]

def save_profile(login, server, name="", requested=False):
    login,server,label=validate(login,server,name)
    timestamp=datetime.now(timezone.utc).isoformat() if requested else None
    with open_db() as conn:
        count=conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        exists=conn.execute("SELECT label,requested_at FROM profiles WHERE login=? AND server=?",
                            (login,server)).fetchone()
        if not exists and count >= MAX_ACCOUNTS:
            raise ValueError("Maximum number of DEMO profiles reached")
        # Retain the existing profile's name and previous launch status unless explicitly changed.
        if exists and not name:
            label=exists[0]
        prior=exists[1] if exists else None
        conn.execute(
            """INSERT INTO profiles(login,server,label,requested_at)
               VALUES(?,?,?,?)
               ON CONFLICT(login,server) DO UPDATE SET
                 label=excluded.label, requested_at=excluded.requested_at""",
            (login,server,label,timestamp or prior))
        conn.commit()
    return {"login":login,"server":server,"label":label,
            "login_requested_at":timestamp or prior, "connected":False,
            "verified":False,"orders_enabled":False}

def delete_profile(login, server):
    login, server,_=validate(login,server)
    with open_db() as conn:
        row=conn.execute("DELETE FROM profiles WHERE login=? AND server=?",(login,server))
        conn.commit()
        return bool(row.rowcount)

