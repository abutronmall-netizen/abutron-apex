#!/usr/bin/env python3
"""Produce a paste-safe snapshot of a running APEX.

Run this *on the box* and paste the output back. It is designed so that nothing
sensitive can ever leave the machine:

  * no secrets, no tokens, no account ids, no API keys — the API surface it reads
    (/healthz, /api/state) does not carry them, and the local files it summarises
    are the data cache and the decision journal;
  * redaction is belt-and-braces: any key matching token|secret|key|password is
    replaced before serialisation;
  * read-only: it never calls /api/control, so it cannot disturb the loop.

    python3 scripts/remote_report.py                      # localhost:8000
    python3 scripts/remote_report.py --url http://localhost:8001
    python3 scripts/remote_report.py --out report.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REDACT = ("token", "secret", "key", "password", "passwd", "authorization", "credential")
SAFE_ENV = ("APEX_ROLES", "APEX_CONFIG", "APEX_DATA_DIR", "APEX_SECRETS",
            "APEX_BAR_SECONDS", "APEX_COLLECT_MINUTES", "APEX_DERIV_TICK_SECONDS")


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if any(r in k.lower() for r in REDACT) else _scrub(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _get(url: str, timeout: int = 10):
    req = urllib.request.Request(url, headers={"User-Agent": "apex-report/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:                                             # noqa: BLE001
        return None


def _manifest(data_dir: Path) -> dict:
    for p in (data_dir / "data_cache" / "MANIFEST.json", Path("data_cache/MANIFEST.json")):
        if p.exists():
            try:
                d = json.loads(p.read_text())
                return {"updated": d.get("updated"), "disk_free_gb": d.get("disk_free_gb"),
                        "files": d.get("files", [])[:24]}
            except Exception:                                     # noqa: BLE001
                return {"error": f"unreadable: {p}"}
    return {"error": "no MANIFEST.json found — has the collector run?"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    base = a.url.rstrip("/")
    report: dict = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": os.uname().nodename if hasattr(os, "uname") else "?",
        "git_sha": _git_sha(),
        "env": {k: os.environ[k] for k in SAFE_ENV if k in os.environ},
        "python": sys.version.split()[0],
    }

    try:
        report["healthz"] = _get(f"{base}/healthz")
    except Exception as e:                                        # noqa: BLE001
        report["healthz"] = {"error": f"{type(e).__name__}: {e}"}

    try:
        st = _get(f"{base}/api/state")
        live = st.get("system", {}).get("live", {})
        acc = st.get("account", {})
        mem = st.get("memory", {})
        report["desk"] = {
            "universe": st.get("system", {}).get("universe", []),
            "mode": st.get("system", {}).get("mode"),
            "advisor": st.get("system", {}).get("advisor"),
            "bars_streamed": live.get("bars_streamed"),
            "last_ts": live.get("last_ts"),
            "equity": acc.get("equity"),
            "starting_equity": acc.get("starting_equity"),
            "leverage": acc.get("leverage"),
            "n_trades": acc.get("n_trades"),
            "positions": {k: round(float(v.get("notional", 0)), 2)
                          for k, v in (acc.get("positions") or {}).items()
                          if abs(float(v.get("notional", 0))) > 0.01},
            "targets": {k: round(float(v), 4) for k, v in (st.get("target_weights") or {}).items()},
            "regimes": {k: v.get("regime") for k, v in (st.get("regimes") or {}).items()},
            "memory": {"settled": mem.get("settled"), "pending": mem.get("pending"),
                       "narratives": mem.get("narratives", [])[:8]},
            "risk": st.get("risk"),
            "fills": [f for f in (st.get("trades") or [])[-12:]],
        }
    except Exception as e:                                        # noqa: BLE001
        report["desk"] = {"error": f"{type(e).__name__}: {e}"}

    data_dir = Path(os.environ.get("APEX_DATA_DIR") or ".")
    report["data_cache"] = _manifest(data_dir)
    report["decisions_log"] = {
        p.name: {"lines": sum(1 for _ in p.open()), "bytes": p.stat().st_size}
        for p in sorted(data_dir.glob("state/*.jsonl")) + sorted(Path("state").glob("*.jsonl"))
        if p.exists()}

    out = json.dumps(_scrub(report), indent=1, default=str)
    if a.out:
        Path(a.out).write_text(out)
        print(f"written -> {a.out} ({len(out)} bytes)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
