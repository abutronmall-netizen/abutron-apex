#!/usr/bin/env python3
"""FP DEMO broker-candle setup lifecycle. Pure, deterministic, no broker/order I/O.

A qualified M5+M15/H1/H4 BOS may wait for a *later* fresh ICT zone
retest without requiring momentum RSI to still be at breakout levels.
The original FP scanner remains the sole reader of broker-authenticated data,
and the independent AI, risk, reconciliation and native order gates remain.
"""
from __future__ import annotations
import copy
from typing import Any

SCHEMA = "abutron.fpmarkets.setup_lifecycle.v1"
MAX_EVENT_BARS = 6
MAX_MISSED_BARS = 1
M5_SECONDS = 300

def _market_htf(row: dict) -> str:
    return row.get("higher_timeframe_direction", "MIXED")

def _price_rejection(last: dict, side: str) -> bool:
    hi, lo, close, opened = (last[k] for k in ("high", "low", "close", "open"))
    span = hi - lo
    if span <= 0:
        return False
    return (close > opened and close >= lo + span * .55) if side == "BUY" else (
        close < opened and close <= lo + span * .45)

def _zone_confirmation(features: dict, last: dict, side: str, atr: float) -> tuple[bool, str]:
    """A fresh zone touch + directional close; no stale OB creation-only passes."""
    t = last["time"]
    if not _price_rejection(last, side):
        return False, "ENTRY_REJECTION_NOT_CONFIRMED"
    zones = []
    fvg = features.get("fvg_retest") or {}
    if fvg.get("direction") == side and fvg.get("retested_bar") == t:
        zones.append(("FVG_FRESH_RETEST", fvg.get("zone")))
    ob = features.get("order_block_proxy_retest") or {}
    if ob.get("direction") == side and isinstance(ob.get("created_bar"), int) and ob["created_bar"] < t:
        zones.append(("OB_PROXY_FRESH_RETEST", ob.get("zone")))
    for label, zone in zones:
        if not isinstance(zone, (list, tuple)) or len(zone) != 2:
            continue
        lower, upper = zone
        if type(lower) not in (float, int) or type(upper) not in (float, int) or not (0 < lower <= upper):
            continue
        if not (last["low"] <= upper and last["high"] >= lower):
            continue
        # Reject chasing a rapid move far beyond the actual retracement zone.
        if side == "BUY" and last["close"] > upper + .35 * atr:
            continue
        if side == "SELL" and last["close"] < lower - .35 * atr:
            continue
        return True, label
    return False, "NO_FRESH_NEARBY_FVG_OR_OB_RETEST"

def _confirm_pending(row: dict, bars: list, setup: dict, smc: Any) -> tuple[bool, str]:
    side = setup["side"]
    current = bars[-1]["time"]
    if _market_htf(row) != side:
        return False, "HIGHER_TIMEFRAME_INVALIDATED"
    event_age = (current - setup["event_bar"]) // M5_SECONDS
    if event_age <= 0 or event_age > MAX_EVENT_BARS:
        return False, "STRUCTURE_EVENT_EXPIRED"
    atr = smc.average_true_range(bars)
    if not isinstance(atr, (int, float)) or atr <= 0:
        return False, "M5_ATR_UNAVAILABLE"
    evidence = smc.evaluate(bars, side, side)
    structure = (evidence.get("features") or {}).get("structure") or {}
    flags = evidence.get("flags") or {}
    if (evidence.get("status") != "RESEARCH_CONFIRMED"
        or flags.get("higher_timeframe") is not True
        or structure.get("event_bar_time") != setup["event_bar"]
        or structure.get("direction") != side
        or structure.get("event") not in ("BOS", "CHoCH")
        or structure.get("invalidated") is True):
        return False, "ORIGINAL_SMC_STRUCTURE_NO_LONGER_VALID"
    pivot = setup["pivot"]
    if (side == "BUY" and bars[-1]["close"] < pivot - .5 * atr) or (
        side == "SELL" and bars[-1]["close"] > pivot + .5 * atr):
        return False, "BROKEN_PIVOT_INVALIDATED"
    features = evidence.get("features") or {}
    favorable=features.get("premium_discount")=="FAVORABLE"
    if favorable:
        passed, reason = _zone_confirmation(features, bars[-1], side, atr)
        if not passed:
            return False, reason
        # Original ICT dealing-range discount/premium entry is unchanged.
    else:
        # Separate ICT trend-CONTINUATION family, not a bypass of discount.
        # A fresh same-direction FVG created on/after the approved BOS must
        # retest on THIS closed M5, show rejection, and remain close to zone.
        # Unlike discount reversals, continuation FVGs may be in premium.
        fvg=features.get("fvg_retest") or {}
        last=bars[-1]
        if (row.get("m5_direction")!=side or
            fvg.get("direction")!=side or
            type(fvg.get("created_bar")) is not int or
            fvg["created_bar"]<setup["event_bar"] or
            fvg["created_bar"]>=last["time"] or
            fvg.get("retested_bar")!=last["time"]):
            return False, "CONTINUATION_FVG_EVENT_OR_M5_TREND_NOT_VALID"
        passed, reason = _zone_confirmation(features, last, side, atr)
        if not passed or reason!="FVG_FRESH_RETEST":
            return False, "CONTINUATION_FVG_RETEST_OR_REJECTION_NOT_VALID"
        zone=fvg.get("zone")
        if not isinstance(zone,(list,tuple)) or len(zone)!=2:
            return False, "CONTINUATION_FVG_ZONE_INVALID"
        low,high=zone
        if (side=="BUY" and last["close"]>high+.20*atr) or (
            side=="SELL" and last["close"]<low-.20*atr):
            return False, "CONTINUATION_ENTRY_OVEREXTENDED"
        reason="ICT_CONTINUATION_FVG_FRESH_RETEST"
    rsi = (row.get("indicators") or {}).get("M5", {}).get("rsi14")
    if type(rsi) not in (int, float) or not (35 <= rsi <= 70 if side == "BUY" else 30 <= rsi <= 65):
        return False, "M5_RSI_OVEREXTENDED_OR_UNAVAILABLE"
    return True, reason

