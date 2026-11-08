#!/usr/bin/env python3
"""Container entrypoint: secrets -> layout -> supervisord with the roles you asked for.

  APEX_ROLES="web,collector,trader"   any subset of the three
  PORT=10000                          the web role binds here (managed hosts inject it)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from apex.paths import data_path, disk_free_gb, ensure_layout
    from apex.secrets import SecretsError, load, status

    try:
        load()
    except SecretsError as e:
        print(f"[apex] secret load failed: {e}", file=sys.stderr)
        print("[apex] continuing in paper mode (no credentials)", file=sys.stderr)

    print(f"[apex] secrets: {json.dumps(status())}")
    print(f"[apex] layout: {json.dumps(ensure_layout())}")
    print(f"[apex] disk free: {disk_free_gb()} GB at {data_path('.')}")

    app_dir = os.environ.get("APEX_APP_DIR") or str(ROOT)
    roles = [r.strip() for r in (os.environ.get("APEX_ROLES") or "web").split(",") if r.strip()]
    port = os.environ.get("PORT", "8000")
    cfg = os.environ.get("APEX_CONFIG", "")
    cfg_arg = f"--config {cfg}" if cfg else ""

    programs = {}
    if "web" in roles:
        programs["web"] = (f"python3 scripts/run_server.py --host 0.0.0.0 --port {port} {cfg_arg}")
    if "collector" in roles:
        minutes = os.environ.get("APEX_COLLECT_MINUTES", "60")
        ticks = os.environ.get("APEX_DERIV_TICK_SECONDS", "0")
        programs["collector"] = (f"python3 scripts/collect.py --every {minutes} "
                                 f"--deriv-ticks {ticks} {cfg_arg}")
    if "trader" in roles:
        raise SystemExit("ABUTRON offline staging forbids trader service role")
        if not os.environ.get("DERIV_API_TOKEN"):
            print("[apex] trader role skipped: DERIV_API_TOKEN absent (paper only)", file=sys.stderr)
        else:
            bs = os.environ.get("APEX_BAR_SECONDS", "1.0")
            programs["trader"] = (f"python3 scripts/run_deriv.py --live-demo "
                                  f"--bar-seconds {bs} {cfg_arg}")
    if not programs:
        print("[apex] no roles enabled", file=sys.stderr)
        return 2

    conf = ["[supervisord]", "nodaemon=true", "pidfile=/tmp/supervisord.pid",
            "logfile=/dev/null", "logfile_maxbytes=0",
            "[rpcinterface:supervisor]",
            "supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface",
            "[supervisorctl]", "serverurl=http://127.0.0.1:9001", ""]
    for name, cmd in programs.items():
        conf += [f"[program:{name}]", f"command={cmd}", f"directory={app_dir}",
                 "autostart=true", "autorestart=true", "startsecs=5",
                 "startretries=1000", "stopsignal=TERM", "stopwaitsecs=20",
                 "stdout_logfile=/dev/fd/1", "stdout_logfile_maxbytes=0",
                 "redirect_stderr=true", ""]
    Path("/tmp/supervisord.conf").write_text("\n".join(conf))
    if os.environ.get("APEX_DRY_RUN"):
        print("\n".join(conf))
        return 0
    print(f"[apex] starting roles: {list(programs)} on port {port}")
    os.execvp("supervisord", ["supervisord", "-c", "/tmp/supervisord.conf"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
