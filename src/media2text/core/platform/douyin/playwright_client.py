from __future__ import annotations

import json
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from playwright.sync_api import Response, sync_playwright

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.parse import _user_sec_uid, map_http_error

_PROFILE_API_MARKER = "user/profile/other"


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


def _profile_payload_from_response(response: Response) -> dict | None:
    try:
        text = response.text().strip()
    except Exception:
        return None
    if not text or text[0] not in "{[":
        return None
    try:
        data = json.loads(text)
    except JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("status_code") not in (0, None):
        return None
    if not data.get("user"):
        return None
    return data


def _matching_profile_payload(responses: list[Response], sec_uid: str) -> dict | None:
    for response in responses:
        payload = _profile_payload_from_response(response)
        if not payload:
            continue
        user = payload.get("user")
        if isinstance(user, dict) and _user_sec_uid(user) == sec_uid:
            return payload
    return None


def fetch_profile_api_via_page(session_path: Path, sec_uid: str) -> dict:
    """Load the profile page in-browser and capture the signed profile/other XHR."""
    url = f"https://www.douyin.com/user/{sec_uid}"
    captured: list[Response] = []

    def on_response(response: Response) -> None:
        if _PROFILE_API_MARKER in response.url and response.status == 200:
            captured.append(response)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                payload = _matching_profile_payload(captured, sec_uid)
                if payload:
                    return payload
                page.wait_for_timeout(500)
            try:
                content = page.content()
            except Exception:
                content = ""
            if "登录" in content and "passport" in content:
                raise AuthRequired("login required on profile page")
        finally:
            context.close()
            browser.close()

    raise ParseFailed("profile API response not captured from page")


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
