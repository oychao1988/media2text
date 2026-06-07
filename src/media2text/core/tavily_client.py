"""Tavily API key resolution (minimal stub for #224; #223 adds Search/Extract client)."""

from __future__ import annotations

import os

from media2text.core import env_file as _env_file


def resolve_tavily_api_key(*, env_key: str = "TAVILY_API_KEY") -> str:
    """Prefer project ``.env`` on disk over stale ``os.environ``."""
    val = _env_file.read_env_var(env_key, path=_env_file.env_file_path()).strip()
    if not val:
        val = os.environ.get(env_key, "").strip()
    if val:
        os.environ[env_key] = val
    return val
