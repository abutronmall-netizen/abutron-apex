"""Read-only ABUTRON APEX live + historical research rankings.

Never imported by the signal router or MT5 workers. Scores describe present
rule confluence, NOT trade win probability, broker approval or trade advice.
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

MARKET = Path("/var/lib/apex/operator-live/native-market.json")
SCANNER = Path("/var/lib/apex/operator-live/native-scanner.json")
HISTORY = Path("/var/lib/apex/precision-history-ai-snapshot/closed-candles.sqlite3")
REVIEWS = Path("/var/lib/abutron-scanner-llm/latest.json")
ALLOWED_FRAMES = {"M1", "M5", "M15", "H1", "H4", "D1"}
DERIV_VISIBLE_SYMBOLS=frozenset(("Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0"))
MAX_AGE = 180


def _read(path: Path, limit=8_000_000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("INPUT_NOT_AVAILABLE")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _age(timestamp, now):
    parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UNTRUSTED_TIMESTAMP")
    result = now.timestamp() - parsed.timestamp()
    if not -15 <= result <= MAX_AGE:
        raise ValueError("STALE_NATIVE_BROKER_SNAPSHOT")
    return round(result, 1)


def _historical(conn, symbol, current_bar):
    records = conn.execute(
        """SELECT start_time_utc,close FROM candles
           WHERE symbol=? AND timeframe='M5' AND start_time_utc<?
           ORDER BY start_time_utc DESC LIMIT 501""",
        (symbol, current_bar)
    ).fetchall()
    return _summarize_records(list(reversed(records)))


def _historical_from_verified_broker(m5, current_bar):
    """Temporary display-only fallback: native broker M5 (never a cached trade signal)."""
    records=[]
    for bar in m5:
        ts=int(bar["time"])
        close=float(bar["close"])
        if ts<current_bar and ts%300==0 and close>0 and math.isfinite(close):
            records.append((ts,close))
    return _summarize_records(records[-501:])


def _summarize_records(bars):
    past_moves = []
    for older, newer in zip(bars, bars[1:]):
        if newer[0] - older[0] != 300 or older[1] <= 0:
            continue  # Never treat a discontinuous interval as one M5 return.
        delta = abs(float(newer[1]) / float(older[1]) - 1.0) * 100
        if math.isfinite(delta):
            past_moves.append(delta)
    span = (bars[-1][0]-bars[0][0]) / 3600 if len(bars)>=2 else 0
    median = statistics.median(past_moves) if past_moves else None
    enough = len(past_moves)>=40
    return {
        "closed_m5_bars": len(bars),
        "completed_m5_returns": len(past_moves),
        "historical_span_hours": round(span, 1),
        "median_abs_m5_move_pct": round(median, 5) if enough else None,
        "evidence_depth": "SHORT_HISTORY" if span<24*30 else "MULTIWEEK",
        "sufficient_for_volatility_context": enough,
        "validated_strategy_win_rate": None,
        "cost_adjusted_backtest_available": False,
        "_returns": past_moves,
    }


def build(now=None, *, market=None, scanner=None, connection=None, reviews=None):
    now = now or datetime.now(timezone.utc)
    market = market if market is not None else _read(MARKET)
    scanner = scanner if scanner is not None else _read(SCANNER)
    if not isinstance(market, dict) or not isinstance(scanner, dict):
        raise ValueError("BROKER_FEED_NOT_VERIFIED")
    if (market.get("schema")!="apex.mt5.market.v1"
        or market.get("source")!="Deriv DEMO MT5"
        or market.get("execution_enabled") is not False
        or scanner.get("schema")!="apex.scanner.shadow.v1"
        or scanner.get("source")!="Deriv DEMO MT5"
        or scanner.get("orders_enabled") is not False
        or scanner.get("live_enabled") is not False
        or scanner.get("broker_generated_at_utc") != market.get("generated_at_utc")):
        raise ValueError("SCANNER_BROKER_SNAPSHOT_MISMATCH")
    market_age = _age(market.get("generated_at_utc"), now)
    scanner_age = _age(scanner.get("generated_at_utc"), now)
    rows = scanner.get("instruments")
    data = market.get("data")
    if not isinstance(rows, list) or len(rows)!=13 or not isinstance(data,dict) or len(data)!=13:
        raise ValueError("INCOMPLETE_13_SYMBOL_SCAN")
    scan_symbols = {x.get("symbol") for x in rows if isinstance(x,dict)}
    if len(scan_symbols)!=13 or scan_symbols!=set(data):
        raise ValueError("SYMBOLS_DO_NOT_MATCH")
    own_conn = connection is None
    archive_temporarily_unavailable=False
    if own_conn:
        if HISTORY.is_symlink():
            raise ValueError("UNTRUSTED_HISTORY_SNAPSHOT_PATH")
        if (not HISTORY.is_file() or not -15 <= now.timestamp()-HISTORY.stat().st_mtime <= 600):
            # Never treat an outdated immutable snapshot as current history.
            connection=None
            archive_temporarily_unavailable=True
        else:
            try:
                # Snapshot is an atomic standalone SQLite backup with no active
                # WAL files; immutable mode requires no write-capable DB path.
                connection=sqlite3.connect(
                    "file:"+str(HISTORY)+"?mode=ro&immutable=1",uri=True,timeout=1)
                connection.execute("PRAGMA query_only=ON")
            except sqlite3.OperationalError:
                # The snapshot is not accessible: use recent verified MT5
                # candles rather than granting the web process write access.
                if connection is not None:
                    connection.close()
                connection=None
                archive_temporarily_unavailable=True
    try:
        if connection is not None:
            try:
                history_ok=connection.execute("PRAGMA quick_check").fetchone()
            except sqlite3.OperationalError:
                archive_temporarily_unavailable=True
                connection.close()
                connection=None
            else:
                if history_ok != ("ok",):
                    # Actual database corruption is NOT a permissible fallback.
                    raise ValueError("HISTORICAL_DATABASE_CHECK_FAILED")
        if reviews is None:
            try: reviews=_read(REVIEWS,600_000)
            except (ValueError,OSError,TypeError,UnicodeError,json.JSONDecodeError):
                reviews={}
        matched_reviews={}
        if (isinstance(reviews,dict) and reviews.get("schema")=="abutron.scanner.llm.v1"):
            try:
                age_llm=_age(reviews.get("checked_at_utc"),now)
                for item in reviews.get("reviews",[]):
                    if isinstance(item,dict) and item.get("symbol") in scan_symbols:
                        matched_reviews[item["symbol"]]=item
            except (ValueError, TypeError, OverflowError):
                pass
        output=[]
        for entry in rows:
            symbol=entry["symbol"]
            frames=data[symbol]
            if not isinstance(frames,dict) or set(frames)!=ALLOWED_FRAMES:
                raise ValueError("INCOMPLETE_BROKER_TIMEFRAMES")
            m5=frames.get("M5")
            if not isinstance(m5,list) or len(m5)<2:
                raise ValueError("BROKER_M5_UNAVAILABLE")
            bar=int(entry.get("last_closed_m5"))
            last=next((b for b in reversed(m5) if int(b["time"])==bar),None)
            if last is None or bar+300>now.timestamp()-1:
                raise ValueError("UNMATCHED_COMPLETED_M5_CANDLE")
            if connection is not None:
                try:
                    history=_historical(connection,symbol,bar)
                    history["source"]="HISTORICAL_SQLITE_READONLY_SNAPSHOT"
                except sqlite3.OperationalError:
                    archive_temporarily_unavailable=True
                    connection.close()
                    connection=None
            if connection is None:
                history=_historical_from_verified_broker(m5,bar)
                history["source"]="RECENT_VERIFIED_MT5_BARS_FALLBACK"
            prior=m5[-2]
            delta_pct=abs(float(last["close"])/float(prior["close"])-1.0)*100 if float(prior["close"])>0 else None
            if delta_pct is None or not math.isfinite(delta_pct):
                raise ValueError("INVALID_BROKER_PRICE")
            reference=history.pop("_returns")
            percentile=(round(100*sum(p<=delta_pct for p in reference)/len(reference),1)
                        if history["sufficient_for_volatility_context"] else None)
            regime=("ELEVATED" if percentile is not None and percentile>=95
                    else "QUIET" if percentile is not None and percentile<=15
                    else "NORMAL" if percentile is not None else "UNKNOWN")
            history["current_m5_abs_move_pct"]=round(delta_pct,5)
            history["current_m5_move_percentile"]=percentile
            history["volatility_context"]=regime
            direction=entry.get("proposal","HOLD")
            if direction not in ("BUY","SELL","HOLD"):
                raise ValueError("UNTRUSTED_SCANNER_PROPOSAL")
            signal=entry.get("m5_signal")
            indicators=entry.get("indicators")
            if not isinstance(indicators,dict) or set(indicators)!=ALLOWED_FRAMES:
                raise ValueError("INCOMPLETE_INDICATOR_EVIDENCE")
            if indicators["M5"].get("bar_time")!=bar:
                raise ValueError("INDICATOR_TIME_MISMATCH")
            aligned={"BUY":"UP","SELL":"DOWN"}.get(direction)
            htf=sum(indicators[tf].get("trend")==aligned for tf in ("M15","H1","H4")) if aligned else 0
            rsi=float(indicators["M5"]["rsi14"])
            rsi_valid=(53<=rsi<=70 if direction=="BUY" else 30<=rsi<=47 if direction=="SELL" else False)
            # Heuristic confluence/recency score, NEVER a probability or backtest.
            score=(min(100,62+8*(signal==direction)+6*htf+
                       4*(indicators["D1"].get("trend")==aligned)+4*rsi_valid-
                       (6 if regime=="ELEVATED" else 2 if regime=="QUIET" else 0))
                   if direction in ("BUY","SELL") else None)
            llm=matched_reviews.get(symbol,{})
            valid_llm=(direction in ("BUY","SELL")
                       and llm.get("m5_bar_time")==bar
                       and llm.get("scanner_proposal")==direction)
            output.append({
                "symbol":symbol,
                "family":entry.get("family"),
                "proposal":direction,
                "m5_bar_time":bar,
                "m5_closed_utc":datetime.fromtimestamp(bar+300,timezone.utc).isoformat(),
                "higher_tf_confirmations":htf,
                "m5_rsi":round(rsi,2),
                "evidence_score":score,
                "score_type":"CURRENT_CONFLUENCE_HEURISTIC_NOT_WIN_PROBABILITY",
                "reason":str(entry.get("reason",""))[:190],
                "qwen_advisory":str(llm.get("rating","PENDING"))[:32] if valid_llm else "PENDING",
                "historical":history,
                "broker_order_authorized":False,
                "read_only":True,
            })
        output=[item for item in output if item["symbol"] in DERIV_VISIBLE_SYMBOLS]
        output.sort(key=lambda x:(x["evidence_score"] is None,
                                  -(x["evidence_score"] or 0),x["symbol"]))
        top=[item for item in output if item["evidence_score"] is not None][:3]
        return {
            "schema":"abutron.apex.decision_intelligence.readonly.v1",
            "available":True,"mode":"DERIV_DEMO_RESEARCH_ONLY",
            "generated_at_utc":now.isoformat(),
            "market_age_seconds":market_age,
            "scanner_age_seconds":scanner_age,
            "broker_snapshot_utc":market["generated_at_utc"],
            "scanner_snapshot_utc":scanner["generated_at_utc"],
            "total_symbols":len(output),
            "qualified_research_count":sum(x["evidence_score"] is not None for x in output),
            "top_three":top,"all_symbols":output,
            "historical_limitations":(
                "Archive temporarily unavailable: some symbols use only recent verified native MT5 M5 bars. "
                "Volatility context only, never a validated success rate."
                if archive_temporarily_unavailable else
                "M5 history is short; volatility context only, not proven setup success rate."),
            "historical_archive_fallback":archive_temporarily_unavailable,
            "historical_source":(
                "VERIFIED_NATIVE_M5_ONLY" if archive_temporarily_unavailable
                else "HISTORICAL_SQLITE_READONLY_SNAPSHOT"),
            "scoring_explanation":"Existing APEX BUY/SELL gate + M5/M15/H1/H4/D1 confirmation + RSI + historical M5 volatility; not a forecast or trade permission.",
            "signals_executed":0,
            "order_routing_changed":False,
            "live_trading":False,
        }
    finally:
        if own_conn and connection is not None:
            connection.close()
