#!/usr/bin/env python3
"""Start the APEX dashboard + live paper-trading loop."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apex.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="APEX dashboard")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--bar-seconds", type=float, default=1.2,
                    help="wall-clock seconds per simulated bar")
    ap.add_argument("--config", default=None, help="e.g. config/deriv_only.yaml")
    ap.add_argument("--no-live", action="store_true", help="serve the API only")
    a = ap.parse_args()

    if a.config:
        import os
        os.environ["APEX_CONFIG"] = a.config
    cfg = load_config(a.config)
    port = a.port or int(cfg["api"].get("port", 8000))
    host = a.host or str(cfg["api"].get("host", "0.0.0.0"))

    import uvicorn
    from apex import api_server as srv  # noqa: F401  (ensures module import)
    from apex.api.server import app, CFG  # type: ignore
    if a.bar_seconds:
        CFG["api"]["bar_seconds"] = a.bar_seconds
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
