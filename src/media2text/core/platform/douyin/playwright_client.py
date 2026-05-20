from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.parse import map_http_error


def fetch_json(
    session_path: Path,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    referer: str = "https://www.douyin.com/",
) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(session_path))
        try:
            response = context.request.get(
                url,
                headers={
                    "Referer": referer,
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                },
            )
            body = response.text()
            if response.status >= 400:
                raise map_http_error(response.status, body)
            data = response.json()
            if not isinstance(data, dict):
                raise ParseFailed("expected JSON object")
            return data
        finally:
            context.close()
            browser.close()


def fetch_profile_html(session_path: Path, sec_uid: str) -> str:
    url = f"https://www.douyin.com/user/{sec_uid}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            content = page.content()
            if "登录" in content and "passport" in content:
                raise AuthRequired("login required on profile page")
            return content
        finally:
            context.close()
            browser.close()
