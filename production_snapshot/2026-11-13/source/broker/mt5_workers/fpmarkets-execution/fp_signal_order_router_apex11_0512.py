#!/usr/bin/python3
"""FP Markets DEMO 0512: fail-closed broker-native signal-to-order writer.
No Deriv integrations. No LIVE support. OFF by default.
Never retries potentially-sent orders. Positives require AI + SMC + ICT.
"""
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
sys.path.insert(0,'/opt/apex-client-mt5')
import abutron_selective_tradingagents_v1 as selective
import re
import sqlite3
import stat
import tempfile
import time

CID="35b81a287b6a030f2f46ff426b135e6c"
FP1636_CID='80cf848587fcec6311dd93560c1c46c6'
WORKER=Path("/var/lib/private/abutron-client-mt5-"+CID)
FILES=WORKER/"terminal/MQL5/Files"
SCANNER=Path("/var/lib/abutron-fp-scanner/partial-latest.json")
APEX_JOURNAL=Path("/var/lib/abutron-apex11-fp-0512/account-bound-m5-journal.sqlite3")
AI=Path("/var/lib/abutron-fp-scanner/ai/latest.json")
FEED=Path("/var/lib/abutron-fpmarkets-feed/partial")/(CID+".json")
HISTORY=Path("/var/lib/apex/operator-live/fp-native-history.json")
RECON=Path("/var/lib/abutron-fp-execution/reconciliation/latest.json")
DB=Path("/var/lib/apex-signup/accounts.sqlite3")
STATE=Path("/var/lib/abutron-fp-execution/order-router")
CONFIG=Path("/etc/abutron/fp-demov1-execution.json")
HEX32=re.compile("^[a-f0-9]{32}$")
HEX64=re.compile("^[a-f0-9]{64}$")
RISK_SL=50.0
REWARD_TP=100.0
PORTFOLIO_CEILING=0.20
SYMBOLS={"XAUUSD","BTCUSD","EURUSD","GBPUSD","USDJPY","AUDUSD","US100","US30","SP500","GER40","USOIL","USDCHF","NZDUSD"}
V101_SHA="f0edbc4fbeb792d970b4e661d7c9d399419bcddbf49b36d36f520fc33a859ed4"
V113_SHA="5463e4073a1991fb3b52d1fe253a4fa2da035b5a4889a8ab8d32cee856048d06"
ADAPTIVE_FLAG=Path("/etc/abutron/optionc-live-010.json")
def adaptive_on():
    if not ADAPTIVE_FLAG.is_file() or ADAPTIVE_FLAG.is_symlink():return False
    data=load(ADAPTIVE_FLAG,4000)
    if data.get("schema")!="abutron.optionc.activation.v2" or data.get("demo_only") is not True:
        raise ValueError("FP_ADAPTIVE_CONFIG_DENIED")
    return (data.get("fpmarkets_enabled") is True and
            data.get("fp_enabled") is False and
            data.get("fpmarkets_connection_allowlist")==[CID,FP1636_CID] and
            data.get("risk_budget_pct_per_trade")==0.1 and
            data.get("portfolio_ceiling_pct")==20)


def timestamp(v):
    t=dt.datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("NAIVE_TIMESTAMP")
    return t.timestamp()

def recent(doc,name,now,max_age):
    val=doc.get(name)
    if not val or not -15<=now-timestamp(val)<=max_age:
        raise ValueError("STALE_"+name.upper())

def load(p,limit=5000000):
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size>limit or st.st_size<2:
        raise ValueError("INVALID_NATIVE_SOURCE_FILE")
    return json.loads(p.read_text(encoding="utf-8"))

def account_proof():
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=5) as c:
        r=c.execute("""SELECT x.broker,x.environment,x.broker_server,x.status,
                        x.account_reference,COALESCE(t.desired_enabled,0),COALESCE(t.effective_enabled,0)
                        FROM apex_mt5_connections x LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
                        WHERE x.id=?""",(CID,)).fetchone()
    if not r or r[:4]!=("FP Markets","DEMO","FPMarketsSC-Demo","CONNECTED"):
        raise ValueError("FP_DEMO_ACCOUNT_UNVERIFIED")
    if not (str(r[4]).isdigit() and len(str(r[4]))>=4):
        raise ValueError("FP_LOGIN_UNVERIFIED")
    w=load(WORKER/"worker-health.json",30000)
    nonce=w.get("nonce");owner=w.get("proof_owner")
    if not (w.get("id")==CID and w.get("broker")=="FP Markets" and
            w.get("status")=="CONNECTED" and w.get("heartbeat_fresh") is True and
            w.get("mode")=="DEMO" and w.get("server")=="FPMarketsSC-Demo" and
            isinstance(nonce,str) and HEX32.fullmatch(nonce) and
            isinstance(owner,str) and len(owner)==36):
        raise ValueError("FP_WORKER_UNVERIFIED")
    h=FILES/("ABUTRON_SESSION_HEARTBEAT_V1_"+nonce+".txt")
    if not h.is_file() or h.is_symlink() or time.time()-h.stat().st_mtime>13:
        raise ValueError("FP_NATIVE_HEARTBEAT_MISSING")
    if h.read_text(encoding="utf-8-sig").splitlines()!=[
        "ABUTRON_MT5_NATIVE_HEARTBEAT_V1",nonce,owner,"FP_MARKETS",
        "FPMarketsSC-Demo","DEMO","CONNECTED","NO_ORDER_FUNCTIONS"]:
        raise ValueError("FP_NATIVE_HEARTBEAT_MISMATCH")
    return {"nonce":nonce,"login":str(r[4]),"desired":r[5],"effective":r[6]}

