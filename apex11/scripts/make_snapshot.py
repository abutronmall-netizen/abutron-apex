#!/usr/bin/env python3
"""Freeze the live desk into a single self-contained HTML file.

The result renders with zero network access: the engine state is embedded, and the
dashboard falls back to it when its SSE/fetch calls fail (e.g. opened from disk,
or previewed in a sandboxed iframe).

    python3 scripts/make_snapshot.py --url http://localhost:8000 --out docs/dashboard_snapshot.html
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--out", default=str(ROOT / "docs" / "dashboard_snapshot.html"))
    a = ap.parse_args()

    with urllib.request.urlopen(f"{a.url}/api/state", timeout=20) as r:
        state = json.loads(r.read().decode())
    html = (ROOT / "ui" / "dashboard.html").read_text(encoding="utf-8")

    boot = (
        "<script>\n"
        "window.SNAPSHOT_MODE = true;\n"
        f"window.EMBEDDED_STATE = {json.dumps(state)};\n"
        "</script>\n"
    )
    html = html.replace("<script>\n\"use strict\";", boot + "<script>\n\"use strict\";", 1)

    html = html.replace(
        """async function poll() {
  try {
    const r = await fetch("api/state", {cache: "no-store"});
    render(await r.json());
  } catch (e) { /* server starting */ }
}""",
        """let liveOk = false;
async function poll() {
  try {
    const r = await fetch("api/state", {cache: "no-store"});
    const j = await r.json();
    liveOk = true;
    render(j);
  } catch (e) {
    if (!liveOk && window.EMBEDDED_STATE) render(window.EMBEDDED_STATE);
  }
}""")

    html = html.replace(
        """connect();
poll();""",
        """if (window.EMBEDDED_STATE) render(window.EMBEDDED_STATE);
if (!window.SNAPSHOT_MODE) connect();
poll();""")

    html = html.replace(
        """  $("footerRight").textContent = `mode ${sys.mode} · advisor ${ad.mode} · uptime ${live.uptime_s || 0}s`;""",
        """  $("footerRight").textContent = `mode ${sys.mode} · advisor ${ad.mode} · uptime ${live.uptime_s || 0}s` +
    (window.SNAPSHOT_MODE && !liveOk ? " · frozen snapshot" : "");""")

    Path(a.out).write_text(html, encoding="utf-8")
    kb = len(html.encode()) / 1024
    print(f"wrote {a.out} ({kb:.0f} KB) · bars {state['system']['live'].get('bars_streamed')} · "
          f"eq {state['account']['equity']:,.0f} · memory settled {state.get('memory', {}).get('settled')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
