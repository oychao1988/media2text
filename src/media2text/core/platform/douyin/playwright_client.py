from __future__ import annotations

import json
import shutil
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.sync_api import Response, sync_playwright


def _chromium_executable() -> str | None:
    """Return absolute system chromium path if Playwright's bundled one is unavailable (e.g. ARM64)."""
    path = shutil.which("chromium-browser") or shutil.which("chromium")
    return path  # shutil.which returns absolute path or None

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.parse import _user_sec_uid, map_http_error

_PROFILE_API_MARKER = "user/profile/other"
_AWEME_POST_MARKER = "aweme/v1/web/aweme/post"


def _scroll_aweme_post_feed(page) -> None:
    """Trigger Douyin profile post list to load more signed aweme/post XHR."""
    try:
        page.mouse.wheel(0, 2000)
    except Exception:
        pass
    try:
        page.locator("[data-e2e='user-post-list'] >> div").last.scroll_into_view_if_needed(
            timeout=3000
        )
    except Exception:
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
        except Exception:
            pass


def _normalize_aweme_max_cursor(max_cursor: str) -> str:
    return max_cursor if max_cursor else "0"


def _aweme_post_sec_uid_from_url(url: str) -> str | None:
    if _AWEME_POST_MARKER not in url:
        return None
    qs = parse_qs(urlparse(url).query)
    return (qs.get("sec_user_id") or [None])[0]


def _aweme_post_cursor_from_url(url: str) -> str | None:
    if _AWEME_POST_MARKER not in url:
        return None
    qs = parse_qs(urlparse(url).query)
    raw = (qs.get("max_cursor") or [None])[0]
    if raw is None:
        return None
    return _normalize_aweme_max_cursor(str(raw))


def _aweme_post_query_matches(url: str, *, sec_uid: str, max_cursor: str) -> bool:
    if _aweme_post_sec_uid_from_url(url) != sec_uid:
        return False
    got = _aweme_post_cursor_from_url(url)
    return got == _normalize_aweme_max_cursor(max_cursor)


def _aweme_post_payload_from_response(
    response: Response,
    *,
    sec_uid: str,
    max_cursor: str,
) -> dict | None:
    if response.status != 200 or not _aweme_post_query_matches(
        response.url, sec_uid=sec_uid, max_cursor=max_cursor
    ):
        return None
    try:
        data = response.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("status_code") not in (0, None):
        return None
    aweme_list = data.get("aweme_list")
    if not isinstance(aweme_list, list):
        return None
    return data


def _pick_aweme_post_payload(payloads: list[dict]) -> dict | None:
    if not payloads:
        return None
    return max(payloads, key=lambda p: len(p.get("aweme_list") or []))


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
        browser = p.chromium.launch(headless=True, executable_path=_chromium_executable())
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
        browser = p.chromium.launch(headless=True, executable_path=_chromium_executable())
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


def _store_aweme_post_snapshot(
    snapshots: dict[str, dict],
    *,
    url: str,
    payload: dict,
) -> None:
    cursor = _aweme_post_cursor_from_url(url)
    if cursor is None:
        return
    prev = snapshots.get(cursor)
    if not prev or len(payload.get("aweme_list") or []) > len(prev.get("aweme_list") or []):
        snapshots[cursor] = payload


def fetch_aweme_post_snapshots_until_cursor(
    session_path: Path,
    sec_uid: str,
    required_cursor: str,
) -> dict[str, dict]:
    """Open profile page and scroll until a specific max_cursor response is captured."""
    want = _normalize_aweme_max_cursor(required_cursor)
    url = f"https://www.douyin.com/user/{sec_uid}"
    snapshots: dict[str, dict] = {}

    def on_response(response: Response) -> None:
        if response.status != 200 or _aweme_post_sec_uid_from_url(response.url) != sec_uid:
            return
        try:
            data = response.json()
        except Exception:
            return
        if not isinstance(data, dict) or data.get("status_code") not in (0, None):
            return
        if not isinstance(data.get("aweme_list"), list):
            return
        _store_aweme_post_snapshot(snapshots, url=response.url, payload=data)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=_chromium_executable())
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.monotonic() + 60.0
            scrolls = 0
            while time.monotonic() < deadline:
                if want in snapshots:
                    return snapshots
                if scrolls < 40:
                    _scroll_aweme_post_feed(page)
                    scrolls += 1
                page.wait_for_timeout(800)
        finally:
            context.close()
            browser.close()

    return snapshots


def fetch_aweme_post_snapshots_via_page(session_path: Path, sec_uid: str) -> dict[str, dict]:
    """Load profile page once and capture all signed aweme/post pages (by max_cursor)."""
    url = f"https://www.douyin.com/user/{sec_uid}"
    snapshots: dict[str, dict] = {}

    def on_response(response: Response) -> None:
        if response.status != 200 or _aweme_post_sec_uid_from_url(response.url) != sec_uid:
            return
        try:
            data = response.json()
        except Exception:
            return
        if not isinstance(data, dict) or data.get("status_code") not in (0, None):
            return
        if not isinstance(data.get("aweme_list"), list):
            return
        _store_aweme_post_snapshot(snapshots, url=response.url, payload=data)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=_chromium_executable())
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.monotonic() + 60.0
            collect_until = time.monotonic() + 8.0
            scrolls = 0
            while time.monotonic() < deadline:
                if snapshots.get("0") and time.monotonic() >= collect_until:
                    if scrolls >= 25:
                        return snapshots
                    _scroll_aweme_post_feed(page)
                    scrolls += 1
                page.wait_for_timeout(800)
            try:
                content = page.content()
            except Exception:
                content = ""
            if "登录" in content and "passport" in content and not snapshots:
                raise AuthRequired("login required on profile page")
        finally:
            context.close()
            browser.close()

    if snapshots:
        return snapshots
    raise ParseFailed("aweme post API response not captured from page")


def fetch_aweme_post_via_page(
    session_path: Path,
    sec_uid: str,
    *,
    max_cursor: str = "",
    count: int = 18,
) -> dict:
    """Return one aweme/post page payload (uses a single in-browser capture pass)."""
    _ = count
    snapshots = fetch_aweme_post_snapshots_via_page(session_path, sec_uid)
    want = _normalize_aweme_max_cursor(max_cursor)
    payload = snapshots.get(want)
    if payload:
        return payload
    raise ParseFailed(f"aweme post page for max_cursor={want} not captured")


def fetch_profile_html(session_path: Path, sec_uid: str) -> str:
    url = f"https://www.douyin.com/user/{sec_uid}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=_chromium_executable())
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
