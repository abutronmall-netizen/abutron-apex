"""FP DEMO completed-candle ENTRY gate, research-only and no order functions.

Runs only on already strict EMA9/EMA21, RSI14 and M15/H1/H4 alignment.
Rejects late/chasing entries, weak or counter-directional M5 closes, high spread.
"""
import math
VERSION="FP_DEMO_ENTRY_QUALITY_V1"
MIN_BODY_ATR=0.35
MAX_EMA9_EXTENSION_ATR=0.65
MAX_SPREAD_ATR=0.30
MAX_QUOTE_DRIFT_ATR=0.55
BUY_CLOSE_LOCATION_MIN=0.55
SELL_CLOSE_LOCATION_MAX=0.45

def finite(v):
    return type(v) in (int,float) and math.isfinite(float(v))

def gate(row, frames, quote):
    """Returns (reason, measurements). 'PASS' never grants order authority."""
    if row.get("proposal") not in ("BUY","SELL"):
        return "RESEARCH_NOT_QUALIFIED",{}
    try:
        i=row["indicators"]["M5"]
        raw=frames["M5"][-1]
        side=row["proposal"]
        required=(i["atr14"],i["ema9"],raw["open"],raw["high"],
                  raw["low"],raw["close"],quote["bid"],quote["ask"])
        if not all(finite(v) for v in required):
            return "UNVERIFIED_PRICE_OR_ATR",{}
        atr,ema9,o,high,low,close,bid,ask=map(float,required)
        if (atr<=0 or low<=0 or high<=low or not low<=min(o,close)
            or not max(o,close)<=high or bid<=0 or ask<bid
            or type(raw.get("time")) is not int
            or raw["time"]!=row.get("m5_closed_bar")):
            return "CANDLE_OR_QUOTE_INVALID",{}
        spread=(ask-bid)/atr
        location=(close-low)/(high-low)
        signed_body=(close-o)/atr
        extension=abs(close-ema9)/atr
        mid=(bid+ask)/2
        drift=abs(mid-close)/atr
        measurements={"m5_body_atr":round(signed_body,4),
                      "ema9_extension_atr":round(extension,4),
                      "spread_atr":round(spread,4),
                      "quote_drift_atr":round(drift,4),
                      "m5_close_location":round(location,4)}
        if spread>MAX_SPREAD_ATR:
            return "SPREAD_EXCEEDS_M5_VOLATILITY_BUDGET",measurements
        if drift>MAX_QUOTE_DRIFT_ATR:
            return "PRICE_MOVED_SINCE_CLOSED_M5",measurements
        if extension>MAX_EMA9_EXTENSION_ATR:
            return "LATE_CHASED_ENTRY_TOO_FAR_FROM_EMA9",measurements
        if abs(signed_body)<MIN_BODY_ATR:
            return "WEAK_CLOSED_M5_BODY",measurements
        if side=="BUY" and (signed_body<=0 or location<BUY_CLOSE_LOCATION_MIN):
            return "BUY_NOT_CONFIRMED_BY_CLOSED_M5",measurements
        if side=="SELL" and (signed_body>=0 or location>SELL_CLOSE_LOCATION_MAX):
            return "SELL_NOT_CONFIRMED_BY_CLOSED_M5",measurements
        return "PASS",measurements
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,AttributeError):
        return "ENTRY_EVIDENCE_UNAVAILABLE",{}
