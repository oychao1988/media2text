from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.errors import ParseFailed
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.douyin.models import LiveRoomInfo


def test_get_live_room_prefers_http_when_client_present(tmp_path: Path) -> None:
    client = MagicMock()
    session = tmp_path / "douyin.json"
    session.write_text('{"cookies": []}', encoding="utf-8")
    adapter = DouyinAdapterV1(client, session_path=session)
    live = LiveRoomInfo(room_id="7318296342189919011", is_live=True)

    with (
        patch(
            "media2text.core.platform.douyin.adapter.resolve_live_via_http",
            return_value=live,
        ) as http_live,
        patch.object(adapter, "_live_room_via_playwright") as pw_live,
    ):
        info = adapter.get_live_room(sec_uid="MS4wLjABAAAAtest")

    assert info.is_live is True
    assert info.room_id == live.room_id
    http_live.assert_called_once_with(client, "MS4wLjABAAAAtest")
    pw_live.assert_not_called()


def test_get_live_room_falls_back_to_playwright_when_http_fails(tmp_path: Path) -> None:
    client = MagicMock()
    session = tmp_path / "douyin.json"
    session.write_text('{"cookies": []}', encoding="utf-8")
    adapter = DouyinAdapterV1(client, session_path=session)
    live = LiveRoomInfo(room_id="7318296342189919011", is_live=True)

    with (
        patch(
            "media2text.core.platform.douyin.adapter.resolve_live_via_http",
            side_effect=ParseFailed("http blocked"),
        ),
        patch.object(adapter, "_live_room_via_playwright", return_value=live) as pw_live,
    ):
        info = adapter.get_live_room(sec_uid="MS4wLjABAAAAtest")

    assert info.is_live is True
    pw_live.assert_called_once_with(session, "MS4wLjABAAAAtest")


def test_get_live_room_playwright_runtime_error_surfaces_playwright_error(
    tmp_path: Path,
) -> None:
    client = MagicMock()
    session = tmp_path / "douyin.json"
    session.write_text('{"cookies": []}', encoding="utf-8")
    adapter = DouyinAdapterV1(client, session_path=session)

    with (
        patch(
            "media2text.core.platform.douyin.adapter.resolve_live_via_http",
            side_effect=ParseFailed("http blocked"),
        ),
        patch.object(
            adapter,
            "_live_room_via_playwright",
            side_effect=RuntimeError("playwright_chromium_launch_failed"),
        ),
    ):
        with pytest.raises(RuntimeError, match="playwright_chromium_launch_failed"):
            adapter.get_live_room(sec_uid="MS4wLjABAAAAtest")


def test_resolve_stream_url_prefers_signed_http_enter(tmp_path: Path) -> None:
    client = MagicMock()
    adapter = DouyinAdapterV1(client, session_path=tmp_path / "missing.json")

    with patch(
        "media2text.core.platform.douyin.live_enter.resolve_stream_via_signed_http_enter",
        return_value="https://example.com/live.flv",
    ) as signed_enter:
        url = adapter.resolve_stream_url(room_id="7649404054766291754", sec_uid="MS4wLjABAAAAtest")

    assert url == "https://example.com/live.flv"
    signed_enter.assert_called_once_with(
        client,
        "7649404054766291754",
        sec_user_id="MS4wLjABAAAAtest",
        web_rid=None,
    )
