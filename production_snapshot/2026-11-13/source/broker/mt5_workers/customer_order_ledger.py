#!/usr/bin/env python3
"""APEX customer DEMO broker attempt ledger. No MT5 access or order-sending.

All transitions use SQLite FULL durability and immediate write locks.
Unknown broker outcomes cannot be retried. Terminal, broker, customer, signal,
position and native SL/TP identities remain bound in the ledger.
"""
from __future__ import annotations
import sqlite3,datetime,re,math,hashlib
from pathlib import Path
DB=Path("/var/lib/apex-client-feed/execution-ledger.sqlite3")
HEX=re.compile(r"^[a-f0-9]{32}$")
SYMBOLS={
 "Volatility 10 Index.0","Volatility 25 Index.0","Volatility 50 Index.0",
 "Volatility 75 Index.0","Volatility 100 Index.0",
 "Crash 150 Index.0","Crash 300 Index.0","Crash 600 Index.0","Crash 1000 Index.0",
 "Boom 150 Index.0","Boom 300 Index.0","Boom 600 Index.0","Boom 1000 Index.0"}
ACTIVE=("RESERVED","SUBMISSION_UNKNOWN","BROKER_ACK_UNRECONCILED",
        "OPEN_PROTECTED","UNPROTECTED")
class Blocked(RuntimeError):pass
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def expected_key(owner,cid,symbol,bar,side):
 return hashlib.sha256((owner+"|"+cid+"|"+symbol+"|M5|"+str(bar)+"|"+side).encode()).hexdigest()
def new(path=DB):
 path=Path(path)
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 c=sqlite3.connect(str(path),timeout=15,isolation_level=None)
 c.execute("PRAGMA journal_mode=WAL")
 c.execute("PRAGMA synchronous=FULL")
 c.execute("PRAGMA busy_timeout=15000")
 c.executescript("""CREATE TABLE IF NOT EXISTS attempts(
  signal_key TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  connection_id TEXT NOT NULL,
  broker TEXT NOT NULL CHECK(broker='Deriv'),
  environment TEXT NOT NULL CHECK(environment='DEMO'),
  broker_server TEXT NOT NULL CHECK(broker_server='Deriv-Demo'),
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  m5_bar_time INTEGER NOT NULL,
  state TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  volume REAL,entry_price REAL,stop_loss REAL,take_profit REAL,
  buffered_loss_usd REAL,
  broker_order INTEGER,broker_deal INTEGER,broker_position INTEGER,
  reason TEXT,
  UNIQUE(connection_id,symbol,m5_bar_time)
 );
 CREATE INDEX IF NOT EXISTS attempts_customer_active ON attempts(connection_id,state);
 CREATE INDEX IF NOT EXISTS attempts_customer_position ON attempts(connection_id,broker_position);""")
 return c
def valid_id(v):return isinstance(v,str) and bool(HEX.fullmatch(v))
def reserve(c,owner,cid,symbol,side,bar,key,proof):
 if not valid_id(owner) or not valid_id(cid) or symbol not in SYMBOLS or side not in ("BUY","SELL"):
  raise Blocked("BAD_CUSTOMER_OR_SYMBOL")
 if type(bar)!=int or type(key)!=str or key!=expected_key(owner,cid,symbol,bar,side):
  raise Blocked("SIGNAL_IDENTITY_MISMATCH")
 if proof.get("broker")!="Deriv" or proof.get("environment")!="DEMO" or proof.get("server")!="Deriv-Demo":
  raise Blocked("BROKER_ENVIRONMENT_NOT_APPROVED")
 if proof.get("current_broker_identity_verified") is not True:
  raise Blocked("BROKER_ACCOUNT_IDENTITY_UNVERIFIED")
 occupied=proof.get("occupied_symbols")
 if (type(proof.get("open_positions")) is not int or
     not 0<=proof["open_positions"]<13 or
     type(proof.get("pending_orders")) is not int or proof["pending_orders"]!=0 or
     proof.get("protected_positions_reconciled") is not True or
     not isinstance(occupied,list) or len(set(occupied))!=len(occupied) or
     len(occupied)!=proof["open_positions"] or
     any(x not in SYMBOLS for x in occupied) or symbol in occupied):
  raise Blocked("PORTFOLIO_SYMBOL_CAPACITY_OR_PROTECTION_UNVERIFIED")
 if proof.get("risk_governor_approved") is not True or proof.get("account_trade_authorized") is not True:
  raise Blocked("RISK_OR_ACCOUNT_AUTHORIZATION_MISSING")
 if proof.get("single_writer_approved") is not True:
  raise Blocked("EXCLUSIVE_EXECUTION_OWNERSHIP_UNVERIFIED")
 now=datetime.datetime.now(datetime.timezone.utc).timestamp()
 if not 0<=now-(bar+300)<=240:
  raise Blocked("STALE_OR_FUTURE_BAR")
 stamp=utc()
 c.execute("BEGIN IMMEDIATE")
 try:
  if c.execute("SELECT count(*) FROM attempts WHERE signal_key=?",(key,)).fetchone()[0]:
   raise Blocked("SIGNAL_ALREADY_RECORDED")
  if c.execute("""SELECT count(*) FROM attempts WHERE connection_id=? AND
    symbol=? AND state IN ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED',
                           'OPEN_PROTECTED','UNPROTECTED')""",(cid,symbol)).fetchone()[0]:
   raise Blocked("SYMBOL_ATTEMPT_NOT_RECONCILED")
  c.execute("""INSERT INTO attempts(signal_key,owner,connection_id,broker,environment,
    broker_server,symbol,side,m5_bar_time,state,created_at_utc,updated_at_utc)
    VALUES(?,?,?,'Deriv','DEMO','Deriv-Demo',?,?,?,'RESERVED',?,?)""",
    (key,owner,cid,symbol,side,bar,stamp,stamp))
  c.execute("COMMIT")
 except Exception:
  c.execute("ROLLBACK");raise
 return key
