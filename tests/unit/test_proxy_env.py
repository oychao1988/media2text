from __future__ import annotations

import os

from media2text.core.proxy_env import is_socks_proxy_url, without_socks_proxy_env


def test_is_socks_proxy_url() -> None:
    assert is_socks_proxy_url("socks5://127.0.0.1:7890")
    assert is_socks_proxy_url("SOCKS5H://127.0.0.1:7890")
    assert not is_socks_proxy_url("http://127.0.0.1:7890")
    assert not is_socks_proxy_url("")


def test_without_socks_proxy_env_restores(monkeypatch) -> None:
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:7890")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    with without_socks_proxy_env():
        assert "ALL_PROXY" not in os.environ
        assert os.environ.get("HTTP_PROXY") == "http://127.0.0.1:7890"
    assert os.environ.get("ALL_PROXY") == "socks5://127.0.0.1:7890"
