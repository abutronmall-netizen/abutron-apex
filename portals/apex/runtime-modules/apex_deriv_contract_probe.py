"""Deriv DEMO contract-loss diagnostic; no order functions are invoked.

Reads the 13 broker symbols from the APEX MT5 market snapshot. It computes
ATR-based hypothetical stops and uses official MT5 order_calc_profit only.
This is not order approval or an enforceable USD loss ceiling.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5

MT5_EXE = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MARKET = Path("/var/lib/apex/mt5-market/deriv_demo_bars.json")


def atr14(bars):
    tr = []
    for i in range(1, len(bars)):
        prev = float(bars[i - 1]["close"])
        cur = bars[i]
        high, low = float(cur["high"]), float(cur["low"])
        tr.append(max(high - low, abs(high - prev), abs(low - prev)))
    if len(tr) < 14:
        raise ValueError("Insufficient H1 bars for ATR")
    return sum(tr[-14:]) / 14


def main():
    data = json.loads(MARKET.read_text(encoding="utf-8"))
    if (data.get("source") != "Deriv DEMO MT5"
            or data.get("schema") != "apex.mt5.market.v1"
            or data.get("execution_enabled") is not False):
        raise RuntimeError("Snapshot source invalid")
    if len(data.get("data", {})) != 13:
        raise RuntimeError("Expected 13 Deriv broker symbols")
    generated = datetime.fromisoformat(data["generated_at_utc"])
    if generated.tzinfo is None or abs((datetime.now(timezone.utc) - generated).total_seconds()) > 900:
        raise RuntimeError("Market snapshot stale")
    if not mt5.initialize(MT5_EXE, timeout=16000):
        raise RuntimeError("Broker terminal unavailable")
    try:
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if (account is None or terminal is None or not terminal.connected
                or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO
                or "deriv" not in str(account.company).lower()
                or "demo" not in str(account.server).lower()
                or str(account.currency).upper() != "USD"):
            raise RuntimeError("Only authenticated Deriv USD DEMO permitted")
        out = []
        for name, frames in data["data"].items():
            entry = {"symbol": name, "verified": False}
            try:
                bars = frames.get("H1")
                if not bars or len(bars) < 30:
                    raise ValueError("Missing broker H1 history")
                sym = mt5.symbol_info(name)
                tick = mt5.symbol_info_tick(name)
                if sym is None or tick is None:
                    raise ValueError("Missing broker symbol specifications or quote")
                a = atr14(bars)
                ask, bid = float(tick.ask), float(tick.bid)
                if not 0 < bid <= ask or not math.isfinite(a) or a <= 0:
                    raise ValueError("Invalid broker quote or ATR")
                vol = float(sym.volume_min)
                if (vol <= 0 or not math.isfinite(vol)
                        or vol > float(sym.volume_max)
                        or float(sym.volume_step) <= 0):
                    raise ValueError("Invalid minimum broker volume")
                spread = ask - bid
                distance = max(2.0 * a, 3.0 * spread,
                               (int(sym.trade_stops_level) + 2) * float(sym.point))
                buy_sl = round(ask - distance, int(sym.digits))
                sell_sl = round(bid + distance, int(sym.digits))
                if buy_sl <= 0 or sell_sl <= bid:
                    raise ValueError("Invalid protective stops")
                buy = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, name, vol, ask, buy_sl)
                sell = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, name, vol, bid, sell_sl)
                if buy is None or sell is None:
                    raise ValueError("Official MT5 P/L calculation unavailable")
                buy_loss, sell_loss = max(0.0, -float(buy)), max(0.0, -float(sell))
                if not all(map(math.isfinite, (buy_loss, sell_loss))):
                    raise ValueError("Nonfinite USD loss calculation")
                entry.update({"verified": True, "minimum_lot": vol,
                              "buy_sl_est_usd": round(buy_loss, 2),
                              "sell_sl_est_usd": round(sell_loss, 2),
                              "h1_atr": round(a, int(sym.digits)),
                              "spread_points": round(spread / float(sym.point), 1)})
            except (ValueError, TypeError, AttributeError) as ex:
                entry["reason"] = str(ex)[:130]
            out.append(entry)
        result = {"status": "inspection_only", "orders_placed": 0,
                  "source": "Deriv USD DEMO MT5", "budget_reference_usd": None,
                  "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                  "calculated_count": sum(r["verified"] for r in out),
                  "instruments": out}
        print(json.dumps(result, allow_nan=False), flush=True)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "blocked", "orders_placed": 0,
                          "error_type": type(exc).__name__,
                          "error": str(exc)[:150]}), flush=True)
        raise SystemExit(1)
