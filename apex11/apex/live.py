"""Live paper-trading runner.

Streams bars into the engine at an accelerated clock so the dashboard shows a
real decision cycle unfolding in seconds rather than hours. Swap the DataSource
for `DerivFeed` / `AlpacaFeed` and the same loop trades a real demo account.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from .config import Cfg, load_config
from .core.bus import BUS
from .data.synthetic import SyntheticSource
from .engine import ApexEngine


class LiveRunner:
    def __init__(self, cfg: Optional[Cfg] = None, bar_seconds: float = 1.2,
                 warmup_bars: int = 400, seed: Optional[int] = None) -> None:
        self.cfg = cfg or load_config()
        self.bar_seconds = float(bar_seconds)
        self.warmup_bars = int(warmup_bars)
        self.engine = ApexEngine(self.cfg, mode="paper", seed=seed)
        self.source = SyntheticSource(self.cfg, seed=seed)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.running = False
        self.bars = 0
        self.started_at = time.time()

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="apex-live", daemon=True)
        self._thread.start()
        self.running = True

    def stop(self) -> None:
        self._stop.set()
        self.running = False

    def _loop(self) -> None:
        hist = self.source.warmup(self.warmup_bars)
        for i in range(self.warmup_bars):
            bars = {s: hist[s][i] for s in hist if i < len(hist[s])}
            self.engine.warmup(bars)
        BUS.publish("status", {"msg": "warmup complete", "bars": self.warmup_bars})

        stream = self.source.stream()
        while not self._stop.is_set():
            t0 = time.time()
            try:
                bars = next(stream)
            except StopIteration:
                break
            if not bars:
                continue
            self.engine.step(bars)
            self.bars += 1
            BUS.publish("bar", {"index": self.engine.index, "equity": self.engine.broker.equity})
            elapsed = time.time() - t0
            if self.bar_seconds > elapsed:
                self._stop.wait(self.bar_seconds - elapsed)

    # ------------------------------------------------------------------
    def state(self) -> Dict[str, Any]:
        st = self.engine.state()
        st["system"]["live"] = {
            "running": self.running,
            "bars_streamed": self.bars,
            "bar_seconds": self.bar_seconds,
            "uptime_s": round(time.time() - self.started_at, 1),
        }
        return st

    def control(self, action: str) -> Dict[str, Any]:
        if action == "pause":
            self.engine.pause(True)
        elif action == "resume":
            self.engine.pause(False)
        elif action == "flatten":
            fills = self.engine.flatten()
            return {"ok": True, "flattened": len(fills)}
        elif action == "reset-risk":
            self.engine.resume_risk()
        elif action == "start":
            self.start()
        elif action == "stop":
            self.stop()
        else:
            return {"ok": False, "error": f"unknown action {action}"}
        return {"ok": True, "action": action, "paused": self.engine.paused}