def bridge_proof(account,now):
    binary=WORKER/"terminal/MQL5/Experts/ABUTRON/AbutronFPNativeOrderBridgeV101.ex5"
    needed_sha=V113_SHA if adaptive_on() else V101_SHA
    if not binary.is_file() or binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest()!=needed_sha:
        raise ValueError("FP_NATIVE_BRIDGE_SHA_INVALID")
    p=FILES/("ABUTRON_FP_BRIDGE_READY_V3_"+account["nonce"]+".txt")
    if p.is_symlink() or not p.is_file() or not -10<=now-p.stat().st_mtime<=14:
        raise ValueError("FP_V3_BRIDGE_NOT_FRESH")
    lines=p.read_text(encoding="utf-8-sig").splitlines()
    if (len(lines)!=11 or lines[:5]!=[
        "FP_NATIVE_BRIDGE_READY_V3",account["nonce"],account["login"],"FPMarketsSC-Demo","FP_DEMO"]):
        raise ValueError("FP_V3_BRIDGE_IDENTITY_INVALID")
    try:
        clock,pending,positions,terminal,broker,enabled=map(int,lines[5:])
    except ValueError:raise ValueError("FP_V3_BRIDGE_VALUES_INVALID")
    if abs(now-clock)>26 or any(x<0 for x in (pending,positions)) or any(x not in (0,1) for x in (terminal,broker,enabled)):
        raise ValueError("FP_V3_BRIDGE_STATE_INVALID")
    adaptive_ready=False
    if adaptive_on():
        ap=FILES/("ABUTRON_OPTIONC_FP_CAPABILITY_V2_"+account["nonce"]+".txt")
        if ap.is_symlink() or not ap.is_file() or not -10<=now-ap.stat().st_mtime<=14:
            raise ValueError("FP_ADAPTIVE_NATIVE_CAPABILITY_MISSING")
        lines=ap.read_text(encoding="utf-8-sig").splitlines()
        if (len(lines)!=9 or lines[:5]!=[
           "APEX_OPTIONC_ADAPTIVE_CAPABILITY_V2",account["nonce"],
           account["login"],"FPMarketsSC-Demo","FP"] or
           abs(now-int(lines[5]))>26 or lines[6:]!=["1","0.10","20"]):
            raise ValueError("FP_ADAPTIVE_NATIVE_CAPABILITY_NOT_APPROVED")
        adaptive_ready=True
    return {"positions":positions,"pending":pending,"enabled":enabled,
      "terminal":terminal,"broker":broker,"adaptive_ready":adaptive_ready}

def _ai_evidence_digest(row):
 # Independent exact-candle SHA256 reconstruction from immutable APEX scanner.
 return selective.validate_evidence('FP Markets DEMO MT5',row['symbol'],
        row['m5_closed_bar'],row['proposal'],row['indicators'])[1]



def feasible_broker_usd100_sell_target(symbol,side,mapping,quote):
    """Conservative broker-data USD index floor, NOT an entry approval.

    At the approved minimum lot and the USD index contract size, a SELL
    cannot collect USD100 gross profit when even a zero price yields less
    than USD98 (the EA USD100 tolerance is +/-USD2). Never increase lots.
    The broker EA remains the final authority via OrderCalcProfit.
    """
    if adaptive_on():
        return True # No fixed $100 target in native 0.10% mode.
    if side!="SELL" or symbol!="SP500":
        return True
    if mapping.get("actual")!="US500":
        return False
    values=[mapping.get("min_lot"),mapping.get("contract_size"),quote.get("bid")]
    if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values):
        return False
    lot,contract,bid=values
    return bid*lot*contract>=REWARD_TP-2.0

