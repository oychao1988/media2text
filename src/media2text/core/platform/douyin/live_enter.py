"""Resolve Douyin live FLV via webcast/room/web/enter (signed HTTP or Playwright)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

import httpx
from playwright.sync_api import sync_playwright

from media2text.core.errors import ParseFailed
from media2text.core.platform.douyin.signed_api import _UA, _false_ms_token, sign_get_url
from media2text.core.playwright_env import launch_chromium, playwright_exclusive

_ENTER_BASE = "https://live.douyin.com/webcast/room/web/enter/"
_WEB_RID_RE = re.compile(r'web_rid["\']?\s*[:=]\s*["\']?(\d+)')


def flv_from_room_dict(room: dict) -> str | None:
    stream_url = room.get("stream_url") or {}
    flv_pull = stream_url.get("flv_pull_url")
    if isinstance(flv_pull, dict) and flv_pull:
        for key in ("HD1", "SD1", "FULL_HD1"):
            url = flv_pull.get(key)
            if isinstance(url, str) and url:
                return url
        return next((v for v in flv_pull.values() if isinstance(v, str) and v), None)
    if isinstance(flv_pull, str) and flv_pull:
        return flv_pull
    return None


def room_from_enter_payload(payload: dict) -> dict | None:
    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("data")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0]
        room = data.get("room")
        if isinstance(room, dict):
            return room
    room = payload.get("room")
    return room if isinstance(room, dict) else None


def resolve_web_rid_from_live_page(client: httpx.Client, profile_room_id: str) -> str | None:
    """Best-effort web_rid from live.douyin.com HTML (unreliable; prefer profile page)."""
    response = client.get(
        f"https://live.douyin.com/{profile_room_id}",
        headers={"Referer": f"https://live.douyin.com/{profile_room_id}"},
    )
    if response.status_code >= 400:
        return None
    match = _WEB_RID_RE.search(response.text)
    return match.group(1) if match else None


def resolve_web_rid_from_profile_page(client: httpx.Client, sec_uid: str) -> str | None:
    """Resolve web_rid from creator profile HTML live badge link."""
    from media2text.core.platform.douyin.http_live import fetch_profile_page
    from media2text.core.platform.douyin.parse import parse_profile_html

    html = fetch_profile_page(client, sec_uid)
    info = parse_profile_html(html)
    if info.is_live and info.web_rid:
        return info.web_rid
    return None


def resolve_web_rid_for_enter(
    client: httpx.Client,
    profile_room_id: str,
    *,
    sec_user_id: str | None = None,
    web_rid: str | None = None,
) -> str:
    if web_rid:
        return web_rid
    if sec_user_id:
        from_profile = resolve_web_rid_from_profile_page(client, sec_user_id)
        if from_profile:
            return from_profile
    from_live_page = resolve_web_rid_from_live_page(client, profile_room_id)
    if from_live_page:
        return from_live_page
    raise ParseFailed(
        f"could not resolve web_rid for profile room_id={profile_room_id}"
    )


def _enter_query_params(
    web_rid: str,
    *,
    sec_user_id: str | None = None,
    ms_token: str | None = None,
) -> dict[str, str]:
    params: dict[str, str] = {
        "aid": "6383",
        "app_name": "douyin_web",
        "live_id": "1",
        "device_platform": "web",
        "language": "zh-CN",
        "enter_from": "web_live",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "139.0.0.0",
        "web_rid": web_rid,
        "enter_source": "",
        "is_need_double_stream": "false",
        "msToken": ms_token or _false_ms_token(),
    }
    if sec_user_id:
        params["sec_user_id"] = sec_user_id
    return params


def fetch_signed_web_enter_payload(
    client: httpx.Client,
    web_rid: str,
    *,
    sec_user_id: str | None = None,
) -> dict:
    """Signed HTTP GET to webcast/room/web/enter (no browser)."""
    ms_token = (client.cookies.get("msToken") or "").strip() or None
    params = _enter_query_params(web_rid, sec_user_id=sec_user_id, ms_token=ms_token)
    signed_url, ua = sign_get_url(_ENTER_BASE, params, user_agent=_UA)
    response = client.get(
        signed_url,
        headers={
            "User-Agent": ua,
            "Referer": f"https://live.douyin.com/{web_rid}",
        },
    )
    if response.status_code >= 400:
        raise ParseFailed(f"web/enter HTTP {response.status_code}")
    body = response.content
    if not body:
        raise ParseFailed("web/enter empty body")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ParseFailed("web/enter expected JSON object") from exc
    if not isinstance(payload, dict):
        raise ParseFailed("web/enter expected JSON object")
    return payload


def resolve_stream_via_signed_http_enter(
    client: httpx.Client,
    profile_room_id: str,
    *,
    sec_user_id: str | None = None,
    web_rid: str | None = None,
) -> str:
    """Resolve FLV via signed enter; profile_room_id is internal id from profile/other."""
    resolved_web_rid = resolve_web_rid_for_enter(
        client,
        profile_room_id,
        sec_user_id=sec_user_id,
        web_rid=web_rid,
    )
    payload = fetch_signed_web_enter_payload(
        client, resolved_web_rid, sec_user_id=sec_user_id
    )
    room = room_from_enter_payload(payload)
    if not room:
        code = payload.get("status_code")
        raise ParseFailed(f"enter response has no room payload (status_code={code})")
    status = room.get("status")
    stream_flv_url = flv_from_room_dict(room)
    if status != 2 or not stream_flv_url:
        raise ParseFailed(
            f"enter room not streaming (status={status}, flv={bool(stream_flv_url)})"
        )
    return stream_flv_url


def _room_id_from_live_url(live_url: str) -> str:
    return live_url.rstrip("/").split("/")[-1]


def _parse_enter_payload(payload: dict, *, live_url: str) -> tuple[str, str, str | None]:
    room = room_from_enter_payload(payload)
    if not room:
        raise ParseFailed("enter response has no room payload (offline or parse drift)")

    room_id = str(room.get("id_str") or room.get("id") or "")
    title = room.get("title")
    status = room.get("status")
    stream_flv_url = flv_from_room_dict(room)
    if not stream_flv_url:
        raise ParseFailed(f"enter room {room_id or '?'} has no flv_pull_url (status={status})")
    title_str = title if isinstance(title, str) else None
    return stream_flv_url, room_id or _room_id_from_live_url(live_url), title_str


def fetch_web_enter_payload(
    session: Path,
    *,
    room_id: str,
    sec_user_id: str | None = None,
) -> dict:
    """Call webcast/room/web/enter via Playwright request context (legacy fallback)."""
    params = {
        "web_rid": room_id,
        "room_id_str": room_id,
        "enter_source": "",
        "is_need_double_stream": "false",
        "cookie_enabled": "true",
    }
    if sec_user_id:
        params["sec_user_id"] = sec_user_id
    url = f"{_ENTER_BASE}?{urlencode(params)}"

    with playwright_exclusive():
        with sync_playwright() as p:
            browser = launch_chromium(p, headless=True)
            context = browser.new_context(storage_state=str(session))
            try:
                response = context.request.get(
                    url,
                    headers={"Referer": f"https://live.douyin.com/{room_id}"},
                )
                if response.status >= 400:
                    raise ParseFailed(f"web/enter HTTP {response.status}")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ParseFailed("web/enter expected JSON object")
                return payload
            finally:
                context.close()
                browser.close()


def resolve_stream_via_web_enter(
    session: Path,
    live_url: str,
    *,
    wait_ms: int = 8_000,
    sec_user_id: str | None = None,
) -> tuple[str, str, str | None]:
    """Resolve FLV pull URL by opening the live page and intercepting web/enter."""
    enter_payload: dict | None = None
    final_url = live_url

    with playwright_exclusive():
        with sync_playwright() as p:
            browser = launch_chromium(p, headless=True)
            context = browser.new_context(storage_state=str(session))
            page = context.new_page()

            def on_response(response) -> None:
                nonlocal enter_payload
                if "webcast/room/web/enter" not in response.url or response.status != 200:
                    return
                try:
                    enter_payload = response.json()
                except Exception:
                    return

            page.on("response", on_response)
            page.goto(live_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(wait_ms)
            try:
                page.mouse.wheel(0, 400)
            except Exception:
                pass
            page.wait_for_timeout(min(wait_ms, 4_000))
            final_url = page.url
            browser.close()

    if not enter_payload:
        raise ParseFailed(
            f"no webcast/room/web/enter response for {live_url} (final={final_url})"
        )

    return _parse_enter_payload(enter_payload, live_url=live_url)
