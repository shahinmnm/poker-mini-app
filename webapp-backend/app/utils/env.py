"""Environment variable helpers for the webapp backend.

These helpers treat empty strings as missing values so that Docker compose
placeholders like ``${VAR:-default}`` are not required for sensible defaults.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("app.utils.env")


def _normalize(value: Optional[str]) -> Optional[str]:
    """Return ``None`` for empty or whitespace-only values."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def get_env_str(name: str, default: str) -> str:
    """Read a string environment variable with a fallback for empty values."""
    value = _normalize(os.getenv(name))
    if value is None:
        return default
    return value


def get_env_int(name: str, default: int) -> int:
    """Read an integer environment variable with robust parsing."""
    value = _normalize(os.getenv(name))
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        log.warning("Invalid integer for %s: %r – using default %s", name, value, default)
        return default
