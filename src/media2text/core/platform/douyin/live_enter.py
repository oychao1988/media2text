"""Resolve Douyin live FLV pull URL via webcast/room/web/enter (Playwright)."""

from __future__ import annotations

from pathlib import Path

from media2text.core.errors import ParseFailed
from playwright.sync_api import sync_playwright


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


def resolve_stream_via_web_enter(
    session: Path,
    live_url: str,
    *,
    wait_ms: int = 8_000,
) -> tuple[str, str, str | None]:
    """Open Douyin live page and capture webcast/room/web/enter pull URL."""
    enter_payload: dict | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
        final_url = page.url
        browser.close()

    if not enter_payload:
        raise ParseFailed(
            f"no webcast/room/web/enter response for {live_url} (final={final_url})"
        )

    room = room_from_enter_payload(enter_payload)
    if not room:
        raise ParseFailed("enter response has no room payload (offline or parse drift)")

    room_id = str(room.get("id_str") or room.get("id") or "")
    title = room.get("title")
    status = room.get("status")
    stream_flv_url = flv_from_room_dict(room)
    if not stream_flv_url:
        raise ParseFailed(f"enter room {room_id or '?'} has no flv_pull_url (status={status})")
    title_str = title if isinstance(title, str) else None
    return stream_flv_url, room_id, title_str
