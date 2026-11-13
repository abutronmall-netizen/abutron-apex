"""Official MetaTrader 5 broker telemetry for APEX on Deriv DEMO.

Read-only. Deliberately does not import or invoke any MT5 trading action.
Scrubs account login, credentials and arbitrary broker comments from output.
"""
import json
import math
import sys
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOLS = (
    "Volatility 10 Index.0", "Volatility 25 Index.0", "Volatility 50 Index.0",
    "Volatility 75 Index.0", "Volatility 100 Index.0",
    "Crash 150 Index.0", "Crash 300 Index.0", "Crash 600 Index.0",
    "Crash 1000 Index.0", "Boom 150 Index.0", "Boom 300 Index.0",
    "Boom 600 Index.0", "Boom 1000 Index.0",
)


def num(val, scale=2):
    f=float(val)
    if not math.isfinite(f):
        raise ValueError("Nonfinite broker account metric")
    return round(f,scale)


def main():
    if not mt5.initialize(TERMINAL, timeout=15000):
        raise RuntimeError("MT5 broker session unavailable")
    try:
        a=mt5.account_info()
        t=mt5.terminal_info()
        if (a is None or t is None or not t.connected
                or a.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO
                or "deriv" not in str(a.company).lower()
                or "demo" not in str(a.server).lower()
                or str(a.currency).upper() != "USD"):
            raise RuntimeError("Only authenticated Deriv USD DEMO is allowed")
        when=datetime.now(timezone.utc)
        active=mt5.positions_get()
        if active is None:raise RuntimeError("Could not reconcile active broker positions")
        positions=[]
        for p in active:
            positions.append({
                "ticket":int(p.ticket),"symbol":str(p.symbol)[:80],
                "side":"BUY" if p.type==mt5.POSITION_TYPE_BUY else "SELL",
                "volume":num(p.volume,4),"price_open":num(p.price_open,6),
                "price_current":num(p.price_current,6),
                "sl":num(p.sl,6),"tp":num(p.tp,6),
                "profit_usd":num(p.profit),"swap_usd":num(p.swap),
                "magic":int(p.magic),"opened_utc":datetime.fromtimestamp(int(p.time),timezone.utc).isoformat(),
            })
        begin=when-timedelta(days=30)
        deals=mt5.history_deals_get(begin,when)
        if deals is None:raise RuntimeError("MT5 deal history unavailable")
        # Include all broker deal entries for traceability; don't confuse deposits with P&L.
        entries=[]
        exit_types={mt5.DEAL_ENTRY_OUT,mt5.DEAL_ENTRY_INOUT,mt5.DEAL_ENTRY_OUT_BY}
        for deal in deals:
            if int(deal.type) not in (mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL):
                continue
            realized=int(deal.entry) in exit_types
            pnl=num(deal.profit+deal.swap+deal.commission+deal.fee)
            entries.append({
                "deal":int(deal.ticket),"position_id":int(deal.position_id),
                "time_utc":datetime.fromtimestamp(int(deal.time),timezone.utc).isoformat(),
                "symbol":str(deal.symbol)[:80],
                "side":"BUY" if deal.type==mt5.DEAL_TYPE_BUY else "SELL",
                "entry":"EXIT" if realized else "ENTRY",
                "volume":num(deal.volume,4),
                "price":num(deal.price,6),
                "net_cashflow_usd":pnl,
                "profit_usd":num(deal.profit),
                "cost_usd":num(deal.swap+deal.commission+deal.fee),
                "magic":int(deal.magic),
            })
        entries.sort(key=lambda x:(x["time_utc"],x["deal"]))
        today=when.date()
        # Include entry-side commission, closing profit, swap and fees from
        # every trade deal. Do not net winning trades against the gross-loss cap.
        realized_today=sum(x["net_cashflow_usd"] for x in entries if x["time_utc"][:10]==str(today))
        month_realized=sum(x["net_cashflow_usd"] for x in entries)
        gross_negative_today=sum(max(0.0,-x["net_cashflow_usd"]) for x in entries
                                 if x["time_utc"][:10]==str(today))
        contracts=[]
        for name in SYMBOLS:
            s=mt5.symbol_info(name)
            tick=mt5.symbol_info_tick(name)
            if s is None or tick is None:
                contracts.append({"symbol":name,"ok":False})
                continue
            contracts.append({
                "symbol":name,"ok":True,"min_lot":num(s.volume_min,4),
                "lot_step":num(s.volume_step,4),"max_lot":num(s.volume_max,4),
                "trade_mode":int(s.trade_mode),"execution_mode":int(s.trade_exemode),
                "stops_level":int(s.trade_stops_level),"freeze_level":int(s.trade_freeze_level),
                "point":num(s.point,9),"digits":int(s.digits),
                "bid":num(tick.bid,6),"ask":num(tick.ask,6),
                "tick_time_utc":datetime.fromtimestamp(int(tick.time),timezone.utc).isoformat(),
            })
        result={
            "schema":"apex.mt5.account.v1",
            "source":"Deriv DEMO MT5",
            "generated_at_utc":when.isoformat(),
            "account":{"mode":"DEMO","broker":"Deriv","currency":"USD",
                "balance_usd":num(a.balance),"equity_usd":num(a.equity),
                "margin_usd":num(a.margin),"free_margin_usd":num(a.margin_free),
                "floating_profit_usd":num(a.profit),
                "open_positions":len(positions),
                "realized_today_usd":num(realized_today),
                "realized_30d_usd":num(month_realized),
                "gross_negative_deal_cashflows_today_usd":num(gross_negative_today),
                "allow_trading_terminal":bool(t.trade_allowed),
                "allow_trading_account":bool(a.trade_allowed),
                "allow_expert_terminal":bool(t.tradeapi_disabled is False),
                },
            "positions":positions,
            "history_30d":entries[-1500:],
            "history_complete":len(entries)<=1500,
            "contracts":contracts,
            "orders_placed_by_this_exporter":0,
            "execution_enabled":False,"live_enabled":False,
        }
        print(json.dumps(result,allow_nan=False,separators=(",",":")),flush=True)
    finally:
        mt5.shutdown()


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"schema":"apex.mt5.account.v1","status":"BLOCKED",
            "reason":type(exc).__name__,"orders_placed_by_this_exporter":0,
            "execution_enabled":False}),flush=True)
        raise SystemExit(1)
