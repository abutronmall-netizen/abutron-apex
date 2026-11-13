"""Read-only, account-bound broker evidence for the APEX operator portal.

This is an observation layer. Native history is NOT proof that an APEX
decision caused a fill, and neither research publishers nor history
exporters place orders.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import stat

ROOT = Path("/var/lib/apex/operator-live")
FP_FILES = {
    "0512": "fp-native-history.json",
    "1636": "fp-native-history-account-80cf848587fcec6311dd93560c1c46c6.json",
    "1622": "fp-native-history-account-14eef404262094655b2040c8ced86a53.json",
}
FP_SCHEMA = "abutron.fpmarkets.native.account_history.readonly.v1"


def _read(path: Path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 100 <= before.st_size <= 2_000_000:
            raise ValueError("invalid size or type")
        data = os.read(fd, 2_000_001)
        after = os.fstat(fd)
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (
            after.st_ino, after.st_mtime_ns, after.st_size
        ):
            raise ValueError("changing source")
        doc = json.loads(data)
        if not isinstance(doc, dict):
            raise ValueError("not an object")
        return doc
    finally:
        os.close(fd)


def _age(stamp, now):
    t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timezone missing")
    age = (now - t.astimezone(timezone.utc)).total_seconds()
    if not -30 <= age <= 180:
        raise ValueError("source stale")
    return round(max(0, age))


def _stop_valid(pos, fp=False):
    try:
        side = pos.get("side")
        entry = float(pos.get("open_price"))
        stop = float(pos.get("stop_loss" if fp else "sl"))
        target = float(pos.get("take_profit" if fp else "tp"))
        return side in ("BUY", "SELL") and (
            stop < entry < target if side == "BUY" else target < entry < stop
        ) and all(abs(x) < 1e12 for x in (entry, stop, target))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False


def _base(broker, suffix, environment="DEMO"):
    return {
        "account_suffix": suffix,
        "broker": broker,
        "environment": environment,
        "status": "UNVERIFIED",
        "age_seconds": None,
        "open_positions": None,
        "positions_with_stops": None,
        "broker_deals_in_export_window": None,
        "recent_apex_acknowledged_entries": None,
        "native_risk_budget_overruns": None,
        "attribution": "NOT_VERIFIED",
        "note": "Current account-bound broker evidence unavailable",
    }


def current(root: Path = ROOT, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    rows = []
    for suffix in ("6207", "7593", "9244"):
        item = _base("Deriv", suffix)
        if suffix == "6207":
            try:
                d = _read(root / "native-status.json")
                age = _age(d["checked_at_utc"], now)
                acc = d["primary_account"]
                if not (d.get("schema") == "abutron.operator.native.v1"
                        and d.get("broker_source") == "NATIVE_BROKER_VERIFIED"
                        and acc.get("available") is True
                        and acc.get("stale") is False
                        and acc.get("environment") == "Deriv DEMO USD"
                        and isinstance(acc.get("positions"), list)
                        and acc.get("open_positions") == len(acc["positions"])):
                    raise ValueError("operator source not verified")
                positions = acc["positions"]
                item.update(
                    status="BROKER_SNAPSHOT_CURRENT",
                    age_seconds=age,
                    open_positions=len(positions),
                    positions_with_stops=sum(
                        p.get("broker_stops_attached") is True and _stop_valid(p)
                        for p in positions if isinstance(p, dict)
                    ),
                    recent_apex_acknowledged_entries=len(acc.get("recent_deals", []))
                        if isinstance(acc.get("recent_deals"), list) else None,
                    native_risk_budget_overruns=sum(
                        p.get("native_budget_exceeded") is True
                        for p in positions if isinstance(p, dict)
                    ),
                    attribution="APEX_ACKNOWLEDGED_ENTRIES_SEPARATE_FROM_OPEN_POSITIONS",
                    note="Primary-owner broker snapshot; position-to-signal attribution not asserted",
                )
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                pass
        else:
            item["note"] = "No separate account-bound Deriv broker history exposed in this portal"
        rows.append(item)

    for suffix, filename in FP_FILES.items():
        item = _base("FP Markets", suffix)
        try:
            d = _read(root / filename)
            age = _age(d["generated_at_utc"], now)
            positions = d["positions"]
            if not (d.get("schema") == FP_SCHEMA
                    and d.get("available") is True
                    and d.get("history_verified_from_mt5") is True
                    and d.get("broker") == "FP Markets"
                    and d.get("environment") == "DEMO"
                    and d.get("account_currency") == "USD"
                    and d.get("account_masked") == "••••" + suffix
                    and d.get("execution_enabled") is False
                    and d.get("orders_submitted_by_exporter") == 0
                    and isinstance(positions, list)
                    and d.get("open_positions_count") == len(positions)
                    and isinstance(d.get("trade_deals"), list)):
                raise ValueError("FP proof invalid")
            item.update(
                status="BROKER_HISTORY_CURRENT",
                age_seconds=age,
                open_positions=len(positions),
                positions_with_stops=sum(
                    _stop_valid(p, fp=True) for p in positions if isinstance(p, dict)
                ),
                broker_deals_in_export_window=d.get("broker_deals_count")
                    if isinstance(d.get("broker_deals_count"), int) else None,
                attribution="BROKER_HISTORY_NOT_APEX_ATTRIBUTED",
                note="MT5 history exporter is read-only; execution switch not inferred",
            )
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass
        rows.append(item)

    live = _base("Deriv", "0178", "LIVE")
    live["status"] = "NO_CURRENT_LIVE_BROKER_PROOF"
    live["note"] = "LIVE excluded from DEMO execution evidence; no LIVE activation asserted"
    rows.append(live)
    return {
        "schema": "abutron.apex11.broker_evidence.readonly.v1",
        "checked_at_utc": now.isoformat(),
        "risk_scope": "DISPLAY_ONLY_NO_TRADING_CONTROL",
        "strategy_attribution_verified": False,
        "portfolio_20pct_headroom_verified": False,
        "accounts": rows,
    }
