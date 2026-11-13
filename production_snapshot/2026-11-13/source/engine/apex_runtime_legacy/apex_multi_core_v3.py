"""APEX DEMO v3: pure multi-position ledger/recovery logic. No broker sends.

Fail closed on unresolved submissions, missing SL/TP, mismatched volume,
or off-ledger APEX positions. Supports one concurrent position per symbol.
"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

ACTIVE = ("PENDING","UNKNOWN","UNPROTECTED","OPEN_PROTECTED")
UNCERTAIN = ("PENDING","UNKNOWN","UNPROTECTED")

class ReconcileError(RuntimeError):
    pass

def position_direction(mt5, position):
    return "BUY" if int(position.type)==int(mt5.POSITION_TYPE_BUY) else "SELL" if int(position.type)==int(mt5.POSITION_TYPE_SELL) else "UNKNOWN"

def reconcile_all(conn, mt5, magic, mark, now=None):
    now=now or datetime.now(timezone.utc)
    positions=mt5.positions_get()
    orders=mt5.orders_get()
    if positions is None or orders is None:
        raise ReconcileError("BROKER_POSITIONS_OR_ORDERS_UNAVAILABLE")
    positions=list(positions)
    orders=list(orders)
    rows=conn.execute("""SELECT signal_key,created_utc,symbol,side,state,
                            request_json,broker_order,broker_deal
                         FROM attempts WHERE state IN
                         ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED')""").fetchall()
    if any(r[4] in UNCERTAIN for r in rows):
        raise ReconcileError("UNRESOLVED_BROKER_SUBMISSION_REQUIRES_REVIEW")
    if len(rows)>13:
        raise ReconcileError("MORE_THAN_13_ACTIVE_LEDGER_POSITIONS")
    if len(positions)>13:
        raise ReconcileError("MORE_THAN_13_ACCOUNT_POSITIONS")
    keys=set()
    for key,created,symbol,side,state,raw,ticket,deal in rows:
        if symbol in keys:
            raise ReconcileError("DUPLICATE_ACTIVE_SYMBOL_IN_LEDGER")
        keys.add(symbol)
        if state!="OPEN_PROTECTED" or ticket is None:
            raise ReconcileError("BAD_LEDGER_STATE")
        matches=[p for p in positions if int(p.ticket)==int(ticket)]
        if matches:
            if len(matches)!=1:
                raise ReconcileError("DUPLICATE_BROKER_TICKET")
            p=matches[0]
            try: req=json.loads(raw)
            except Exception:raise ReconcileError("INVALID_LEDGER_ORDER_REQUEST")
            if (int(p.magic)!=int(magic) or str(p.symbol)!=symbol
                or position_direction(mt5,p)!=side):
                raise ReconcileError("BROKER_POSITION_IDENTITY_MISMATCH")
            if float(p.sl)<=0 or float(p.tp)<=0:
                raise ReconcileError("APEX_POSITION_MISSING_SL_TP")
            if (abs(float(p.volume)-float(req["volume"]))>1e-7
                or abs(float(p.sl)-float(req["sl"]))>0.000001
                or abs(float(p.tp)-float(req["tp"]))>0.000001):
                raise ReconcileError("BROKER_POSITION_TERMS_CHANGED")
        else:
            try: created_dt=datetime.fromisoformat(created)
            except ValueError:raise ReconcileError("LEDGER_TIMESTAMP_INVALID")
            if created_dt.tzinfo is None:
                raise ReconcileError("LEDGER_TIMESTAMP_WITHOUT_TZ")
            history=mt5.history_deals_get(created_dt-timedelta(minutes=5),now)
            if history is None:
                raise ReconcileError("BROKER_CLOSE_HISTORY_UNAVAILABLE")
            # A confirmed full exit is required. A partial exit remains unresolved.
            exits=[h for h in history
                   if int(h.position_id)==int(ticket)
                   and int(h.entry) in (mt5.DEAL_ENTRY_OUT,mt5.DEAL_ENTRY_INOUT,mt5.DEAL_ENTRY_OUT_BY)]
            try: requested=float(json.loads(raw)["volume"])
            except (KeyError,ValueError,TypeError):
                raise ReconcileError("LEDGER_VOLUME_UNAVAILABLE")
            if not exits or sum(float(h.volume) for h in exits)<requested-1e-7:
                raise ReconcileError("POSITION_MISSING_WITHOUT_FULL_CLOSE")
            mark(conn,key,"CLOSED",order=ticket,deal=deal)
    active_tickets={int(r[6]) for r in rows}
    for p in positions:
        if int(p.magic)==int(magic) and int(p.ticket) not in active_tickets:
            raise ReconcileError("OFF_LEDGER_APEX_BROKER_POSITION")
    return {"broker_positions":positions,
            "open_apex_positions":[p for p in positions if int(p.magic)==int(magic)],
            "open_symbols":set(str(p.symbol) for p in positions),
            "reconciled_closed":sum(1 for r in rows if int(r[6]) not in {int(p.ticket) for p in positions})}

def reserve_symbol(conn,candidate,request):
    """Durable atomic reservation. Blocks same symbol, duplicate signal, uncertain global state."""
    symbol=candidate["symbol"]
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute(
            "SELECT 1 FROM attempts WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED') LIMIT 1"
        ).fetchone():
            raise ReconcileError("UNCERTAIN_BROKER_ORDER_GLOBAL_LOCK")
        if conn.execute("SELECT 1 FROM attempts WHERE signal_key=?",(candidate["signal_key"],)).fetchone():
            raise ReconcileError("DUPLICATE_M5_SIGNAL")
        if conn.execute(
            "SELECT 1 FROM attempts WHERE symbol=? AND state='OPEN_PROTECTED' LIMIT 1",(symbol,)
        ).fetchone():
            raise ReconcileError("SYMBOL_ALREADY_OPEN")
        conn.execute("""INSERT INTO attempts
            (signal_key,created_utc,symbol,side,state,request_json)
            VALUES (?,?,?,?,?,?)""",
            (candidate["signal_key"],datetime.now(timezone.utc).isoformat(),
             symbol,candidate["side"],"PENDING",json.dumps(request,sort_keys=True)))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise

def install_symbol_unique_index(conn):
    # Backstop independent of application logic (survives process restarts).
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS apex_one_open_attempt_per_symbol_v3
                    ON attempts(symbol)
                    WHERE state IN ('PENDING','UNKNOWN','UNPROTECTED','OPEN_PROTECTED')""")
