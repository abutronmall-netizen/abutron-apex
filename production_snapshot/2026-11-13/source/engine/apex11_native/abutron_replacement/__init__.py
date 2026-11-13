"""ABUTRON replacement package exports, loaded only when explicitly needed.

Do not initialize the APEX model or its LLM when importing guardian-only
modules. Keep the public offline bridge interface available for tests and
read-only research. This module grants no order authority.
"""
from importlib import import_module

__all__ = ("AbutronApex11SignalBridge", "CandleRejected")

def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(".bridge", __name__), name)

def __dir__():
    return sorted(set(globals()) | set(__all__))