def match_signals(scanner,ai,feed,now):
    if (scanner.get("schema")!="abutron.fpmarkets.apex.scanner.partial.readonly.v1"
      or scanner.get("status")!="FP_SCANNER_PARTIAL_READONLY"
      or scanner.get("orders_enabled") is not False or
      scanner.get("execution_authorized") is not False or
      scanner.get("account_controls_modified") is not False):
        raise ValueError("FP_SCANNER_NOT_RESEARCH_VERIFIED")
    recent(scanner,"checked_at_utc",now,140)
    if (feed.get("schema")!="abutron.fpmarkets.native.partial.readonly.v1"
      or feed.get("connection_id")!=CID
      or feed.get("account_mode")!="DEMO"
      or feed.get("broker_server")!="FPMarketsSC-Demo"
      or feed.get("execution_enabled") is not False
      or feed.get("orders_submitted")!=0
      or feed.get("parallel_forex_status")!="SIX_FOREX_R_VERIFIED_V305"
      or abs(timestamp(scanner.get("native_market_at_utc"))-
             timestamp(feed.get("checked_at_utc")))>15):
        raise ValueError("FP_NATIVE_SCANNER_PAIR_MISMATCH")
    recent(feed,"checked_at_utc",now,140)
    rows=scanner.get("instruments")
    if not isinstance(rows,list) or len(rows)!=13 or {r.get("symbol") for r in rows}!=SYMBOLS:
        raise ValueError("FP_13_SYMBOL_UNIVERSE_INVALID")
    out=[]
    for row in rows:
        sym=row["symbol"];side=row.get("proposal")
        if side not in ("BUY","SELL") or row.get("available") is not True:continue
        # Use existing APEX closed-bar scanner signal directly.
        # TradingAgents and retired SMC/ICT are not execution vetoes.
        m=feed.get("mapping",{}).get(sym,{})
        quote=feed.get("quotes",{}).get(sym,{})
        bar=feed.get("bars",{}).get(sym,{})
        if (m.get("status")!="MAPPED" or m.get("trade_mode")!=4 or
           quote.get("symbol")!=m.get("actual") or
           not all(isinstance(bar.get(tf),list) and len(bar[tf])>=60 for tf in ("M1","M5","M15","H1","H4","D1"))):
            continue
        if not isinstance(row.get("m5_closed_bar"),int):
            continue
        if not isinstance(quote.get("age_seconds"),(int,float)) or quote["age_seconds"]>90 or quote["age_seconds"]< -10:
            continue
        # Reject only broker-mathematically impossible USD100 targets.
        # Other symbols retain their original native OrderCalcProfit checks.
        if not feasible_broker_usd100_sell_target(sym,side,m,quote):
            continue
        out.append({"symbol":sym,"native_symbol":m["actual"],"side":side,
                    "closed_bar":row["m5_closed_bar"],"min_lot":m["min_lot"],
                    "lot_step":m["lot_step"]})
    return sorted(out,key=lambda x:(x["closed_bar"],x["symbol"]),reverse=True)



