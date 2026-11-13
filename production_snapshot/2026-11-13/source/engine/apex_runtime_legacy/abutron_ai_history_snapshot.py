#!/usr/bin/env python3
"""Isolated SQLite snapshot for read-only ABUTRON AI analysis.

Copies committed broker candle history using SQLite backup() to a standalone
immutable-compatible file. Never imports or writes any broker order modules,
account credentials, EAs, or live history source.
"""
from __future__ import annotations
import datetime
import json
import os
import sqlite3
import tempfile
from pathlib import Path

SOURCE=Path('/var/lib/apex/precision-history/closed-candles.sqlite3')
DEST=Path('/var/lib/apex/precision-history-ai-snapshot/closed-candles.sqlite3')
MAX_SOURCE_BYTES=100_000_000


def snapshot(source=SOURCE,dest=DEST):
    if (source.is_symlink() or not source.is_file() or
        source.stat().st_size>MAX_SOURCE_BYTES or dest.is_symlink()):
        raise ValueError('HISTORICAL_SOURCE_OR_DESTINATION_INVALID')
    if not dest.parent.is_dir() or dest.parent.is_symlink():
        raise ValueError('SNAPSHOT_DIRECTORY_NOT_READY')
    # The collector is free to append while this read transaction runs.
    src=sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True,timeout=5)
    tmp=None
    try:
        src.execute('PRAGMA query_only=ON')
        if src.execute('PRAGMA quick_check').fetchone()!=('ok',):
            raise ValueError('SOURCE_HISTORY_CORRUPTION')
        fd,tmp=tempfile.mkstemp(prefix='.new-ai-history-',suffix='.sqlite3',dir=dest.parent)
        os.close(fd)
        copied=sqlite3.connect(tmp,timeout=5)
        try:
            src.backup(copied,pages=100,sleep=0.02)
            copied.execute('PRAGMA journal_mode=DELETE')
            if copied.execute('PRAGMA quick_check').fetchone()!=('ok',):
                raise ValueError('BACKUP_HISTORY_CORRUPTION')
            count=copied.execute('SELECT COUNT(*) FROM candles').fetchone()[0]
            symbols=copied.execute('SELECT COUNT(DISTINCT symbol) FROM candles').fetchone()[0]
            frames=copied.execute('SELECT COUNT(DISTINCT timeframe) FROM candles').fetchone()[0]
            assert count>5000 and symbols==13 and frames==6
        finally:
            copied.close()
        os.chmod(tmp,0o640)
        with open(tmp,'rb') as f:os.fsync(f.fileno())
        os.replace(tmp,dest)
        tmp=None
        directory_fd=os.open(dest.parent,os.O_RDONLY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
        return {'status':'OK','candles':count,'symbols':symbols,'frames':frames,
            'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'destination':str(dest),'execution_modified':False}
    finally:
        src.close()
        if tmp and os.path.exists(tmp):os.unlink(tmp)


if __name__=='__main__':
    print(json.dumps(snapshot()),flush=True)