def _new_structure(row: dict, bars: list, smc: Any) -> dict | None:
    side = row.get("proposal")
    if side not in ("BUY", "SELL") or row.get("smc", {}).get("status") != "PASS":
        return None
    evidence = smc.evaluate(bars, side, _market_htf(row))
    features = evidence.get("features") or {}
    marker = features.get("structure") or {}
    age = marker.get("age_bars")
    if (evidence.get("status") != "RESEARCH_CONFIRMED"
        or marker.get("direction") != side
        or marker.get("event") not in ("BOS", "CHoCH")
        or marker.get("invalidated") is True
        or type(marker.get("event_bar_time")) is not int
        or type(age) is not int or not 0 <= age < MAX_EVENT_BARS
        or type(marker.get("level")) not in (int, float)
        or marker["level"] <= 0):
        return None
    return {"side": side, "event_bar": marker["event_bar_time"],
            "pivot": marker["level"], "first_seen_bar": bars[-1]["time"]}

def apply(report: dict, markets: dict, previous: dict | None, smc: Any) -> tuple[dict, dict]:
    """Use only the *latest verified closed* M5 and persisted decisions.

    No historical replay is used to bootstrap order signals. An old event must
    first be staged on one observed bar, then independently confirmed on a later
    observed closed M5 bar. One account, one setup record per symbol.
    """
    if (report.get("status") not in ("FP_SCANNER_READONLY_ACTIVE", "FP_SCANNER_PARTIAL_READONLY")
        or report.get("schema") not in ("abutron.fpmarkets.apex.scanner.readonly.v1", "abutron.fpmarkets.apex.scanner.partial.readonly.v1")
        or report.get("orders_enabled") is not False):
        raise ValueError("FP_LIFECYCLE_SCANNER_NOT_AUTHENTIC")
    fingerprint = report.get("account_fingerprint")
    previous = previous or {}
    if previous and (previous.get("schema") != SCHEMA or not isinstance(previous.get("setups"), dict)):
        raise ValueError("FP_LIFECYCLE_STATE_INVALID")
    same_account = previous.get("account_fingerprint") == fingerprint
    old = previous.get("setups", {}) if same_account else {}
    output = copy.deepcopy(report)
    next_setups = {}
    for row in output["instruments"]:
        symbol = row["symbol"]
        if row.get("available") is False or symbol not in markets:
            reset = {"phase":"IDLE","last_seen_bar":0,"event_bar":None,
                     "side":None,"pivot":None,"first_seen_bar":None,
                     "note":"BROKER_SYMBOL_NOT_CURRENTLY_VERIFIED"}
            row["setup_lifecycle"] = _public(reset)
            next_setups[symbol] = reset
            continue
        bars = markets[symbol]["M5"]
        bar = bars[-1]["time"]
        stored = old.get(symbol) or {}
        if stored and (type(stored.get("last_seen_bar")) is not int
                       or stored["last_seen_bar"] > bar
                       or stored.get("phase") not in ("IDLE", "WAIT_ICT", "READY")):
            raise ValueError("FP_LIFECYCLE_STATE_TAMPER_OR_CLOCK_ROLLBACK")
        state = {"phase":"IDLE", "last_seen_bar": bar, "event_bar": None,
                 "side": None, "pivot": None, "first_seen_bar": None,
                 "note": "NO_NEW_QUALIFIED_STRUCTURE"}
        phase, prior_bar = stored.get("phase"), stored.get("last_seen_bar")
        # Same candle: never generate a new setup/re-entry; replay READY only
        # after rechecking all current evidence and expiry conditions.
        if prior_bar == bar:
            state = stored.copy()
            if phase == "READY":
                ok, note = _confirm_pending(row, bars, stored, smc)
                if ok:
                    _make_retest_candidate(row, stored, note)
                else:
                    state.update(phase="IDLE", note="READY_REVALIDATION_FAILED_"+note)
            row["setup_lifecycle"] = _public(state)
            next_setups[symbol] = state
            continue
        can_progress = (not stored or prior_bar is None or
                        0 < bar - prior_bar <= (MAX_MISSED_BARS + 1) * M5_SECONDS)
        if (can_progress and phase == "WAIT_ICT"
                and bar > stored.get("first_seen_bar", bar)
                and bar - stored["event_bar"] <= MAX_EVENT_BARS * M5_SECONDS):
            ok, note = _confirm_pending(row, bars, stored, smc)
            if ok:
                state = {**stored, "last_seen_bar": bar, "phase": "READY",
                         "note": "FRESH_ICT_RETEST_"+note,
                         "setup_family": ("CONTINUATION_FVG" if "CONTINUATION" in note
                                          else "DEEP_DISCOUNT_RETEST")}
                _make_retest_candidate(row, state, note)
            elif note in ("HIGHER_TIMEFRAME_INVALIDATED", "STRUCTURE_EVENT_EXPIRED",
                          "ORIGINAL_SMC_STRUCTURE_NO_LONGER_VALID", "BROKEN_PIVOT_INVALIDATED"):
                state = {**stored, "phase": "IDLE", "last_seen_bar": bar,
                         "note": note}
            else:
                state = {**stored, "last_seen_bar": bar, "note": note}
        # Seed only from a newly observed qualifying structure, never the
        # first scanned candle as a READY entry. A consumed event cannot re-arm.
        if state["phase"] == "IDLE" and can_progress:
            new = _new_structure(row, bars, smc)
            consumed = stored.get("event_bar")
            if new and new["event_bar"] != consumed:
                state = {**new, "phase":"WAIT_ICT", "last_seen_bar":bar,
                         "note":"WAITING_FOR_LATER_CLOSED_BAR_AND_ICT_ZONE"}
        row["setup_lifecycle"] = _public(state)
        next_setups[symbol] = state
    output["smc_ict_passed"] = sum(r["candidate_for_ai"] for r in output["instruments"])
    output["scanner_proposals"] = sum(r["proposal"] in ("BUY", "SELL") for r in output["instruments"])
    output["setup_lifecycle_version"] = SCHEMA
    output["pending_ict_setups"] = sum(s["phase"] == "WAIT_ICT" for s in next_setups.values())
    output["ready_ict_setups"] = sum(s["phase"] == "READY" for s in next_setups.values())
    next_state = {"schema": SCHEMA, "account_fingerprint": fingerprint, "setups":next_setups}
    return output, next_state

def _public(state: dict) -> dict:
    return {k:state.get(k) for k in ("phase", "side", "event_bar",
                                    "first_seen_bar", "last_seen_bar", "note",
                                    "setup_family")}

def _make_retest_candidate(row: dict, setup: dict, note: str) -> None:
    side = setup["side"]
    row["proposal"] = side
    row["reason"] = "STAGED_SMC_ICT_RETEST_" + note
    row["smc"]["status"] = "PASS"
    row["smc"]["reasons"] = []
    row["ict"]["status"] = "PASS"
    # Preserve the actual broker-candle premium/discount evidence. A genuine
    # continuation FVG has a separate, explicit entry family instead.
    if "CONTINUATION" not in note:
        row["ict"]["premium_discount"] = "FAVORABLE"
    row["ict"]["setup_family"] = ("CONTINUATION_FVG" if "CONTINUATION" in note
                                  else "DEEP_DISCOUNT_RETEST")
    row["ict"]["zone_retest"] = True
    row["candidate_for_ai"] = True
    row["final_decision"] = "HOLD"  # still requires independent model + router proof
    row["orders_enabled"] = False
    row["execution_authorized"] = False

