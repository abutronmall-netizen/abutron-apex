"""Secret loading for hosted deployments.

The process boots with almost no rights and pulls what it needs at start:

    APEX_SECRETS=env        (default)  read straight from the environment
    APEX_SECRETS=file                  APEX_SECRETS_FILE=/run/secrets/apex.json
    APEX_SECRETS=doppler               DOPPLER_TOKEN=dp.st.xxx
    APEX_SECRETS=infisical             INFISICAL_TOKEN=... INFISICAL_PROJECT_ID=...

Values are merged into `os.environ` (never overwriting something already set, so a
host-level override always wins) and are **never logged**. `status()` reports which
names are present, not what they contain.

Nothing here is required to run the demo/paper loop: with no secrets at all the app
stays in paper mode. Only live-demo Deriv trading needs DERIV_API_TOKEN.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Dict, Optional

PROVIDERS = ("env", "file", "doppler", "infisical")
_LOADED: Dict[str, str] = {}


class SecretsError(RuntimeError):
    pass


def get(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SecretsError(
            f"{name} is not set. Provider={provider()!r}. "
            f"Populate it in your secrets manager (see docs/deploy.md) — "
            f"never commit it, never paste it into a chat."
        )
    return val


def redact(value: Optional[str]) -> str:
    """Show enough to recognise a key, not enough to use it."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}{'*' * (len(value) - 7)}{value[-4:]}"


def provider() -> str:
    return (os.environ.get("APEX_SECRETS") or "env").strip().lower()


# --------------------------------------------------------------------- providers
def _from_file() -> Dict[str, str]:
    path = os.environ.get("APEX_SECRETS_FILE")
    if not path:
        raise SecretsError("APEX_SECRETS_FILE is required when APEX_SECRETS=file")
    with open(path, "rb") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SecretsError("secrets file must be a JSON object of name -> value")
    return {str(k): str(v) for k, v in data.items()}


def _from_doppler() -> Dict[str, str]:
    token = require("DOPPLER_TOKEN")
    project = os.environ.get("DOPPLER_PROJECT", "apex")
    config = os.environ.get("DOPPLER_CONFIG", "prd")
    url = ("https://api.doppler.com/v3/configs/config/secrets/download"
           f"?format=json&project={urllib.parse.quote(project)}"
           f"&config={urllib.parse.quote(config)}")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return {str(k): str(v) for k, v in json.loads(r.read()).items()}


def _from_infisical() -> Dict[str, str]:
    token = require("INFISICAL_TOKEN")
    workspace = require("INFISICAL_PROJECT_ID")
    env = os.environ.get("INFISICAL_ENV", "prod")
    host = os.environ.get("INFISICAL_HOST", "https://app.infisical.com")
    url = (f"{host}/api/v3/secrets/raw?workspaceId={urllib.parse.quote(workspace)}"
           f"&environment={urllib.parse.quote(env)}")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.loads(r.read())
    secrets = (payload.get("secrets") or payload.get("data") or [])
    return {str(s["secretKey"]): str(s["secretValue"]) for s in secrets
            if isinstance(s, dict) and "secretKey" in s}


_FETCHERS = {"file": _from_file, "doppler": _from_doppler, "infisical": _from_infisical}


def load(provider_name: Optional[str] = None) -> Dict[str, str]:
    """Fetch secrets from the configured provider into the environment."""
    name = (provider_name or provider()).strip().lower()
    if name not in PROVIDERS:
        raise SecretsError(f"unknown APEX_SECRETS provider {name!r}; pick one of {PROVIDERS}")
    if name == "env":
        return {}
    fetch = _FETCHERS[name]
    try:
        values = fetch()
    except SecretsError:
        raise
    except Exception as e:                                        # noqa: BLE001
        raise SecretsError(f"{name} secret fetch failed: {type(e).__name__}: {e}") from e

    applied = {}
    for k, v in values.items():
        if k in os.environ:            # host-level value always wins
            continue
        os.environ[k] = v
        applied[k] = v
    _LOADED.clear()
    _LOADED.update(applied)
    return applied


def status() -> Dict[str, object]:
    """Safe to log: provider, count, and the names — never the values."""
    return {
        "provider": provider(),
        "loaded_count": len(_LOADED),
        "loaded_names": sorted(_LOADED),
        "deriv_token": redact(os.environ.get("DERIV_API_TOKEN")),
        "llm_key": redact(os.environ.get("APEX_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")),
        "has_deriv_token": bool(os.environ.get("DERIV_API_TOKEN")),
    }
