"""Read-only broker-history evaluation input; NEVER a live-feed substitute.

Requires externally retained immutable source and separate attestation manifest.
No attempt to join disconnected archives to live candle sessions.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, math, os, sqlite3, stat
from pathlib import Path
from .production_contracts import BrokerBoundBars, FeedRefused, DERIV_ALLOWED, _closed


@dataclass(frozen=True)
class HistorySegment:
    symbol: str
    first_open: int
    last_open: int
    bars: int
    gaps_before: int
    account_suffix: str
    source_kind: str = 'broker_copyrates_readonly_archive'


def _read_proof(path: Path) -> dict:
    path=Path(path)
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size <= 50 or st.st_size > 200_000:
        raise FeedRefused('BROKER_HISTORY_PROOF_INVALID')
    try:
        doc=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError):
        raise FeedRefused('BROKER_HISTORY_PROOF_UNREADABLE') from None
    required={'source':'DERIV_DEMO_MT5_READONLY_COPYRATES', 'status':'VERIFIED_RESEARCH_ONLY',
              'session_nonce_matched':True,'orders_submitted':0,
              'account_switches_modified':False,'positions_modified':False,
              'overlap_mismatches':0}
    for k,v in required.items():
        if doc.get(k)!=v:
            raise FeedRefused('BROKER_HISTORY_PROVENANCE_UNVERIFIED')
    if not isinstance(doc.get('source_sha256'),str) or len(doc['source_sha256']) != 64:
        raise FeedRefused('BROKER_HISTORY_SOURCE_HASH_MISSING')
    if doc.get('source_account_suffix') != '6207':
        raise FeedRefused('BROKER_HISTORY_ACCOUNT_NOT_ATTESTED')
    return doc


def load_deriv_archive_segments(*, database: Path, proof_file: Path,
                                symbol: str, connection_id: str,
                                max_rows: int = 100_000) -> tuple[HistorySegment,...]:
    """Extract contiguous M5 windows; refuse unproven broker-history sources.

    Validates *file provenance* based on a pre-existing trusted export manifest.
    Does not independently communicate with or authenticate the MT5 broker.
    """
    if symbol not in DERIV_ALLOWED or max_rows < 1 or max_rows > 100_000:
        raise FeedRefused('UNAPPROVED_HISTORY_SCOPE')
    proof=_read_proof(proof_file)
    if not isinstance(connection_id,str) or len(connection_id)!=32 or any(c not in '0123456789abcdef' for c in connection_id):
        raise FeedRefused('INVALID_CONNECTION_ID')
    f=Path(database)
    st=f.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size < 8192 or st.st_size > 200_000_000:
        raise FeedRefused('UNSAFE_HISTORY_DATABASE')
    # The hash in the original manifest is for the raw authenticated MQL5 export,
    # not the derived SQLite DB. Never falsely equate the two.
    uri=f.resolve().as_uri()+'?mode=ro&immutable=1'
    db=sqlite3.connect(uri,uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != {'candles'}:
            raise FeedRefused('UNEXPECTED_HISTORY_TABLES')
        schema=[x[1] for x in db.execute('PRAGMA table_info(candles)')]
        expected=['symbol','timeframe','start_time_utc','open','high','low','close']
        if schema!=expected:
            raise FeedRefused('HISTORY_SCHEMA_CHANGED')
        data=db.execute('''SELECT start_time_utc,open,high,low,close FROM candles
          WHERE symbol=? AND timeframe='M5' ORDER BY start_time_utc ASC LIMIT ?''',
          (symbol,max_rows+1)).fetchall()
    finally:
        db.close()
    if len(data)>max_rows or not data:
        raise FeedRefused('HISTORY_LENGTH_INVALID')
    gaps=0;group_start=0;segments=[];previous=None
    # Verify geometry, close order, no impossible timestamps.
    for i,(ts,o,h,l,c) in enumerate(data):
        ts=int(ts)
        _closed(symbol,ts,o,h,l,c,captured_at=ts+300,historical=True)
        if previous is not None:
            diff=ts-previous
            if diff<=0 or diff%300:
                raise FeedRefused('HISTORY_SORT_OR_ALIGNMENT_INVALID')
            if diff!=300:
                segments.append(HistorySegment(symbol,data[group_start][0],previous,i-group_start,gaps,
                                               proof['source_account_suffix']))
                group_start=i;gaps+=1
        previous=ts
    segments.append(HistorySegment(symbol,data[group_start][0],previous,len(data)-group_start,gaps,
                                   proof['source_account_suffix']))
    return tuple(segments)


def archive_warmup_readiness(segments: tuple[HistorySegment,...], *, warmup_bars:int=0)->dict:
    if warmup_bars<0: raise FeedRefused('INVALID_WARMUP')
    viable=[s for s in segments if s.bars >= warmup_bars+1]
    return {'history_available_for_historical_replay':bool(viable),
            'longest_contiguous_m5':max((s.bars for s in segments),default=0),
            'segments':len(segments),'eligible_segments':len(viable),
            'live_warmup_proven':False,
            'warning':'Historical research availability does not prove a continuous current live feed'}


def can_combine_archive_and_live(*, archived:tuple[dict,...],live:tuple[dict,...],
                                 archived_connection_id:str,live_connection_id:str)->dict:
    """Check overlapping candles, but do not require uninterrupted archive history.

    Retain only real candle data. Return gap metadata rather than vetoing the
    whole feed or inventing bars in missing intervals.
    """
    if archived_connection_id != live_connection_id or not archived_connection_id:
        raise FeedRefused('ARCHIVE_LIVE_ACCOUNT_MISMATCH')
    if not archived or not live:
        raise FeedRefused('NO_ARCHIVE_OR_LIVE_BARS')
    amap={b['ts']:b for b in archived};lmap={b['ts']:b for b in live}
    if len(amap)!=len(archived) or len(lmap)!=len(live):
        raise FeedRefused('DUPLICATE_CANDLE_TIMESTAMP')
    overlap=sorted(set(amap)&set(lmap))
    for ts in overlap:
        if any(not math.isclose(float(amap[ts][field]),float(lmap[ts][field]),
                              rel_tol=0,abs_tol=1e-8)
               for field in ('open','high','low','close')):
            raise FeedRefused('ARCHIVE_LIVE_CANDLE_MISMATCH')
    merged={**amap,**lmap}
    seq=sorted(merged)
    if any(b<=a or (b-a)%300 for a,b in zip(seq,seq[1:])):
        raise FeedRefused('UNALIGNED_HISTORY_TIMESTAMP')
    gaps=sum(b-a!=300 for a,b in zip(seq,seq[1:]))
    tail=1
    for j in range(len(seq)-1,0,-1):
        if seq[j]-seq[j-1]!=300: break
        tail+=1
    return {'bars':len(seq),'overlap_verified':len(overlap),
            'missing_interval_count':gaps,'contiguous_tail_bars':tail,
            'first_close':seq[0],'last_close':seq[-1],
            'orders_submitted':0}


def read_archive_contiguous_tail(*,database:Path,proof_file:Path,symbol:str,
                                 connection_id:str,rows_needed:int=1200)->tuple[dict,...]:
    """Return real M5 archive tail including gaps for indicator reset.

    Verify broker-export evidence and candle geometry without filling missing
    bars or imposing a continuous-history minimum.
    """
    load_deriv_archive_segments(database=database,proof_file=proof_file,
                                symbol=symbol,connection_id=connection_id)
    if rows_needed<1 or rows_needed>20000:
        raise FeedRefused('INVALID_ARCHIVED_HISTORY_REQUEST')
    src=Path(database).resolve().as_uri()+'?mode=ro&immutable=1'
    db=sqlite3.connect(src,uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        rows=db.execute("SELECT start_time_utc,open,high,low,close FROM candles "
                        "WHERE symbol=? AND timeframe='M5' "
                        "ORDER BY start_time_utc DESC LIMIT ?",(symbol,rows_needed)).fetchall()[::-1]
    finally: db.close()
    converted=tuple(_closed(symbol,int(t),o,h,l,c,captured_at=int(t)+300,historical=True)
                    for t,o,h,l,c in rows)
    if not converted or any(b['ts']<=a['ts'] or (b['ts']-a['ts'])%300
                            for a,b in zip(converted,converted[1:])):
        raise FeedRefused('ARCHIVED_HISTORY_INVALID_TIMESTAMPS')
    return converted