def submit_pending(c,key,volume,entry,sl,tp,loss):
 numeric=(volume,entry,sl,tp,loss)
 if not all(type(v) in (float,int) and math.isfinite(v) and v>0 for v in numeric):
  raise Blocked("UNPROTECTED_OR_INVALID_BROKER_REQUEST")
 if (entry<=sl or tp<=entry) and (sl<=entry or entry<=tp):
  raise Blocked("INVALID_STOP_TAKE_PROFIT_GEOMETRY")
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT state,side FROM attempts WHERE signal_key=?",(key,)).fetchone()
  if not row or row[0]!="RESERVED":raise Blocked("LEDGER_NOT_RESERVED")
  if row[1]=="BUY" and not (sl<entry<tp):raise Blocked("INVALID_BUY_STOPS")
  if row[1]=="SELL" and not (tp<entry<sl):raise Blocked("INVALID_SELL_STOPS")
  c.execute("""UPDATE attempts SET state='SUBMISSION_UNKNOWN',volume=?,entry_price=?,
       stop_loss=?,take_profit=?,buffered_loss_usd=?,updated_at_utc=?
       WHERE signal_key=?""",(*numeric,utc(),key))
  c.execute("COMMIT")
 except Exception:c.execute("ROLLBACK");raise
def broker_ack(c,key,order,deal):
 if type(order)!=int or order<=0 or type(deal)!=int or deal<=0:
  raise Blocked("BROKER_ACK_MISSING_IDENTIFIERS")
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT state FROM attempts WHERE signal_key=?",(key,)).fetchone()
  if not row or row[0]!="SUBMISSION_UNKNOWN":raise Blocked("NOT_IN_UNKNOWN_BROKER_STATE")
  c.execute("""UPDATE attempts SET state='BROKER_ACK_UNRECONCILED',broker_order=?,
    broker_deal=?,updated_at_utc=? WHERE signal_key=?""",(order,deal,utc(),key))
  c.execute("COMMIT")
 except Exception:c.execute("ROLLBACK");raise
def confirm_position(c,key,position,sl,tp,account_match,broker_verified):
 if type(position)!=int or position<=0:raise Blocked("BROKER_POSITION_ID_INVALID")
 if not (account_match is True and broker_verified is True):
  raise Blocked("BROKER_PROOF_NOT_MATCHED")
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT state,stop_loss,take_profit FROM attempts WHERE signal_key=?",(key,)).fetchone()
  if not row or row[0]!="BROKER_ACK_UNRECONCILED":raise Blocked("BROKER_ACK_NOT_RECONCILED")
  state="OPEN_PROTECTED" if (isinstance(sl,(float,int)) and isinstance(tp,(float,int))
    and abs(sl-row[1])<=0.00000001 and abs(tp-row[2])<=0.00000001) else "UNPROTECTED"
  c.execute("""UPDATE attempts SET state=?,broker_position=?,updated_at_utc=?,
    reason=? WHERE signal_key=?""",(state,position,utc(),
    "BROKER_NATIVE_SL_TP_NOT_CONFIRMED" if state=="UNPROTECTED" else None,key))
  c.execute("COMMIT")
 except Exception:c.execute("ROLLBACK");raise
 if state=="UNPROTECTED":raise Blocked("EMERGENCY_UNPROTECTED_BROKER_POSITION")
 return state
