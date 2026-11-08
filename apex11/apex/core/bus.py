"""Tiny synchronous event bus + append-only JSONL audit log."""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._lock = threading.RLock()
        self.ring: Deque[Dict[str, Any]] = deque(maxlen=2000)

    def subscribe(self, topic: str, fn: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self._subs.setdefault(topic, []).append(fn)

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        evt = {"topic": topic, "ts": time.time(), **payload}
        with self._lock:
            self.ring.append(evt)
            subs = list(self._subs.get(topic, ())) + list(self._subs.get("*", ()))
        for fn in subs:
            try:
                fn(evt)
            except Exception:  # never let a subscriber kill the trading loop
                pass

    def recent(self, topic: str | None = None, n: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self.ring)
        if topic:
            items = [e for e in items if e["topic"] == topic]
        return items[-n:]


class JsonlLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, obj: Dict[str, Any]) -> None:
        line = json.dumps(obj, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out


BUS = EventBus()
