"""Resolve Douyin live FLV pull URL via webcast/room/web/enter (Playwright)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from media2text.core.errors import ParseFailed
from playwright.sync_api import sync_playwright

from media2text.core.playwright_env import launch_chromium, playwright_exclusive


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
    """Call webcast/room/web/enter directly (no page navigation)."""
    params = {
        "web_rid": room_id,
        "room_id_str": room_id,
        "enter_source": "",
        "is_need_double_stream": "false",
        "cookie_enabled": "true",
    }
    if sec_user_id:
        params["sec_user_id"] = sec_user_id
    url = f"https://live.douyin.com/webcast/room/web/enter/?{urlencode(params)}"

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
