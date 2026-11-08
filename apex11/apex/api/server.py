"""FastAPI control plane + live dashboard for APEX."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ..config import load_config
from ..paths import data_path, disk_free_gb
from ..live import LiveRunner

ROOT = Path(__file__).resolve().parent.parent.parent
UI = ROOT / "ui" / "dashboard.html"
RESULTS = data_path("results")

runner: Optional[LiveRunner] = None
CFG = load_config()
STARTED = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner
    if runner is None:
        runner = LiveRunner(CFG, bar_seconds=float(CFG["api"].get("bar_seconds", 1.2)))
        runner.start()
    yield
    if runner:
        runner.stop()


app = FastAPI(title="APEX", version="1.0.0", lifespan=lifespan)

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


async def require_control_auth(request: Request,
                               authorization: Optional[str] = Header(None)) -> None:
    """Authorise state-changing calls.

    Set APEX_API_TOKEN and every /api/control call must present it as
    `Authorization: Bearer <token>`. With no token configured, control is only
    accepted from loopback — a public deployment therefore fails *closed*.
    """
    token = os.environ.get("APEX_API_TOKEN")
    if token:
        provided = ""
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        provided = provided or request.query_params.get("token", "")
        if not provided or not hmac.compare_digest(provided, token):
            raise HTTPException(status_code=401, detail="invalid or missing API token")
        return
    host = (request.client.host if request.client else "") or ""
    if host not in LOOPBACK:
        raise HTTPException(
            status_code=403,
            detail=("control endpoints are closed on this deployment: set APEX_API_TOKEN "
                    "and send it as 'Authorization: Bearer <token>'"),
        )


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(UI.read_text(encoding="utf-8") if UI.exists()
                        else "<h1>APEX</h1><p>dashboard.html missing</p>")


@app.get("/api/state")
async def state() -> JSONResponse:
    if runner is None:
        return JSONResponse({"error": "runner not started"}, status_code=503)
    return JSONResponse(runner.state())


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "ts": time.time(),
            "running": bool(runner and runner.running),
            "bars": runner.bars if runner else 0}


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness + readiness for the platform health check.

    200 when the loop is stepping and the disk has room; 503 otherwise, so a
    managed host restarts a wedged process instead of serving a dead dashboard.
    """
    from ..secrets import status as secrets_status

    info: Dict[str, Any] = {
        "role": "web",
        "ts": time.time(),
        "uptime_s": round(time.time() - STARTED, 1),
        "runner_started": runner is not None,
        "runner_running": bool(runner and runner.running),
        "bars": runner.bars if runner else 0,
        "memory_settled": getattr(runner.engine.memory, "settled", None) if runner and runner.engine else None,
        "disk_free_gb": disk_free_gb(),
        "secrets": secrets_status(),
        "data_dir": str(data_path(".")),
    }
    info["ok"] = bool(info["runner_running"] and info["disk_free_gb"] > 0.1)
    return JSONResponse(info, status_code=200 if info["ok"] else 503)


@app.get("/api/backtest")
async def backtest() -> JSONResponse:
    p = RESULTS / "report.json"
    if not p.exists():
        return JSONResponse({"available": False})
    try:
        d = json.loads(p.read_text())
    except json.JSONDecodeError:
        return JSONResponse({"available": False})
    m = d.get("metrics", {})
    return JSONResponse({
        "available": True,
        "config": d.get("config", {}),
        "metrics": m,
        "equity_curve": d.get("equity_curve", [])[:: max(1, len(d.get("equity_curve", [])) // 400)][:400],
    })


@app.post("/api/control/{action}", dependencies=[Depends(require_control_auth)])
async def control(action: str) -> JSONResponse:
    if runner is None:
        return JSONResponse({"ok": False, "error": "runner not started"}, status_code=503)
    return JSONResponse(runner.control(action))


@app.get("/api/stream")
async def stream(request: Request, hz: float = 2.0) -> StreamingResponse:
    """Server-sent events: pushes the full engine state at ~hz frames/second."""

    async def gen():
        last = 0
        while True:
            if await request.is_disconnected():
                break
            now = time.time()
            if now - last >= 1.0 / max(hz, 0.2):
                last = now
                try:
                    payload = runner.state() if runner else {"error": "no runner"}
                except Exception as exc:  # pragma: no cover
                    payload = {"error": str(exc)}
                yield f"data: {json.dumps(payload, default=str)}\n\n"
            await asyncio.sleep(0.05)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def main() -> None:
    import uvicorn
    api = CFG["api"]
    uvicorn.run(app, host=str(api.get("host", "0.0.0.0")), port=int(api.get("port", 8000)),
                log_level="info")


if __name__ == "__main__":
    main()
