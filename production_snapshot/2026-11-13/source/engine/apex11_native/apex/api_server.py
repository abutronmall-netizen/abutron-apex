"""Alias module so `from apex.api_server import app` works."""
from .api.server import app, main  # noqa: F401

__all__ = ["app", "main"]