def closed(c,key,position,exit_deal,broker_position_absent):
 if type(position)!=int or position<=0 or type(exit_deal)!=int or exit_deal<=0 or broker_position_absent is not True:
  raise Blocked("BROKER_CLOSURE_NOT_RECONCILED")
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT state,broker_position FROM attempts WHERE signal_key=?",(key,)).fetchone()
  if not row or row[0] not in ("OPEN_PROTECTED","UNPROTECTED") or row[1]!=position:
   raise Blocked("CANNOT_CLOSE_UNVERIFIED_POSITION")
  c.execute("""UPDATE attempts SET state='CLOSED_RECONCILED',updated_at_utc=?,
    reason='CLOSED_BROKER_VERIFIED' WHERE signal_key=?""",(utc(),key))
  c.execute("COMMIT")
 except Exception:c.execute("ROLLBACK");raise
def unresolved(c):
 return c.execute("""SELECT connection_id,signal_key,symbol,state,broker_order,
  broker_deal,broker_position FROM attempts
  WHERE state IN ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED',
                   'OPEN_PROTECTED','UNPROTECTED') ORDER BY created_at_utc""").fetchall()


def queue_native_usd_pending(c,key,volume,stop_usd=50.0,target_usd=100.0):
 """Durably mark UNKNOWN before writing a one-shot native MT5 order command.

 Broker prices are intentionally not fabricated. They must later be obtained
 from a fresh broker order/position receipt before protection can be certified.
 """
 if not isinstance(key,str) or not re.fullmatch(r"[a-f0-9]{64}",key) or not isinstance(volume,(int,float)) or not math.isfinite(volume) or volume<=0:
  raise Blocked("INVALID_NATIVE_ORDER_INTENT")
 if stop_usd!=50.0 or target_usd!=100.0:
  raise Blocked("NATIVE_FIXED_USD_POLICY_MISMATCH")
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT state FROM attempts WHERE signal_key=?",(key,)).fetchone()
  if not row or row[0]!="RESERVED":raise Blocked("NATIVE_SIGNAL_NOT_RESERVED")
  c.execute("""UPDATE attempts SET state='SUBMISSION_UNKNOWN',volume=?,
    buffered_loss_usd=?,reason='NATIVE_ONE_SHOT_REQUEST_MAY_HAVE_BEEN_SENT',
    updated_at_utc=? WHERE signal_key=?""",
    (float(volume),stop_usd,utc(),key))
  c.execute("COMMIT")
 except Exception:
  c.execute("ROLLBACK");raise


def queue_native_adaptive_pending(c,key,equity_usd,risk_ceiling_pct=0.10):
    """Versioned, durable UNKNOWN state BEFORE native V2 request publication.

    Exact broker lot, entry and SL/TP are unknown until the native EA calculates
    them and a broker-acknowledged position is independently reconciled.
    One signal can never be resubmitted after a crash or uncertain result.
    """
    if not isinstance(key,str) or not re.fullmatch(r"[a-f0-9]{64}",key):
        raise Blocked("ADAPTIVE_INVALID_SIGNAL_KEY")
    if (type(equity_usd) not in (int,float) or not math.isfinite(equity_usd)
        or equity_usd<=0 or risk_ceiling_pct!=0.10):
        raise Blocked("ADAPTIVE_EQUITY_OR_RISK_POLICY_INVALID")
    planned_risk=round(equity_usd*.001,6)
    if planned_risk<=0:raise Blocked("ADAPTIVE_ZERO_RISK_BUDGET")
    c.execute("BEGIN IMMEDIATE")
    try:
        row=c.execute("SELECT state FROM attempts WHERE signal_key=?",(key,)).fetchone()
        if row!=('RESERVED',):
            raise Blocked("ADAPTIVE_SIGNAL_NOT_RESERVED_OR_ALREADY_SENT")
        updated=c.execute("""UPDATE attempts SET state='SUBMISSION_UNKNOWN',
          volume=NULL,entry_price=NULL,stop_loss=NULL,take_profit=NULL,
          buffered_loss_usd=?,
          reason='NATIVE_ADAPTIVE_V2_ONE_SHOT_REQUEST_MAY_HAVE_BEEN_SENT',
          updated_at_utc=?
          WHERE signal_key=? AND state='RESERVED'""",
          (planned_risk,utc(),key))
        if updated.rowcount!=1:raise Blocked("ADAPTIVE_LEDGER_STATE_CONFLICT")
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise

def broker_rejection(c,key,reason):
 """Record exact matching native EA BLOCKED receipt, never treat as fill."""
 if not isinstance(reason,str) or not reason or len(reason)>120:raise Blocked("INVALID_BROKER_REJECTION")
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT state FROM attempts WHERE signal_key=?",(key,)).fetchone()
  if not row or row[0]!="SUBMISSION_UNKNOWN":raise Blocked("NOT_AWAITING_BROKER_RESPONSE")
  c.execute("UPDATE attempts SET state='BROKER_DENIED_NO_FILL',reason=?,updated_at_utc=? WHERE signal_key=?",
    (reason,utc(),key))
  c.execute("COMMIT")
 except Exception:
  c.execute("ROLLBACK");raise
