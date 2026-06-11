from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from media2text.core.platform.interactive_login import wait_for_user_login


def test_wait_for_user_login_tty_uses_input(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: None)
    page = MagicMock()
    context = MagicMock()
    wait_for_user_login(
        page,
        context,
        platform="douyin",
        prompt="Press Enter...",
    )
    context.cookies.assert_not_called()


def test_wait_for_user_login_non_tty_waits_for_cookies(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    page = MagicMock()
    context = MagicMock()
    browser = MagicMock()
    browser.is_connected.return_value = True
    context.browser = browser
    context.pages = [page]

    calls = {"n": 0}

    def cookies() -> list[dict]:
        calls["n"] += 1
        if calls["n"] >= 3:
            return [{"name": "sessionid", "value": "abc"}]
        return []

    context.cookies.side_effect = cookies

    wait_for_user_login(
        page,
        context,
        platform="douyin",
        prompt="Press Enter...",
        timeout_sec=5.0,
    )


def test_wait_for_user_login_non_tty_raises_when_browser_closes(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    page = MagicMock()
    context = MagicMock()
    browser = MagicMock()
    browser.is_connected.return_value = False
    context.browser = browser
    context.pages = [page]
    context.cookies.return_value = []

    with pytest.raises(RuntimeError, match="login not completed"):
        wait_for_user_login(
            page,
            context,
            platform="douyin",
            prompt="Press Enter...",
            timeout_sec=1.0,
        )
