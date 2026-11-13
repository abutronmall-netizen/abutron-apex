#!/usr/bin/env python3
"""FP Markets native-contract readiness, read-only. Never sends or authorizes orders."""
from __future__ import annotations
import datetime, json, math, re, time
from pathlib import Path

SOURCE=Path("/var/lib/abutron-fpmarkets-feed/market/35b81a287b6a030f2f46ff426b135e6c.json")
EXPECTED=("XAUUSD","BTCUSD","EURUSD","GBPUSD","USDJPY","AUDUSD","US100","US30","SP500","GER40","USOIL","USDCHF","NZDUSD")
SCHEMA="abutron.fpmarkets.native.contract.readiness.v1"

def finite_positive(value):
 return type(value) in (int,float) and math.isfinite(value) and value>0

def evaluate(data,now=None):
 now=time.time() if now is None else float(now)
 checked=data.get("checked_at_utc")
 try:
  snapshot=datetime.datetime.fromisoformat(checked.replace("Z","+00:00")).timestamp()
 except (TypeError,ValueError,AttributeError):snapshot=0
 source_fresh=-15<=now-snapshot<=120
 identity=(data.get("schema")=="abutron.fpmarkets.native.candles.v1"
   and data.get("source")=="FP Markets DEMO MT5" and data.get("account_mode")=="DEMO"
   and data.get("broker_server")=="FPMarketsSC-Demo"
   and data.get("execution_enabled") is False and data.get("orders_submitted")==0)
 maps=data.get("mapping",{})
 quotes=data.get("quotes",{})
 universe_ok=(isinstance(maps,dict) and set(maps)==set(EXPECTED)
  and isinstance(quotes,dict) and set(quotes)==set(EXPECTED))
 rows=[]
 for symbol in EXPECTED:
  m=maps.get(symbol,{}) if isinstance(maps,dict) else {}
  q=quotes.get(symbol,{}) if isinstance(quotes,dict) else {}
  r=[]
  if not identity:r.append("FP_NATIVE_ACCOUNT_SOURCE_UNVERIFIED")
  if not source_fresh:r.append("FP_MARKET_FEED_STALE")
  if not universe_ok:r.append("FP_13_SYMBOL_UNIVERSE_MISMATCH")
  if m.get("status")!="MAPPED" or not isinstance(m.get("actual"),str) or not re.fullmatch(r"[A-Za-z0-9_.-]{2,24}",m["actual"]):r.append("FP_SYMBOL_MAPPING_UNVERIFIED")
  if m.get("trade_mode")!=4:r.append("FP_SYMBOL_NOT_IN_FULL_TRADE_MODE")
  for k in ("min_lot","lot_step","contract_size"):
   if not finite_positive(m.get(k)):r.append("FP_BROKER_"+k.upper()+"_UNVERIFIED")
  if not (type(m.get("digits")) is int and 0<=m["digits"]<=12):r.append("FP_BROKER_DIGITS_UNVERIFIED")
  if q.get("symbol")!=m.get("actual") or not finite_positive(q.get("bid")) or not finite_positive(q.get("ask")) or q["ask"]<q["bid"]:r.append("FP_QUOTE_INVALID")
  if not (type(q.get("time")) in (int,float) and -15<=now-q["time"]<=120):r.append("FP_BROKER_TICK_STALE")
  # These three proofs cannot be inferred from price, contract-size or min lot.
  r.extend(("FP_ORDER_CALC_PROFIT_AND_MARGIN_NOT_VERIFIED",
            "FP_BROKER_NATIVE_STOP_LEVELS_NOT_VERIFIED",
            "FP_BROKER_ORDER_CHECK_NOT_VERIFIED",
            "FP_ACCOUNT_EQUITY_AND_EXPOSURE_NOT_RECONCILED"))
  rows.append({"symbol":symbol,"broker_symbol":m.get("actual") if isinstance(m.get("actual"),str) else None,
     "trade_mode_full":m.get("trade_mode")==4,"contract_fields_present":all(finite_positive(m.get(k)) for k in ("min_lot","lot_step","contract_size")),
     "execution_authorized":False,"blockers":r})
 from collections import Counter
 reasons=dict(sorted(Counter(z for row in rows for z in row["blockers"]).items()))
 return {"schema":SCHEMA,"checked_at_utc":datetime.datetime.fromtimestamp(now,datetime.timezone.utc).isoformat(),
  "broker":"FP Markets","environment":"DEMO","source_fresh":source_fresh,"source_identity_verified":identity,
  "symbols_total":len(rows),"symbols_trade_mode_full":sum(x["trade_mode_full"] for x in rows),
  "symbols_trade_mode_disabled":[x["symbol"] for x in rows if not x["trade_mode_full"]],
  "orders_enabled":False,"orders_submitted":0,"ready_to_execute":False,
  "stop_loss_gross_usd":50,"take_profit_gross_usd":100,"portfolio_risk_ceiling_pct":20,
  "risk_metadata_coverage_complete":False,"blocker_totals":reasons,"instruments":rows}

def collect():
 try:
  if SOURCE.is_symlink() or SOURCE.stat().st_size>10_000_000:raise ValueError("UNTRUSTED_MARKET_FILE")
  return evaluate(json.loads(SOURCE.read_text()))
 except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
  return {"schema":SCHEMA,"ready_to_execute":False,"orders_enabled":False,"orders_submitted":0,
      "source_verified":False,"blockers":["FP_CONTRACT_REPORT_FAILED_"+type(exc).__name__]}

if __name__=="__main__":print(json.dumps(collect(),indent=2,sort_keys=True))
