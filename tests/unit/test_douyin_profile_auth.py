from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.errors import AuthRequired, ParseFailed
from media2text.core.platform.douyin.adapter import DouyinAdapterV1


def test_get_user_profile_reraises_auth_from_playwright(tmp_path: Path) -> None:
    session = tmp_path / "douyin.json"
    session.write_text("{}", encoding="utf-8")
    adapter = DouyinAdapterV1(MagicMock(), session_path=session)

    with patch(
        "media2text.core.platform.douyin.adapter.fetch_profile_api",
        side_effect=ParseFailed("profile API returned non-JSON body"),
    ), patch(
        "media2text.core.platform.douyin.adapter.fetch_profile_api_via_page",
        side_effect=AuthRequired("login required on profile page"),
    ):
        with pytest.raises(AuthRequired, match="login required"):
            adapter.get_user_profile(sec_uid="MS4wLjABAAAAtest")
