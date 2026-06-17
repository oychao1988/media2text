from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from media2text.core.errors import ParseFailed
from media2text.core.platform.douyin.http_live import resolve_live_via_http
from media2text.core.platform.douyin.models import LiveRoomInfo


def test_resolve_live_via_http_returns_offline_from_api() -> None:
    client = MagicMock()
    offline = LiveRoomInfo(room_id=None, is_live=False)
    with patch(
        "media2text.core.platform.douyin.http_live.fetch_profile_api",
        return_value={"user": {"room_id": 0, "live_status": 0}},
    ):
        with patch(
            "media2text.core.platform.douyin.http_live.parse_profile_live",
            return_value=offline,
        ):
            info = resolve_live_via_http(client, "MS4wLjABAAAAtest")
    assert info.is_live is False


def test_resolve_live_via_http_propagates_api_block_for_playwright_fallback() -> None:
    client = MagicMock()
    with patch(
        "media2text.core.platform.douyin.http_live.fetch_profile_api",
        side_effect=ParseFailed("profile API blocked"),
    ):
        with pytest.raises(ParseFailed, match="blocked"):
            resolve_live_via_http(client, "MS4wLjABAAAAtest")