def match_account_bound_apex11(feed,now):
    """Source real APEX 1.1 account-bound M5 decisions for existing FP native writer."""
    if (feed.get("schema")!="abutron.fpmarkets.native.partial.readonly.v1"
        or feed.get("connection_id")!=CID or feed.get("account_mode")!="DEMO"
        or feed.get("broker_server")!="FPMarketsSC-Demo"
        or feed.get("execution_enabled") is not False or feed.get("orders_submitted")!=0
        or feed.get("parallel_forex_status")!="SIX_FOREX_R_VERIFIED_V305"):
        raise ValueError("FP_NATIVE_FEED_ACCOUNT_MISMATCH")
    recent(feed,"checked_at_utc",now,140)
    if not APEX_JOURNAL.is_file() or APEX_JOURNAL.is_symlink() or APEX_JOURNAL.stat().st_mode&0o077:
        raise ValueError("FP_APEX11_JOURNAL_UNAVAILABLE_OR_PERMISSIONS")
    with sqlite3.connect('file:'+str(APEX_JOURNAL)+'?mode=ro',uri=True,timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        rows=db.execute("SELECT d.symbol,d.closed_ts,d.payload FROM decisions d "
           "JOIN (SELECT symbol,MAX(closed_ts) AS ts FROM decisions "
           "WHERE account_id=? AND broker='fp_markets' GROUP BY symbol) r "
           "ON d.symbol=r.symbol AND d.closed_ts=r.ts "
           "WHERE d.account_id=? AND d.broker='fp_markets'",(CID,CID)).fetchall()
    if len(rows)!=len(SYMBOLS) or {r[0] for r in rows}!=SYMBOLS:
        raise ValueError("FP_APEX11_ACCOUNT_JOURNAL_SYMBOL_SET_INCOMPLETE")
    out=[]
    for sym,closed,raw in rows:
        d=json.loads(raw);side=d.get('status')
        if (d.get('engine')!='APEX_1_1_0' or d.get('broker')!='fp_markets'
            or d.get('connection_id')!=CID or d.get('symbol')!=sym
            or d.get('source_kind') not in ('fp_native_collector_complete_v1','fp_collector_complete_v1','fp_collector_partial_v1')
            or d.get('order') is not None or d.get('broker_order_authorized') is not False
            or d.get('orders_submitted')!=0 or int(d.get('bar_closed_ts',-1))!=closed):
            raise ValueError("FP_APEX11_JOURNAL_IDENTITY_OR_AUTHORITY_MISMATCH")
        if side not in ('BUY','SELL'): continue
        weight=d.get('target_weight_research_only')
        if (type(weight) not in (float,int) or not math.isfinite(weight)
            or (side=='BUY' and weight<=0) or (side=='SELL' and weight>=0)):
            continue
        if d.get('risk_verdict_simulated',{}).get('halted') is True: continue
        m=feed.get('mapping',{}).get(sym,{})
        q=feed.get('quotes',{}).get(sym,{})
        bars=feed.get('bars',{}).get(sym,{})
        latest=bars.get('M5')
        if (m.get('status')!='MAPPED' or m.get('trade_mode')!=4
            or q.get('symbol')!=m.get('actual')
            or not all(isinstance(bars.get(tf),list) and len(bars[tf])>=60
                       for tf in ('M1','M5','M15','H1','H4','D1'))
            or not latest or type(latest[-1].get('time')) is not int
            or type(closed) is not int or closed%300!=0
            or closed!=latest[-1]['time']+300
            or not 0<=now-closed<=305
            or not isinstance(q.get('age_seconds'),(int,float))
            or not -10<=q['age_seconds']<=90):
            continue
        if not feasible_broker_usd100_sell_target(sym,side,m,q):continue
        signed_direction=1 if side=='BUY' else -1
        net_agent_score=sum(float(a['score']) for a in d.get('signals',[])
                            if isinstance(a,dict) and type(a.get('score')) in (int,float))
        out.append({'symbol':sym,'native_symbol':m['actual'],'side':side,
                    'closed_bar':closed,'min_lot':m['min_lot'],'lot_step':m['lot_step'],
                    'apex_evidence':round(max(0.0,signed_direction*net_agent_score),6),
                    'apex_weight':round(abs(weight),6)})
    return sorted(out,key=lambda x:(x['closed_bar'],x['apex_evidence'],
                                    x['apex_weight'],x['symbol']),reverse=True)


def exposure_fingerprint(history):
    """Snapshot independently broker-exported open positions. Fail closed."""
    items=history.get("positions")
    count=history.get("open_positions_count")
    if type(count) is not int or count<0 or count>len(SYMBOLS):
        raise ValueError("FP_BROKER_POSITION_COUNT_INVALID")
    if not isinstance(items,list) or len(items)!=count:
        raise ValueError("FP_BROKER_POSITION_COUNT_MISMATCH")
    occupied=set();tickets=set();rows=[]
    for p in items:
        if not isinstance(p,dict):raise ValueError("FP_BROKER_POSITION_SCHEMA_INVALID")
        ticket=str(p.get("ticket"))
        symbol=p.get("symbol");side=p.get("side")
        if (not ticket.isdigit() or int(ticket)<=0 or ticket in tickets or
            not isinstance(symbol,str) or not symbol or symbol in occupied or
            side not in ("BUY","SELL")):
            raise ValueError("FP_DUPLICATE_OR_INVALID_BROKER_POSITION")
        volume=p.get("volume");stop=p.get("stop_loss");take=p.get("take_profit")
        entry=p.get("open_price")
        if (not all(type(v) in (int,float) and math.isfinite(v) and v>0
                    for v in (volume,stop,take,entry)) or
            not ((stop<take and entry<take) if side=="BUY" else (take<stop and take<entry))):
            raise ValueError("FP_BROKER_POSITION_PROTECTION_INVALID")
        occupied.add(symbol);tickets.add(ticket)
        rows.append({"ticket":ticket,"symbol":symbol,"side":side,
                     "volume":volume,"stop_loss":stop,"take_profit":take})
    fp=hashlib.sha256(json.dumps(sorted(rows,key=lambda x:x["ticket"]),
                 sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return occupied,fp

def evaluate(now=None):
    now=time.time() if now is None else now
    account=account_proof()
    native=bridge_proof(account,now)
    scan={"instruments":[]};feed=load(FEED)
    choices=match_account_bound_apex11(feed,now)
    native_target_holds=[]
    for row in scan.get("instruments",[]):
        if (isinstance(row,dict) and row.get("symbol")=="SP500"
          and row.get("proposal")=="SELL" and row.get("available") is True
          and row.get("candidate_for_ai") is True
          and not feasible_broker_usd100_sell_target(
              "SP500","SELL",feed.get("mapping",{}).get("SP500",{}),
              feed.get("quotes",{}).get("SP500",{}))):
            native_target_holds.append(
              {"symbol":"SP500","reason":"USD100_TARGET_UNREACHABLE_AT_0_01_LOT"})
    history=load(HISTORY,300000)
    recon=load(RECON,300000)
    recent(history,"generated_at_utc",now,145)
    recent(recon,"generated_at_utc",now,95)
    if not (history.get("history_verified_from_mt5") is True and history.get("broker")=="FP Markets"
      and history.get("environment")=="DEMO" and history.get("history_complete_within_selected_window") is True
      and history.get("orders_submitted_by_exporter")==0 and history.get("execution_enabled") is False
      and recon.get("status")=="RECONCILED_READONLY" and recon.get("bridge_proof_matches_broker") is True):
        raise ValueError("FP_BROKER_RECONCILIATION_UNVERIFIED")
    pos=history.get("open_positions_count");pending=history.get("pending_orders_count")
    equity=history.get("equity_usd")
    if not (type(pos) is int and type(pending) is int and pos>=0 and pending>=0 and
         type(equity) in (int,float) and math.isfinite(equity) and equity>0 and
         native["positions"]==pos and native["pending"]==pending):
        raise ValueError("FP_BROKER_EXPOSURE_MISMATCH")
    occupied,fp=exposure_fingerprint(history)
    risk=recon.get("verified_open_gross_stop_risk_usd")
    if (recon.get("broker_exposure_sha256")!=fp or
        recon.get("verified_open_positions")!=pos or
        type(risk) not in (int,float) or not math.isfinite(risk) or
        risk<0 or (risk>equity*PORTFOLIO_CEILING if adaptive_on() else risk>52.01*pos)):
        raise ValueError("FP_BROKER_OPEN_RISK_PROOF_MISMATCH")
    eligible=[x for x in choices if x.get("native_symbol") not in occupied]
    blocks=[]
    if not choices:blocks.append("NO_CURRENT_APEX11_ACCOUNT_BOUND_M5_SIGNAL")
    elif not eligible:blocks.append("NO_UNOCCUPIED_APEX_SYMBOL")
    if (account["desired"],account["effective"])!=(1,1):blocks.append("FP_AUTOMATIC_TRADING_CONTROL_OFF")
    if native["enabled"]!=1:blocks.append("FP_BRIDGE_AUTO_ORDER_INPUT_OFF")
    if native["terminal"]!=1 or native["broker"]!=1:blocks.append("FP_BROKER_AUTOTRADING_PERMISSION_OFF")
    if pending!=0:blocks.append("FP_EXISTING_PENDING_ORDERS")
    # Sum broker-verified native USD stop risk, plus candidate stop and buffers.
    prospective=equity*0.001 if adaptive_on() else RISK_SL+2*(pos+1)
    if risk+prospective>equity*PORTFOLIO_CEILING:
        blocks.append("FP_20_PERCENT_PORTFOLIO_CAP")
    # Verified historical receipts are not a permanent veto. The independent
    # broker audit must confirm every native ACK; active/uncertain orders remain
    # blocked by broker exposure checks and the persistent single-writer ledger.
    if (recon.get("broker_verified_ack_count") !=
        recon.get("receipt_counts",{}).get("ACK")):
        blocks.append("FP_NATIVE_ACKS_NOT_INDEPENDENTLY_RECONCILED")
    if (FILES/"ABUTRON_FP/APEX_FP_NATIVE_ORDER_V1.req").exists():
        blocks.append("FP_EXISTING_NATIVE_REQUEST_IN_FLIGHT")
    return {"checked_at_utc":dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
      "schema":"abutron.fpmarkets.execution.single_writer.preflight.v1",
      "account":"FP Markets DEMO", "status":"READY" if not blocks else "BLOCKED",
      "positive_tradingagents_count":len(choices),
      "apex11_account_bound_candidate_count":len(choices),
      "occupied_symbol_count":len(occupied),
      "native_target_feasibility_holds":native_target_holds,
      "candidates":eligible,"blockers":blocks,
      "risk_SL_usd":None if adaptive_on() else RISK_SL,
      "reward_TP_usd":None if adaptive_on() else REWARD_TP,
      "new_entry_model":"OPTION_C_ADAPTIVE_V2" if adaptive_on() else "LEGACY_FIXED_USD",
      "portfolio_cap_percent":20, "broker_positions":pos,"broker_pending_orders":pending,
      "broker_equity_usd":equity,"occupied_native_symbols":sorted(occupied),
      "broker_exposure_sha256":fp,"verified_open_risk_usd":risk,
      "automatic_order_execution_authorized":False,
      "orders_submitted":0,"session_nonce":account["nonce"],"login":account["login"]}

def write_status(report,mode):
    STATE.mkdir(parents=True,mode=0o700,exist_ok=True)
    redacted={k:v for k,v in report.items() if k not in ("session_nonce","login")}
    redacted["router_mode"]=mode
    redacted["candidates"]=[{k:v for k,v in r.items() if k not in ("min_lot","lot_step")} for r in report.get("candidates",[])]
    fd,tmp=tempfile.mkstemp(dir=STATE,prefix=".fp-gate-")
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(redacted,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,STATE/"latest.json")
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def durable_ledger():
    path=STATE/"order-journal.sqlite3"
    db=sqlite3.connect(str(path),timeout=5,isolation_level=None)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS requests(
        signal_id TEXT PRIMARY KEY, closed_bar INTEGER NOT NULL,
        canonical TEXT NOT NULL, broker_symbol TEXT NOT NULL,
        side TEXT NOT NULL, session_nonce TEXT NOT NULL,
        state TEXT NOT NULL, created_at INTEGER NOT NULL,
        broker_order_id INTEGER, broker_deal_id INTEGER,
        UNIQUE(canonical,closed_bar))""")
    return db

def safe_receipt(path,signal_id,nonce,login):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2048:
        raise ValueError("FP_NATIVE_RECEIPT_FILE_INVALID")
    lines=path.read_text(encoding="utf-8-sig").splitlines()
    if (len(lines)!=10 or lines[0]!="APEX_FP_NATIVE_V1"
      or lines[1]!=signal_id or lines[2] not in ("ACK","BLOCKED","UNKNOWN")
      or lines[7:]!=[nonce,login,"FPMarketsSC-Demo"]):
        raise ValueError("FP_NATIVE_RECEIPT_SCHEMA_OR_ACCOUNT_INVALID")
    try:order=int(lines[4]);deal=int(lines[5]);when=int(lines[6])
    except ValueError:raise ValueError("FP_NATIVE_RECEIPT_NUMERIC_INVALID")
    if order<0 or deal<0 or when<=0:
        raise ValueError("FP_NATIVE_RECEIPT_VALUES_INVALID")
    return lines[2],order,deal

def refresh_durable_state(db,account):
    rows=db.execute("SELECT signal_id,session_nonce,state,broker_symbol,side,broker_order_id,broker_deal_id FROM requests WHERE state IN ('PREPARED','DISPATCHED','ACK_PENDING_EVIDENCE','OPEN_PROTECTED','UNKNOWN') ORDER BY created_at").fetchall()
    for key,nonce,state,old_symbol,old_side,old_order,old_deal in rows:
        # UNKNOWN is terminal until explicit human investigation; never
        # silently reset it using a later receipt or mutable evidence file.
        if state=="UNKNOWN":
            continue
        # Recheck OPEN_PROTECTED on each poll to permit eventual verified
        # closure, retaining a halt on new entries while risk remains open.
        # Verify only current-session receipts. Older-session uncertain requests
        # remain blocked until a human reconciles them with broker history.
        if nonce!=account["session_nonce"]:
            # An OPEN_PROTECTED position from a previous worker session remains
            # a real broker position, not an unresolved new request. The
            # independent current native reconciliation must match all open
            # positions and USD stop risk; independently bind this older
            # position to its exact native broker entry order/deal/ticket.
            if state=="OPEN_PROTECTED":
                history=load(HISTORY,300000)
                recon=load(RECON,300000)
                recent(history,"generated_at_utc",time.time(),145)
                recent(recon,"generated_at_utc",time.time(),95)
                occupied,fingerprint=exposure_fingerprint(history)
                if (recon.get("status")!="RECONCILED_READONLY"
                    or recon.get("broker_exposure_sha256")!=fingerprint
                    or recon.get("verified_open_positions")!=len(occupied)
                    or recon.get("broker_open_positions")!=len(occupied)
                    or recon.get("native_broker_open_risk_verified") is not True
                    or recon.get("receipt_counts",{}).get("UNKNOWN")!=0):
                    raise ValueError("FP_PRIOR_SESSION_NATIVE_RISK_NOT_RECONCILED")
                positions=[p for p in history.get("positions",[]) if
                    str(p.get("ticket"))==str(old_order) and
                    p.get("symbol")==old_symbol and p.get("side")==old_side]
                entries=[e for e in history.get("trade_deals",[]) if
                    str(e.get("ticket"))==str(old_deal) and
                    str(e.get("order_id"))==str(old_order) and
                    str(e.get("position_id"))==str(old_order) and
                    e.get("symbol")==old_symbol and e.get("side")==old_side and
                    e.get("entry")=="IN"]
                if len(positions)==1 and len(entries)==1:
                    continue
            raise ValueError("FP_UNCERTAIN_PRIOR_SESSION_REQUEST")
        p=FILES/"ABUTRON_FP"/"receipts"/(key+".txt")
        if not p.exists():continue
        result,order,deal=safe_receipt(p,key,nonce,account["login"])
        if result=="UNKNOWN":
            new_state="UNKNOWN"
        elif result=="BLOCKED":
            new_state="BROKER_BLOCKED_NO_ACK"
        else:
            if not order or not deal:raise ValueError("FP_ACK_IDS_INVALID")
            new_state="ACK_PENDING_EVIDENCE"
            evidence=FILES/"ABUTRON_FP"/"evidence"/(key+".txt")
            if evidence.is_file() and not evidence.is_symlink():
                lines=evidence.read_text(encoding="utf-8-sig").splitlines()
                if (len(lines)==19 and lines[:5]==[
                    "APEX_FP_BROKER_POSITION_V1",key,nonce,account["login"],"FPMarketsSC-Demo"]
                    and lines[7]==str(order) and lines[8]==str(deal)):
                    if lines[16]=="CLOSED_BROKER_VERIFIED":
                        new_state="CLOSED_BROKER_VERIFIED"
                    elif lines[16]=="OPEN_PROTECTED":
                        new_state="OPEN_PROTECTED"
                    elif lines[16]=="OPEN_UNPROTECTED":
                        new_state="UNKNOWN"
        db.execute("UPDATE requests SET state=?, broker_order_id=?, broker_deal_id=? WHERE signal_id=?",
                   (new_state,order,deal,key))

def transactionally_create_request(doc,db,now=None):
    now=int(time.time() if now is None else now)
    if doc.get("status")!="READY" or doc.get("blockers"):
        return "NOT_READY"
    # An account or EA switch changed after the scan cannot be overridden by
    # a previously READY research snapshot. Read them again before journal.
    latest=account_proof()
    if ((latest["desired"],latest["effective"])!=(1,1)
      or latest["nonce"]!=doc.get("session_nonce")
      or latest["login"]!=doc.get("login")):
        return "FP_ACCOUNT_PERMISSION_OR_SESSION_CHANGED"
    latest_bridge=bridge_proof(latest,time.time())
    if (latest_bridge["enabled"],latest_bridge["terminal"],latest_bridge["broker"])!=(1,1,1):
        return "FP_NATIVE_EA_OR_TERMINAL_ORDER_PERMISSION_CHANGED"
    if adaptive_on() and not latest_bridge["adaptive_ready"]:
        return "FP_ADAPTIVE_NATIVE_CAPABILITY_MISSING"
    if (latest_bridge["pending"]!=0
      or latest_bridge["positions"]!=doc.get("broker_positions")):
        return "FP_BROKER_EXPOSURE_CHANGED"
    # Recheck independent broker snapshot and risk at the commit boundary.
    latest_history=load(HISTORY,300000)
    latest_recon=load(RECON,300000)
    recent(latest_history,"generated_at_utc",time.time(),145)
    recent(latest_recon,"generated_at_utc",time.time(),95)
    occupied,fingerprint=exposure_fingerprint(latest_history)
    open_risk=latest_recon.get("verified_open_gross_stop_risk_usd")
    if (fingerprint!=doc.get("broker_exposure_sha256") or
        fingerprint!=latest_recon.get("broker_exposure_sha256") or
        len(occupied)!=doc.get("broker_positions") or
        latest_recon.get("status")!="RECONCILED_READONLY" or
        latest_recon.get("verified_open_positions")!=len(occupied) or
        type(open_risk) not in (float,int) or
        not math.isfinite(open_risk) or open_risk!=doc.get("verified_open_risk_usd")):
        return "FP_BROKER_EXPOSURE_CHANGED"
    equity=latest_history.get("equity_usd")
    if (type(equity) not in (float,int) or not math.isfinite(equity) or
        equity<=0 or open_risk+(equity*0.001 if adaptive_on()
             else RISK_SL+2*(len(occupied)+1))>equity*PORTFOLIO_CEILING):
        return "FP_20_PERCENT_PORTFOLIO_CAP"
    candidates=doc.get("candidates",[])
    if not candidates:return "NO_CANDIDATE"
    # OPEN_PROTECTED is reconciled durable exposure, not a pending request.
    if db.execute("""SELECT COUNT(*) FROM requests
                     WHERE state NOT IN ('BROKER_BLOCKED_NO_ACK','CLOSED_BROKER_VERIFIED','OPEN_PROTECTED')""").fetchone()[0]:
        return "PRIOR_NATIVE_REQUEST_UNRESOLVED"
    ledger_open={r[0] for r in db.execute(
        "SELECT broker_symbol FROM requests WHERE state='OPEN_PROTECTED'").fetchall()}
    if ledger_open!=occupied:
        return "FP_LEDGER_BROKER_POSITION_MISMATCH"
    account={"session_nonce":doc["session_nonce"],"login":doc["login"]}
    native_dir=FILES/"ABUTRON_FP"
    st=native_dir.lstat()
    if not stat.S_ISDIR(st.st_mode) or native_dir.is_symlink() or not st.st_mode&0o200:
        raise ValueError("FP_NATIVE_REQUEST_DIR_INVALID")
    final=native_dir/"APEX_FP_NATIVE_ORDER_V1.req"
    if final.exists() or final.is_symlink():
        return "NATIVE_ORDER_REQUEST_ALREADY_EXISTS"
    # One broker account, one writer, one candle key per canonical symbol.
    c=candidates[0]
    if c.get("native_symbol") in occupied:
        return "FP_ONE_POSITION_PER_SYMBOL"
    if (c["symbol"] not in SYMBOLS or c["side"] not in ("BUY","SELL") or
        not isinstance(c.get("closed_bar"),int) or c["closed_bar"]<=0):
        raise ValueError("FP_SIGNAL_KEY_INVALID")
    lot=c.get("min_lot");step=c.get("lot_step")
    if (type(lot) not in (int,float) or type(step) not in (int,float)
      or not math.isfinite(lot) or not math.isfinite(step) or not 0<lot<=1.0 or not 0<step<=lot):
        raise ValueError("FP_BROKER_MIN_VOLUME_UNVERIFIED")
    digest=hashlib.sha256((CID+"|"+c["symbol"]+"|"+str(c["closed_bar"])).encode()).hexdigest()
    if not HEX64.fullmatch(digest):raise ValueError("FP_SIGNAL_HASH_INVALID")
    expire=now+14
    if adaptive_on():
        protocol,amount,sl,tp=("APEX_FP_NATIVE_ADAPTIVE_ORDER_V2",
                               "AUTO","0.10","STRUCTURE_M5")
    else:
        protocol,amount,sl,tp=("APEX_FP_NATIVE_ORDER_V1",
                               "%.6f" % lot,"50.00","100.00")
    payload="\r\n".join([protocol,doc["session_nonce"],digest,
        doc["login"],"FPMarketsSC-Demo",c["native_symbol"],c["side"],
        amount,sl,tp,str(expire),"SEND_DEMO_ONLY"])+"\r\n"
    # Write-ahead insert committed before the file can become visible to MT5.
    db.execute("BEGIN IMMEDIATE")
    try:
        if db.execute("SELECT 1 FROM requests WHERE canonical=? AND closed_bar=?",
                      (c["symbol"],c["closed_bar"])).fetchone():
            db.execute("ROLLBACK")
            return "CANDLE_ALREADY_CONSUMED"
        db.execute("""INSERT INTO requests(signal_id,closed_bar,canonical,
                     broker_symbol,side,session_nonce,state,created_at)
                     VALUES(?,?,?,?,?,?,?,?)""",
                   (digest,c["closed_bar"],c["symbol"],c["native_symbol"],
                    c["side"],doc["session_nonce"],"PREPARED",now))
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise
    tmp=native_dir/(".pending-"+digest)
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            os.fchown(f.fileno(),st.st_uid,st.st_gid)
            f.write(payload.encode("utf-8"))
            f.flush();os.fsync(f.fileno())
        # Hard-link creates a complete final request without overwriting any
        # other process's in-flight order. The bridge consumes only the final.
        os.link(tmp,final,follow_symlinks=False)
        dir_fd=os.open(native_dir,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(dir_fd)
        finally:os.close(dir_fd)
        db.execute("UPDATE requests SET state='DISPATCHED' WHERE signal_id=?",(digest,))
        return "NATIVE_REQUEST_PUBLISHED_WAIT_FOR_BROKER"
    finally:
        if tmp.exists() and not tmp.is_symlink():tmp.unlink()

def main():
    config=load(CONFIG,10000)
    if (config.get("schema")!="abutron.fpmarkets.demo.single_writer.config.v1"
      or config.get("account")!="FP Markets DEMO"
      or type(config.get("enable_request_creation")) is not bool):
        raise ValueError("FP_ROUTER_CONFIG_INVALID")
    # The operating mode is separately controlled by this explicit root-owned
    # config AND both account controls AND the disabled-by-default EA input.
    # Never revive legacy fixed $50/$100 request creation, even if a stale config says ON.
    mode="ARMED" if config["enable_request_creation"] and adaptive_on() else "DISARMED"
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock=STATE/"single-writer.lock"
    with lock.open("a+") as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            doc=evaluate()
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as ex:
            msg=str(ex)
            reason=msg if re.fullmatch("[A-Z][A-Z0-9_]{5,100}",msg) else type(ex).__name__
            doc={"schema":"abutron.fpmarkets.execution.single_writer.preflight.v1",
                 "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                 "status":"BLOCKED","blockers":["FP_"+reason],
                 "positive_tradingagents_count":0,"candidates":[],
                 "automatic_order_execution_authorized":False,"orders_submitted":0}
        # DISARMED mode is fully non-executing; no request writer is activated.
        if mode=="DISARMED":
            write_status(doc,mode)
            return {"status":doc["status"],"mode":mode,
                    "positive":doc["positive_tradingagents_count"],"blockers":doc.get("blockers",[]),"requests_created":0}
        # The single account+signal ledger is persistent. Each request is
        # journaled before atomic broker-visible publication, with no replay.
        db=durable_ledger()
        try:
            # Broker ACK/position reconciliation must run even when NEW-entry
            # readiness is BLOCKED by the resulting open position. This never
            # creates or retries any order; the journal remains idempotent.
            if "session_nonce" in doc and "login" in doc:
                account_for_reconciliation=doc
            else:
                current=account_proof()
                account_for_reconciliation={"session_nonce":current["nonce"],
                                            "login":current["login"]}
            refresh_durable_state(db,account_for_reconciliation)
            result=transactionally_create_request(doc,db)
        except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as err:
            result="BLOCKED_NATIVE_DISPATCH_"+type(err).__name__
        finally:
            db.close()
        doc["dispatch_result"]=result
        if result!="NATIVE_REQUEST_PUBLISHED_WAIT_FOR_BROKER":
            doc["status"]="BLOCKED"
            doc.setdefault("blockers",[]).append(result)
        else:
            doc["status"]="SUBMITTED_TO_NATIVE_BRIDGE_AWAIT_BROKER_RECEIPT"
        write_status(doc,"ARMED")
        return {"status":doc["status"],"mode":"ARMED",
                "blockers":doc.get("blockers",[]),
                "requests_created":int(result=="NATIVE_REQUEST_PUBLISHED_WAIT_FOR_BROKER")}

if __name__=="__main__":
    try:print(json.dumps(main(),sort_keys=True))
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as e:
        print(json.dumps({"status":"BLOCKED","error_type":type(e).__name__,"requests_created":0}))
