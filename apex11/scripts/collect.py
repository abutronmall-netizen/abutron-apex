#!/usr/bin/env python3
"""Continuous market-data collector.

Runs on the box, writes to the mounted volume, and is safe to kill at any moment:
every file is merged and de-duplicated by timestamp, so a restart never loses or
duplicates a bar.

    python3 scripts/collect.py --once                 # one pass (cron / systemd timer)
    python3 scripts/collect.py                        # forever, every --every minutes
    python3 scripts/collect.py --deriv-ticks 3600     # also record synthetic ticks

Outputs, all under $APEX_DATA_DIR/data_cache:
    <SYMBOL>_1D.csv      daily bars   (OKX / Nasdaq / FRED)
    <SYMBOL>.csv         hourly bars  (OKX crypto; Yahoo when reachable)
    ticks/<SYMBOL>.csv   raw Deriv ticks (only where ws.derivws.com is reachable)
    MANIFEST.json        what we hold: rows, first/last bar, last fetch, source
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.config import load_config                        # noqa: E402
from apex.paths import data_path, disk_free_gb, ensure_layout  # noqa: E402
from apex.data import real                                 # noqa: E402

MANIFEST = "MANIFEST.json"
HEADER = "ts,open,high,low,close,volume"


def _merge(path: Path, rows: np.ndarray) -> tuple[int, int]:
    """Merge new rows into a CSV by timestamp. Returns (rows_before, rows_after)."""
    if path.exists() and path.stat().st_size > 0:
        old = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    else:
        old = np.empty((0, 6))
    before = len(old)
    if len(rows) == 0:
        merged = old
    else:
        merged = np.vstack([old, rows]) if len(old) else rows
        order = np.argsort(merged[:, 0], kind="stable")
        merged = merged[order]
        _, idx = np.unique(merged[:, 0], return_index=True)   # keep first on duplicates
        merged = merged[idx]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    np.savetxt(tmp, merged, delimiter=",", header=HEADER, comments="", fmt="%.6f")
    os.replace(tmp, path)                                     # atomic swap
    return before, len(merged)


def collect_bars(cfg, refresh: bool = True) -> dict:
    """One pass over every instrument we have a real source for."""
    report = {"daily": {}, "hourly": {}, "errors": []}
    symbols = [u["symbol"] for u in cfg["universe"]]

    for sym in symbols:
        if sym in real.MAP_DAILY:
            src = real.MAP_DAILY[sym][0]
            try:
                rows = real.fetch_daily(sym, refresh=refresh)
            except Exception as e:                            # noqa: BLE001
                report["errors"].append(f"{sym} daily: {type(e).__name__}: {e}")
                continue
            if rows is None or not len(rows):
                report["errors"].append(f"{sym} daily: no data ({src})")
                continue
            before, after = _merge(data_path(f"data_cache/{sym}_1D.csv", create=True), rows)
            report["daily"][sym] = {"source": src, "rows": after, "new": after - before,
                                    "last": time.strftime("%Y-%m-%dT%H:%MZ",
                                                          time.gmtime(float(rows[-1, 0])))}
            time.sleep(1.0)

        if sym in real.MAP and real.MAP[sym][0] == "okx":
            try:
                rows = real.okx_ohlc(real.MAP[sym][1], bar="1H", bars=4320)
            except Exception as e:                            # noqa: BLE001
                report["errors"].append(f"{sym} hourly: {type(e).__name__}: {e}")
                continue
            before, after = _merge(data_path(f"data_cache/{sym}.csv", create=True), rows)
            report["hourly"][sym] = {"source": "okx", "rows": after, "new": after - before,
                                     "last": time.strftime("%Y-%m-%dT%H:%MZ",
                                                           time.gmtime(float(rows[-1, 0])))}
            time.sleep(0.5)
    return report


def collect_deriv_ticks(symbols: list[str], seconds: int) -> dict:
    """Record raw ticks for the synthetics (needs outbound access to Deriv)."""
    from apex.data.deriv_ws import DerivClient

    app_id = os.environ.get("DERIV_APP_ID", "1089")
    out = {"ticks": {}, "errors": []}
    try:
        client = DerivClient(app_id=str(app_id), token=None)
        client.start(symbols)
    except Exception as e:                                    # noqa: BLE001
        out["errors"].append(f"deriv connect: {type(e).__name__}: {e}")
        return out

    buffers: dict[str, list] = {s: [] for s in symbols}
    t_end = time.time() + seconds
    try:
        while time.time() < t_end:
            batch = client.drain_ticks(timeout=1.0)
            for sym, ts, price in batch:
                buffers.setdefault(sym, []).append([ts, price])
            time.sleep(0.5)
    finally:
        client.stop()

    for sym, rows in buffers.items():
        if not rows:
            continue
        arr = np.array(rows, dtype=float)
        path = data_path(f"data_cache/ticks/{sym}.csv", create=True)
        if path.exists() and path.stat().st_size:
            old = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
            arr = np.vstack([old, arr])
            order = np.argsort(arr[:, 0], kind="stable")
            arr = arr[order]
            _, idx = np.unique(arr[:, 0], return_index=True)
            arr = arr[idx]
        np.savetxt(path, arr, delimiter=",", header="ts,price", comments="", fmt="%.6f")
        out["ticks"][sym] = {"rows": len(arr)}
    return out


def write_manifest(report: dict) -> Path:
    """Inventory of what the collector holds — cheap to diff day over day."""
    cache = data_path("data_cache")
    files = []
    for f in sorted(cache.glob("*.csv")):
        try:
            arr = np.loadtxt(f, delimiter=",", skiprows=1, ndmin=2)
            files.append({"file": f.name, "rows": len(arr),
                          "first": time.strftime("%Y-%m-%d", time.gmtime(float(arr[0, 0]))),
                          "last": time.strftime("%Y-%m-%d", time.gmtime(float(arr[-1, 0])))}
                         if len(arr) else {"file": f.name, "rows": 0})
        except Exception:                                     # noqa: BLE001
            files.append({"file": f.name, "rows": -1, "error": "unreadable"})
    doc = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "data_dir": str(data_path(".")), "disk_free_gb": disk_free_gb(),
           "files": files, "last_run": report}
    out = cache / MANIFEST
    out.write_text(json.dumps(doc, indent=1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="APEX data collector")
    ap.add_argument("--config", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int, default=60, help="minutes between passes")
    ap.add_argument("--deriv-ticks", type=int, default=0,
                    help="also record Deriv ticks for N seconds per pass (0 = off)")
    a = ap.parse_args()

    ensure_layout()
    cfg = load_config(a.config)
    print(f"APEX collector · data_root={data_path('.')} · every={a.every}m")

    while True:
        t0 = time.time()
        report = collect_bars(cfg)
        if a.deriv_ticks:
            syms = [u["symbol"] for u in cfg["universe"]
                    if u["asset_class"] == "deriv_synthetic"]
            if syms:
                report["deriv"] = collect_deriv_ticks(syms, a.deriv_ticks)
        man = write_manifest(report)
        daily = report["daily"]
        print(f"[{time.strftime('%H:%M:%S')}] "
              f"{len(daily)} daily series, new bars: "
              f"{sum(v['new'] for v in daily.values())} · manifest {man}")
        for e in report["errors"]:
            print(f"   ! {e}")
        if a.once:
            return 0
        time.sleep(max(60, a.every * 60 - (time.time() - t0)))


if __name__ == "__main__":
    raise SystemExit(main())
