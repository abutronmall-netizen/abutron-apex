"""Configuration loading: YAML file + environment overrides."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


class Cfg(dict):
    """dict with attribute-style access, recursively wrapped."""

    def __getattr__(self, item: str) -> Any:
        try:
            v = self[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc
        return Cfg(v) if isinstance(v, dict) else v

    def get_cfg(self, key: str, default: Any = None) -> Any:
        v = self.get(key, default)
        return Cfg(v) if isinstance(v, dict) else v


def _deep_update(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


ENV_MAP = {
    "APEX_MODE": ("system", "mode"),
    "APEX_EQUITY": ("account", "starting_equity"),
    "APEX_SEED": ("system", "seed"),
    "APEX_LLM_ENABLED": ("llm", "enabled"),
    "APEX_LLM_MODEL": ("llm", "model"),
    "APEX_LLM_BASE_URL": ("llm", "base_url"),
    "APEX_TARGET_VOL": ("risk", "target_annual_vol"),
    "APEX_PORT": ("api", "port"),
}


def _coerce(raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        return type(current)(raw)
    return raw


def load_config(path: str | os.PathLike | None = None, overrides: Dict[str, Any] | None = None) -> Cfg:
    p = Path(path or os.environ.get("APEX_CONFIG") or DEFAULT_CONFIG)
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if overrides:
        _deep_update(raw, overrides)
    for env_key, (sect, key) in ENV_MAP.items():
        if env_key in os.environ:
            cur = raw.get(sect, {}).get(key)
            raw.setdefault(sect, {})[key] = _coerce(os.environ[env_key], cur)
    return Cfg(raw)


def universe_map(cfg: Cfg) -> Dict[str, Dict[str, Any]]:
    return {u["symbol"]: dict(u) for u in cfg["universe"]}


def symbols(cfg: Cfg, asset_class: str | None = None) -> List[str]:
    out = []
    for u in cfg["universe"]:
        if asset_class and u.get("asset_class") != asset_class:
            continue
        out.append(u["symbol"])
    return out
