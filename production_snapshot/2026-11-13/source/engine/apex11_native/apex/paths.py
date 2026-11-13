"""Filesystem layout, overridable so the app can run from a container with a volume.

Everything the process *writes* (state, results, data cache) goes through here.
Set `APEX_DATA_DIR=/var/data` and the whole mutable surface moves onto the mounted
disk while the code stays read-only.
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DATA = Path(os.environ.get("APEX_DATA_DIR") or _ROOT).resolve()

#: keys that must live on the volume
MUTABLE = ("state", "results", "data_cache", "logs")


def data_root() -> Path:
    return _DATA


def data_path(path: str | os.PathLike, *, create: bool = False) -> Path:
    """Resolve a (usually relative) mutable path against the data root."""
    p = Path(path)
    if p.is_absolute():
        out = p
    else:
        out = _DATA / p
    if create:
        out.parent.mkdir(parents=True, exist_ok=True)
    return out


def ensure_layout() -> dict[str, str]:
    """Create the mutable directories and report where they landed."""
    made = {}
    for name in MUTABLE:
        d = _DATA / name
        d.mkdir(parents=True, exist_ok=True)
        made[name] = str(d)
    return made


def disk_free_gb(path: str | os.PathLike | None = None) -> float:
    import shutil

    target = Path(path) if path else _DATA
    try:
        return round(shutil.disk_usage(str(target)).free / 1e9, 3)
    except OSError:
        return -1.0
