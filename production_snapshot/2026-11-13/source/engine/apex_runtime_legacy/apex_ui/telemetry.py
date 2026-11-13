"""Whitelist-only views of private APEX broker telemetry and risk evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path

ACCOUNT_PATH=Path("/var/lib/apex/mt5-market/deriv_demo_account.json")
SCANNER_PATH=Path("/var/lib/apex/operator-live/native-scanner.json")
DERIV_VISIBLE_SYMBOLS=frozenset(("Volatility 25 Index.0","Volatility 50 Index.0","Volatility 75 Index.0"))
LLM_PATH=Path("/var/lib/abutron-scanner-llm/latest.json")
GOVERNOR_PATH=Path("/var/lib/apex/risk/latest.json")


def read(path):
    try:
        if path.stat().st_size > 4_000_000:return None
        obj=json.loads(path.read_text(encoding="utf8"))
        return obj if isinstance(obj,dict) else None
    except (OSError,UnicodeError,ValueError):
        return None


def age(value):
    try:
        t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if t.tzinfo is None:return None
        return max(0,int((datetime.now(timezone.utc)-t).total_seconds()))
    except (ValueError,TypeError):
        return None


def broker_account():
    doc=read(ACCOUNT_PATH)
    if (not doc or doc.get("schema")!="apex.mt5.account.v1"
            or doc.get("source")!="Deriv DEMO MT5"
            or doc.get("execution_enabled") is not False
            or doc.get("orders_placed_by_this_exporter")!=0):
        return {"available":False,"stale":True,"reason":"Unverified broker account snapshot"}
    a=doc.get("account",{})
    if a.get("mode")!="DEMO" or a.get("broker")!="Deriv" or a.get("currency")!="USD":
        return {"available":False,"stale":True,"reason":"Account identity did not match Deriv USD DEMO"}
    t=age(doc.get("generated_at_utc"))
    positions=[]
    for x in doc.get("positions",[])[:50]:
        positions.append({k:x.get(k) for k in
            ("ticket","symbol","side","volume","price_open","price_current",
            "sl","tp","profit_usd","swap_usd","opened_utc","magic")})
    trades=[]
    for x in reversed(doc.get("history_30d",[])[-50:]):
        trades.append({k:x.get(k) for k in
            ("deal","time_utc","symbol","side","entry","volume","price",
            "profit_usd","cost_usd","net_cashflow_usd")})
    contracts=[]
    for x in doc.get("contracts",[]):
        contracts.append({k:x.get(k) for k in
            ("symbol","ok","min_lot","lot_step","max_lot","point","bid","ask",
            "stops_level","freeze_level","tick_time_utc")})
    return {
        "available":True,"stale":t is None or t>420,
        "age_seconds":t,
        "generated_at_utc":doc.get("generated_at_utc"),
        "environment":"Deriv DEMO USD",
        "balance_usd":a.get("balance_usd"),
        "equity_usd":a.get("equity_usd"),
        "margin_usd":a.get("margin_usd"),
        "free_margin_usd":a.get("free_margin_usd"),
        "floating_profit_usd":a.get("floating_profit_usd"),
        "realized_today_usd":a.get("realized_today_usd"),
        "realized_30d_usd":a.get("realized_30d_usd"),
        "open_positions":a.get("open_positions"),
        "positions":positions,"recent_deals":trades,
        "history_complete":doc.get("history_complete") is True,
        "contracts":contracts,
        "execution_enabled":False,
        "historical_deals_are_not_apex_generated":True,
    }


def scanner_llm_review():
    """Advisory-only, never consumed by the broker order router."""
    doc=read(LLM_PATH)
    if not doc or doc.get("schema")!="abutron.scanner.llm.v1":
        return {"status":"PENDING","model":"qwen2.5:1.5b-instruct"},{}
    seconds=age(doc.get("checked_at_utc"))
    if seconds is None or seconds>1800:
        return {"status":"STALE","model":str(doc.get("model",""))[:48]},{}
    result={"status":("REVIEWED" if doc.get("status")=="MODEL_REVIEW_COMPLETED" else "PENDING"),
            "model":str(doc.get("model",""))[:48],
            "age_seconds":seconds,"last_symbol":doc.get("last_symbol")}
    reviews={x["symbol"]:x for x in doc.get("reviews",[])[:13]
             if isinstance(x,dict) and isinstance(x.get("symbol"),str)}
    return result,reviews


def scanner_status():
    doc=read(SCANNER_PATH)
    if (not doc or doc.get("schema")!="apex.scanner.shadow.v1"
            or doc.get("source")!="Deriv DEMO MT5"
            or doc.get("orders_enabled") is not False
            or doc.get("symbol_count")!=13):
        return {"available":False,"stale":True,"instruments":[],"candidates":0}
    t=age(doc.get("generated_at_utc"))
    # For a matching completed M5 bar, expose its single-candle close/open
    # bias independently of the scanner's multi-candle EMA/RSI direction.
    broker=read(Path("/var/lib/apex/operator-live/native-market.json"))
    broker_data={}
    if (broker and broker.get("schema")=="apex.mt5.market.v1"
        and broker.get("source")=="Deriv DEMO MT5"
        and broker.get("execution_enabled") is False):
        broker_age=age(broker.get("generated_at_utc"))
        if broker_age is not None and broker_age<=660:
            broker_data=broker.get("data",{})
    llm_state,llm_reviews=scanner_llm_review()
    instruments=[]
    for x in doc.get("instruments",[])[:13]:
        if x.get("symbol") not in DERIV_VISIBLE_SYMBOLS:continue
        ind=x.get("indicators",{})
        frame=broker_data.get(x.get("symbol"),{}).get("M5",[])
        # Scanner and broker refresh on different schedules. Match the exact
        # historical candle used by the scanner, not necessarily the newest.
        bar=next((b for b in reversed(frame) if b.get("time")==x.get("last_closed_m5")),None)
        if bar:
            candle_bias=("BUY" if bar["close"]>bar["open"] else
                         "SELL" if bar["close"]<bar["open"] else "NEUTRAL")
            candle_closed=datetime.fromtimestamp(int(bar["time"])+300,timezone.utc).isoformat()
        else:
            candle_bias="UNAVAILABLE"
            candle_closed=None
        review=llm_reviews.get(x.get("symbol"),{})
        matched=(review.get("m5_bar_time")==x.get("last_closed_m5")
                 and review.get("scanner_proposal")==x.get("proposal")
                 and x.get("proposal") in ("BUY","SELL"))
        instruments.append({
            "llm_rating":review.get("rating","PENDING") if matched else "PENDING",
            "llm_agreement":review.get("agreement") if matched else None,
            "llm_reviewed_utc":review.get("reviewed_at_utc") if matched else None,
            "llm_analysis":str(review.get("analysis",""))[:450] if matched else "",
            "symbol":x.get("symbol"),"family":x.get("family"),
            "proposal":x.get("proposal"),"reason":str(x.get("reason",""))[:180],
            "bar_time":x.get("last_closed_m5"),
            "m1_trend":ind.get("M1",{}).get("trend"),
            "m5_trend":ind.get("M5",{}).get("trend"),
            "m5_signal":x.get("m5_signal","HOLD"),
            "m5_candle_bias":candle_bias,
            "m5_candle_closed_utc":candle_closed,
            "higher_tf_signal":x.get("higher_tf_signal","MIXED"),
            "m5_rsi":ind.get("M5",{}).get("rsi14"),
            "m5_atr":ind.get("M5",{}).get("atr14"),
            "m15_trend":ind.get("M15",{}).get("trend"),
            "h1_trend":ind.get("H1",{}).get("trend"),
            "h4_trend":ind.get("H4",{}).get("trend"),
            "d1_trend":ind.get("D1",{}).get("trend"),
            "trade_ready":False,
        })
    return {"available":True,"stale":t is None or t>240,
        "age_seconds":t,"generated_at_utc":doc.get("generated_at_utc"),
        "symbols":len(instruments),"candidates":sum(x["proposal"] in ("BUY","SELL") for x in instruments),
        "strategy_status":doc.get("strategy_status"),
        "orders_enabled":False,
        "llm":llm_state,
        "instruments":instruments,
    }


def governor_status():
    doc=read(GOVERNOR_PATH)
    if (not doc or doc.get("schema")!="apex.risk.governor.v1"
            or doc.get("orders_enabled") is not False):
        return {"available":False,"stale":True,"kill_switch":"LOCKED",
                "status":"BLOCKED","blockers":["RISK_GOVERNOR_UNAVAILABLE"]}
    t=age(doc.get("generated_at_utc"))
    return {"available":True,"stale":t is None or t>240,
        "age_seconds":t,
        "status":"BLOCKED",
        "kill_switch":"LOCKED",
        "reference_usd":doc.get("risk_budget_reference_usd"),
        "risk_parameters_configured":doc.get("risk_parameters_configured") is True,
        "risk_per_trade_pct":doc.get("risk_per_trade_pct"),
        "max_daily_loss_pct":doc.get("max_daily_loss_pct"),
        "max_single_reference_usd":doc.get("max_single_order_reference_usd"),
        "headroom_estimated_usd":doc.get("estimated_account_headroom_usd"),
        "used_estimated_usd":doc.get("estimated_account_loss_used_usd"),
        "blockers":doc.get("system_blockers",[]),
        "proposals":[{"symbol":x.get("symbol"),"side":x.get("proposal"),
                      "estimated_min_lot_loss_usd":x.get("estimated_min_lot_loss_usd"),
                      "status":"BLOCKED","blockers":x.get("blockers",[])[:10]}
                     for x in doc.get("proposals",[])[:13]],
        "orders_enabled":False,
    }

DEMO_POLICY_PATH=Path("/etc/apex/trading-policy.json")
DEMO_STATUS_PATH=Path("/var/lib/apex/demo-execution/latest.json")
DEMO_USD_PROFILE_PATH=Path("/opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json")

def demo_auto_status():
    policy=read(DEMO_POLICY_PATH)
    doc=read(DEMO_STATUS_PATH)
    if not doc or doc.get("schema")!="apex.demo.execution.v1" or (not policy and doc.get("controller_version")!="basket_v1"):
        return {"available":False,"enabled":False,"stale":True,"status":"UNAVAILABLE"}
    age_s=age(doc.get("checked_at_utc"))
    # v1 basket mode is executed ONLY on the source APEX DEMO server.
    if doc.get("controller_version")=="basket_v1":
        p=read(Path("/opt/apex/runtime/APEX_BASKET_POLICY_ACTIVE_v1.json"))
        valid=(isinstance(p,dict) and p.get("schema")=="apex.demo.basket.policy.v1"
               and p.get("environment")=="DERIV_DEMO"
               and p.get("live_trading") is False
               and p.get("execution_enabled") is True
               and p.get("basket_tp_usd")==100.0
               and p.get("basket_sl_usd")==-50.0
               and p.get("per_position_sl_tp") is False
               and len(p.get("lots",{}))==13)
        profiles=([{"symbol":sym,"lots":lot,"stop_usd":None,"target_usd":None}
                    for sym,lot in sorted(p["lots"].items())] if valid else [])
        fresh=(age_s is not None and age_s<=40)
        return {"available":True,"enabled":valid and fresh,"stale":not fresh,
                "usd_profile_active":valid,"usd_profiles":profiles,
                "age_seconds":age_s,"timer_active":False,
                "status":doc.get("status"),"reason":doc.get("reason"),
                "checked_at_utc":doc.get("checked_at_utc"),
                "risk_cap_usd":None,"account_loss_cap_usd":None,
                "controller_version":"basket_v1",
                "local_execution":False,
                "basket_target_usd":100.0,"basket_stop_usd":-50.0,
                "basket_floating_pnl_usd":doc.get("basket_floating_pnl_usd"),
                "max_concurrent_positions":13,"max_positions_per_symbol":1,
                "open_apex_positions":doc.get("open_apex_positions"),
                "open_symbols":doc.get("open_symbols",[]),
                "newly_opened":doc.get("newly_opened",[]),
                "skipped":doc.get("skipped",[]),
                "broker_confirmed_orders":doc.get("broker_confirmed_orders"),
                "unreconciled_attempts":doc.get("unreconciled_attempts")}
    armed=(policy.get("environment")=="DERIV_DEMO" and policy.get("live_trading") is False
           and policy.get("automated_demo_execution") is True
           and policy.get("max_demo_loss_usd") is None
           and policy.get("max_concurrent_positions")==13
           and policy.get("max_positions_per_symbol")==1
           and doc.get("controller_version")=="multi_v3")
    profile=read(DEMO_USD_PROFILE_PATH)
    profile_valid=(isinstance(profile,dict) and
        profile.get("schema")=="apex.deriv.user_profile.review.v1" and
        profile.get("status")=="ACTIVE_DERIV_DEMO_USD_GROSS" and
        profile.get("source_sha256")=="f965a4f6cf9380a3c48401480d49b2af2b235243f82890f8fc14d01073ad1d1d" and
        profile.get("stop_loss_unit")=="USD_GROSS_BROKER_PNL" and
        profile.get("take_profit_unit")=="USD_GROSS_BROKER_PNL" and
        profile.get("live_trading_allowed") is False and
        isinstance(profile.get("rows"),list) and len(profile["rows"])==13)
    profiles=([{"symbol":row[0],"lots":row[1],"stop_usd":row[2],"target_usd":row[3]}
        for row in profile["rows"]] if profile_valid else [])
    return {"available":True,"enabled":armed,"stale":age_s is None or age_s>180,
            "usd_profile_active":profile_valid,"usd_profiles":profiles,
            "age_seconds":age_s,"timer_active":False,
            "status":doc.get("status"),"reason":doc.get("reason"),
            "checked_at_utc":doc.get("checked_at_utc"),
            "remaining_budget_usd":doc.get("remaining_budget_usd"),
            "risk_cap_usd":None,
            "account_loss_cap_usd":None,
            "controller_version":doc.get("controller_version"),
            "max_concurrent_positions":13 if armed else None,
            "max_positions_per_symbol":1 if armed else None,
            "open_apex_positions":doc.get("open_apex_positions"),
            "open_symbols":doc.get("open_symbols",[]),
            "newly_opened":doc.get("newly_opened",[]),
            "skipped":doc.get("skipped",[]),
            "broker_confirmed_orders":doc.get("broker_confirmed_orders"),
            "broker_position_ticket":doc.get("broker_position_ticket"),
            "unreconciled_attempts":doc.get("unreconciled_attempts")}

PRECHECK_PATH=Path("/var/lib/apex/mt5-market/order_precheck_latest.json")
EXECUTION_PATH=Path("/var/lib/apex/execution/latest.json")


def broker_prechecks():
    doc=read(PRECHECK_PATH)
    if (not doc or doc.get("schema")!="apex.mt5.order_precheck.v1"
            or doc.get("source")!="Deriv DEMO MT5"
            or doc.get("orders_placed")!=0
            or doc.get("execution_authorized") is not False):
        return {"available":False,"stale":True,"accepted":0,"evaluated":0,
            "orders_placed":0,"results":[]}
    t=age(doc.get("generated_at_utc"))
    results=[]
    for row in doc.get("results",[])[:26]:
        results.append({
            "symbol":row.get("symbol"),"side":row.get("side"),
            "status":row.get("status"),
            "check_retcode":row.get("check_retcode"),
            "minimum_lot":row.get("min_lot"),
            "price":row.get("price"),"sl":row.get("sl"),"tp":row.get("tp"),
            "buffered_stop_estimate_usd":row.get("model_buffered_loss_usd"),
            "checked_at_utc":row.get("checked_at_utc"),
            "reason":str(row.get("reason",""))[:160],
            "order_check_accepted":row.get("order_check_accepted") is True,
            "execution_authorized":False,
        })
    return {"available":True,"stale":t is None or t>1200,
        "age_seconds":t,"generated_at_utc":doc.get("generated_at_utc"),
        "accepted":doc.get("checked"),"evaluated":doc.get("evaluated"),
        "orders_placed":0,"execution_authorized":False,
        "results":results,
        "message":"MT5 order_check validation only; no fills, broker stops or actual loss limit certification.",
    }


def execution_preview():
    doc=read(EXECUTION_PATH)
    if (not doc or doc.get("schema")!="apex.execution.preview.v1"
            or doc.get("broker_orders_submitted")!=0
            or doc.get("execution_authorized") is not False):
        return {"available":False,"stale":True,"status":"LOCKED",
                "orders_submitted":0,"intents":[]}
    t=age(doc.get("generated_at_utc"))
    return {"available":True,"stale":t is None or t>360,
        "age_seconds":t,
        "status":doc.get("status","BLOCKED"),
        "new_intents":doc.get("new_intents",0),
        "total_intents":doc.get("ledger_total_intents",0),
        "unreconciled_orders":doc.get("unreconciled_orders",0),
        "orders_submitted":0,
        "intents":[{"symbol":x.get("symbol"),"side":x.get("side"),"state":"BLOCKED",
                    "broker_precheck_accepted":x.get("order_check_accepted") is True,
                    "buffered_stop_estimate_usd":x.get("estimated_buffered_stop_usd"),
                    "blockers":x.get("blockers",[])[:7]}
                   for x in doc.get("intents",[])[:13]],
    }
