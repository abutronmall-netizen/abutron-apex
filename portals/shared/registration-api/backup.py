#!/usr/bin/env python3
"""Local-only consistent SQLite backup of APEX signup; not an offsite backup."""
import datetime as dt
import os
from pathlib import Path
import sqlite3

SRC=Path("/var/lib/apex-signup/accounts.sqlite3")
DEST=Path("/var/backups/apex-signup")
DEST.mkdir(parents=True,exist_ok=True,mode=0o700)
DEST.chmod(0o700)
name="signup-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".sqlite3"
temp=DEST/(name+".tmp")
final=DEST/name
if temp.exists():temp.unlink()
with sqlite3.connect(f"file:{SRC}?mode=ro",uri=True) as source:
    with sqlite3.connect(temp) as target:
        source.backup(target)
        result=target.execute("PRAGMA integrity_check").fetchone()[0]
        if result!="ok":raise RuntimeError("Backup integrity check failed: "+result)
os.chmod(temp,0o600)
os.replace(temp,final)
cutoff=dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=14)
for old in DEST.glob("signup-*.sqlite3"):
    if dt.datetime.fromtimestamp(old.stat().st_mtime,dt.timezone.utc)<cutoff:
        old.unlink()
print("Local APEX registration backup created and verified:",final,"bytes:",final.stat().st_size)
