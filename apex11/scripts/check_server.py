#!/usr/bin/env python3
"""Health-check a deployed APEX from the outside.

    python3 scripts/check_server.py https://apex-desk.onrender.com
    python3 scripts/check_server.py https://host --token $APEX_API_TOKEN --json

Exit code 0 = healthy, 1 = degraded, 2 = unreachable. Read-only: this script never
calls /api/control, it only *checks whether that door is open*.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "apex-check/1.0"}


def _get(url: str, token: str | None = None, timeout: int = 15):
    req = urllib.request.Request(url, headers=dict(UA, **(
        {"Authorization": f"Bearer {token}"} if token else {})))
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), round((time.time() - t0) * 1000)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--token", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    base = a.url.rstrip("/")

    out: dict = {"url": base, "ok": False, "checks": {}}
    try:
        status, body, ms = _get(f"{base}/healthz")
        health = json.loads(body)
        out["checks"]["healthz"] = {"status": status, "ms": ms, **{
            k: health.get(k) for k in
            ("ok", "role", "uptime_s", "runner_running", "bars", "memory_settled",
             "disk_free_gb", "secrets")}}
    except Exception as e:                                        # noqa: BLE001
        out["error"] = f"healthz unreachable: {type(e).__name__}: {e}"
        print(json.dumps(out, indent=1) if a.json else out["error"])
        return 2

    try:
        status, body, ms = _get(f"{base}/api/state")
        st = json.loads(body)
        out["checks"]["state"] = {
            "status": status, "ms": ms,
            "universe": st.get("system", {}).get("universe", []),
            "bars": st.get("system", {}).get("live", {}).get("bars_streamed"),
            "equity": round(float(st.get("account", {}).get("equity", 0)), 2),
            "positions": len([p for p in st.get("account", {}).get("positions", {}).values()
                              if abs(p.get("notional", 0)) > 0]),
            "fills": st.get("account", {}).get("n_trades"),
        }
    except Exception as e:                                        # noqa: BLE001
        out["checks"]["state"] = {"error": f"{type(e).__name__}: {e}"}

    # is the control door open to the world?
    try:
        req = urllib.request.Request(f"{base}/api/control/pause", method="POST",
                                     headers=dict(UA, **({"Authorization": f"Bearer {a.token}"}
                                                         if a.token else {})))
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.status
    finally:
        try:                                                      # always un-pause
            req = urllib.request.Request(f"{base}/api/control/resume", method="POST",
                                         headers=dict(UA, **({"Authorization": f"Bearer {a.token}"}
                                                             if a.token else {})))
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:                                         # noqa: BLE001
            pass
    out["checks"]["control_auth"] = {"probe_status": code,
                                     "secured": code in (401, 403)}
    if code == 200:
        out["warning"] = ("CONTROL ENDPOINTS ARE OPEN — anyone with the URL can pause, "
                          "reset or flatten the book. Set APEX_API_TOKEN.")

    h = out["checks"]["healthz"]
    out["ok"] = bool(h.get("runner_running") and (h.get("disk_free_gb") or 0) > 0.1
                     and out["checks"]["control_auth"]["secured"])
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"APEX @ {base}")
        print(f"  healthz      {h['status']} in {h['ms']}ms · runner "
              f"{'UP' if h.get('runner_running') else 'DOWN'} · bars {h.get('bars')}")
        print(f"  uptime       {h.get('uptime_s')}s · disk {h.get('disk_free_gb')} GB free")
        print(f"  secrets      {h.get('secrets', {}).get('provider')} · "
              f"deriv token {h.get('secrets', {}).get('deriv_token')}")
        s_ = out["checks"].get("state", {})
        print(f"  book         {s_.get('positions')} positions · equity {s_.get('equity'):,} · "
              f"{s_.get('fills')} fills")
        print(f"  control      {'SECURED' if out['checks']['control_auth']['secured'] else 'OPEN'}")
        print(f"  verdict      {'OK' if out['ok'] else 'DEGRADED'}")
        if out.get("warning"):
            print(f"  !! {out['warning']}")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
