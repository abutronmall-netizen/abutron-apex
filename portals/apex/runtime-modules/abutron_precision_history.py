#!/usr/bin/env python3
"""Current ABUTRON APEX: broker-native candle history, isolated and read-only.

Reads existing authoritative completed-candle snapshot and adds unseen immutable
candles to a private SQLite DB. NEVER imports or calls broker order modules.
Does not alter signal, native feed, EA, ledger, portal or account settings.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/opt/apex/runtime")
from apex_fast_scanner import validate_snapshot, EXPECTED, FRAMES, utc_now

SOURCE=Path("/var/lib/apex/operator-live/native-market.json")
DEST=Path("/var/lib/apex/precision-history/closed-candles.sqlite3")
MAX_BYTES=250_000_000
def collect(source:Path=SOURCE,dest:Path=DEST)->dict:
    if source.is_symlink() or not source.is_file() or source.stat().st_size>8_000_000:
        raise ValueError("BROKER_INPUT_MISSING_UNSAFE_OR_OVERSIZED")
    raw=source.read_bytes()
    snap=json.loads(raw)
    verified=validate_snapshot(snap,utc_now())
    dest.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    if dest.is_symlink() or (dest.exists() and dest.stat().st_size>MAX_BYTES):
        raise ValueError("HISTORY_STORAGE_UNSAFE_OR_OVER_LIMIT")
    count=0
    con=sqlite3.connect(str(dest),timeout=3,isolation_level=None)
    try:
        con.execute("PRAGMA busy_timeout=3000")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("""CREATE TABLE IF NOT EXISTS candles(
             symbol TEXT NOT NULL,
             timeframe TEXT NOT NULL,
             start_time_utc INTEGER NOT NULL,
             open REAL NOT NULL, high REAL NOT NULL,
             low REAL NOT NULL, close REAL NOT NULL,
             PRIMARY KEY(symbol,timeframe,start_time_utc)
        ) WITHOUT ROWID""")
        con.execute("""CREATE TABLE IF NOT EXISTS imports(
             sha256 TEXT PRIMARY KEY, imported_at_utc TEXT NOT NULL,
             broker_generated_at_utc TEXT NOT NULL,
             candles_added INTEGER NOT NULL
        )""")
        checksum=hashlib.sha256(raw).hexdigest()
        rows=[]
        for symbol in EXPECTED:
            for timeframe in FRAMES:
                for bar in verified[symbol][timeframe]:
                    rows.append((symbol,timeframe,int(bar["time"]),
                                 float(bar["open"]),float(bar["high"]),
                                 float(bar["low"]),float(bar["close"])))
        con.execute("BEGIN IMMEDIATE")
        n0=con.total_changes
        con.executemany("""INSERT OR IGNORE INTO candles
           (symbol,timeframe,start_time_utc,open,high,low,close)
           VALUES(?,?,?,?,?,?,?)""",rows)
        count=con.total_changes-n0
        con.execute("""INSERT OR IGNORE INTO imports
           (sha256,imported_at_utc,broker_generated_at_utc,candles_added)
           VALUES(?,?,?,?)""",(checksum,dt.datetime.now(dt.timezone.utc).isoformat(),
                               snap["generated_at_utc"],count))
        con.execute("COMMIT")
        assert con.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        total=con.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        return {"state":"OK","symbols":13,"timeframes":6,
                "snapshot_candles":len(rows),"new_candles":count,
                "retained_candles":total}
    except Exception:
        if con.in_transaction:con.execute("ROLLBACK")
        raise
    finally:con.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,default=SOURCE)
    ap.add_argument("--db",type=Path,default=DEST)
    args=ap.parse_args()
    print(json.dumps(collect(args.source,args.db),sort_keys=True),flush=True)
