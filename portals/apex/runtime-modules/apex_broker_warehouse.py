"""APEX durable warehouse for official, completed Deriv MT5 broker candles.

Idempotent SQLite ingest. Never fabricates data or revises an existing closed
bar silently; conflicting broker history is recorded as a quality incident.
No account data, trading credentials, order sends or paid APIs.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
from apex_fast_scanner import validate_snapshot

SOURCE=Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")
ROOT=Path("/var/lib/apex/warehouse")
DB=ROOT/"deriv_broker_candles.sqlite"
STATUS=ROOT/"latest.json"


def connect(path=DB):
    path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(path),timeout=30,isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("""CREATE TABLE IF NOT EXISTS bars (
       symbol TEXT NOT NULL, timeframe TEXT NOT NULL, time INTEGER NOT NULL,
       open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
       volume INTEGER NOT NULL, broker_source TEXT NOT NULL,
       first_seen_utc TEXT NOT NULL,
       PRIMARY KEY(symbol,timeframe,time))""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_bars_symbol_frame
                 ON bars(symbol,timeframe,time)""")
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots(
       sha256 TEXT PRIMARY KEY, generated_at_utc TEXT NOT NULL,
       ingested_at_utc TEXT NOT NULL, inserted_bars INTEGER NOT NULL,
       corrected_or_conflicting_bars INTEGER NOT NULL, total_bars INTEGER NOT NULL)""")
    return c


def ingest(c,doc,now=None):
    now=now or datetime.now(timezone.utc)
    records=validate_snapshot(doc,now)
    raw=json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    digest=hashlib.sha256(raw).hexdigest()
    stamp=now.isoformat()
    new_bars=0
    conflicts=[]
    c.execute("BEGIN IMMEDIATE")
    try:
        for symbol,frames in records.items():
            for frame,bars in frames.items():
                for bar in bars:
                    t=int(bar["time"])
                    original=c.execute("SELECT open,high,low,close,volume FROM bars WHERE symbol=? AND timeframe=? AND time=?",(symbol,frame,t)).fetchone()
                    metrics=(float(bar["open"]),float(bar["high"]),float(bar["low"]),float(bar["close"]),int(bar["volume"]))
                    if original is not None:
                        if tuple(original)!=metrics:
                            conflicts.append({"symbol":symbol,"frame":frame,"time":t})
                        continue
                    c.execute("""INSERT INTO bars(symbol,timeframe,time,open,high,low,close,volume,broker_source,first_seen_utc)
                      VALUES (?,?,?,?,?,?,?,?,?,?)""",(symbol,frame,t,*metrics,"Deriv DEMO MT5",stamp))
                    new_bars+=1
        total=c.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
        c.execute("""INSERT OR IGNORE INTO snapshots
          (sha256,generated_at_utc,ingested_at_utc,inserted_bars,corrected_or_conflicting_bars,total_bars)
          VALUES (?,?,?,?,?,?)""",(digest,doc["generated_at_utc"],stamp,new_bars,len(conflicts),total))
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise
    return {"schema":"apex.broker.warehouse.v1","generated_at_utc":stamp,
        "source":"Deriv DEMO MT5","status":"CONFLICT" if conflicts else "OK",
        "source_snapshot_utc":doc["generated_at_utc"],"source_sha256":digest,
        "new_bars":new_bars,"total_bars":total,
        "conflicting_bar_count":len(conflicts),
        "conflicts":conflicts[:25],
        "execution_authorized":False,"orders_placed":0}


def atomic_status(path,doc):
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".warehouse.")
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump(doc,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    doc=json.loads(SOURCE.read_text(encoding="utf8"))
    db=connect()
    try:
        result=ingest(db,doc)
        atomic_status(STATUS,result)
        print(json.dumps({k:result[k] for k in ("status","new_bars","total_bars","conflicting_bar_count","orders_placed")}),flush=True)
        if result["status"]!="OK":raise SystemExit(2)
    finally:db.close()


if __name__=="__main__":
    main()
