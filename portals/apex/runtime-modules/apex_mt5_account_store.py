"""Validate/store private Deriv DEMO account snapshot atomically. Fail closed."""
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime,timezone

TARGET=Path("/var/lib/apex/mt5-market/deriv_demo_account.json")


def valid_number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))


def check(obj):
    if not isinstance(obj,dict) or obj.get("schema")!="apex.mt5.account.v1":
        raise ValueError("invalid broker account schema")
    if obj.get("source")!="Deriv DEMO MT5" or obj.get("execution_enabled") is not False or obj.get("live_enabled") is not False:
        raise ValueError("unverified demo-only source")
    if obj.get("orders_placed_by_this_exporter")!=0:
        raise ValueError("account exporter must not send orders")
    t=datetime.fromisoformat(obj["generated_at_utc"])
    age=(datetime.now(timezone.utc)-t).total_seconds()
    if t.tzinfo is None or age < -30 or age > 120:
        raise ValueError("broker account stale on export")
    account=obj.get("account")
    if not isinstance(account,dict) or account.get("mode")!="DEMO" or account.get("broker")!="Deriv" or account.get("currency")!="USD":
        raise ValueError("account mismatch")
    for k in ("balance_usd","equity_usd","margin_usd","free_margin_usd",
              "floating_profit_usd","realized_today_usd","realized_30d_usd",
              "gross_negative_deal_cashflows_today_usd"):
        if not valid_number(account.get(k)):raise ValueError("invalid account "+k)
    if account["gross_negative_deal_cashflows_today_usd"] < 0:
        raise ValueError("invalid gross negative deal cashflows")
    if account["balance_usd"] < 0 or account["equity_usd"] < 0:
        raise ValueError("invalid broker balance/equity")
    positions=obj.get("positions")
    if not isinstance(positions,list) or len(positions)!=account.get("open_positions"):
        raise ValueError("broker open-position reconciliation mismatch")
    if not isinstance(obj.get("history_30d"),list) or obj.get("history_complete") is not True:
        raise ValueError("broker history incomplete")
    contracts=obj.get("contracts")
    if not isinstance(contracts,list) or len(contracts)!=13:
        raise ValueError("incomplete Deriv contract specification")
    seen=set()
    for p in positions:
        if not isinstance(p,dict) or p.get("ticket") in seen or not isinstance(p.get("ticket"),int):
            raise ValueError("unreconciled positions")
        seen.add(p["ticket"])
        if not all(valid_number(p.get(k)) for k in ("volume","price_open","price_current","profit_usd","sl","tp")):
            raise ValueError("invalid position exposure")
    if "login" in json.dumps(obj).lower() or "password" in json.dumps(obj).lower():
        raise ValueError("broker identity fields forbidden")
    return obj


def store(obj,path=TARGET):
    valid=check(obj)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".account.")
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump(valid,f,allow_nan=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


if __name__=="__main__":
    try:
        raw=sys.stdin.read(4_000_000)
        if len(raw)>=4_000_000:raise ValueError("account payload exceeds size limit")
        doc=json.loads(raw)
        store(doc)
        print(json.dumps({"status":"OK","source":"Deriv DEMO MT5","open_positions":doc["account"]["open_positions"],
            "generated_at_utc":doc["generated_at_utc"],"orders_placed":0}))
    except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
        print("Broker account snapshot REJECTED: "+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
