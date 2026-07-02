"""Proxy environment helpers for outbound HTTP/WebSocket clients."""

from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def is_socks_proxy_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("socks5://", "socks5h://", "socks4://", "socks://"))


def socks_proxy_env_keys() -> list[str]:
    """Env keys currently set to a SOCKS proxy URL."""
    found: list[str] = []
    for key in _PROXY_ENV_KEYS:
        val = os.environ.get(key, "")
        if val and is_socks_proxy_url(val):
            found.append(key)
    return found


@contextmanager
def without_socks_proxy_env() -> Iterator[None]:
    """Temporarily unset SOCKS proxy vars (e.g. for Deepgram direct WS)."""
    removed: dict[str, str] = {}
    for key in socks_proxy_env_keys():
        removed[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(removed)
