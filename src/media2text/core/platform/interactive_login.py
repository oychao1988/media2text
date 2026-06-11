"""Wait for the user to finish an interactive platform login in Playwright."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

DEFAULT_TIMEOUT_SEC = 600.0
SETTLE_SEC = 2.0
POLL_INTERVAL_SEC = 1.0

LoginCookieCheck = Callable[[list[dict]], bool]


def _douyin_logged_in(cookies: list[dict]) -> bool:
    return any(
        cookie.get("name") == "sessionid" and cookie.get("value")
        for cookie in cookies
    )


def _bilibili_logged_in(cookies: list[dict]) -> bool:
    return any(
        cookie.get("name") == "SESSDATA" and cookie.get("value")
        for cookie in cookies
    )


LOGIN_COOKIE_CHECKS: dict[str, LoginCookieCheck] = {
    "douyin": _douyin_logged_in,
    "bilibili": _bilibili_logged_in,
}


def wait_for_user_login(
    page: Page,
    context: BrowserContext,
    *,
    platform: str,
    prompt: str,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> None:
    """Block until login completes.

    CLI (TTY): print *prompt* and wait for Enter.
    Desktop / detached subprocess: keep the browser open and poll login cookies.
    """
    if sys.stdin.isatty():
        print(prompt, flush=True)
        input()
        return

    key = platform.strip().lower()
    check = LOGIN_COOKIE_CHECKS.get(key)
    if check is None:
        raise RuntimeError(f"unsupported interactive login platform: {platform!r}")

    deadline = time.monotonic() + timeout_sec
    logged_in_since: float | None = None

    while time.monotonic() < deadline:
        browser = context.browser
        if browser is None or not browser.is_connected():
            break
        if not context.pages:
            break

        cookies = context.cookies()
        if check(cookies):
            now = time.monotonic()
            if logged_in_since is None:
                logged_in_since = now
            elif now - logged_in_since >= SETTLE_SEC:
                return
        else:
            logged_in_since = None

        try:
            page.wait_for_timeout(int(POLL_INTERVAL_SEC * 1000))
        except Exception:
            break

    if check(context.cookies()):
        return

    raise RuntimeError(
        f"{key} login not completed (browser closed, timed out, or session cookies missing)"
    )
