from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired
from media2text.core.platform.session_validate import (
    PlatformAuthSnapshot,
    invalidate_session_auth_cache,
    platform_auth_snapshot,
)


def test_platform_auth_missing_douyin(tmp_path: Path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    snap = platform_auth_snapshot(cfg, "douyin", validate=True, refresh=True)
    assert snap.status == "missing"
    assert snap.configured is False
    assert snap.auth_required is True


def test_platform_auth_expired_douyin(tmp_path: Path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    session = ws / "sessions" / "douyin.json"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text('{"cookies": [{"name": "sessionid", "value": "x"}]}', encoding="utf-8")

    with patch(
        "media2text.core.platform.douyin.playwright_client.probe_douyin_session",
        side_effect=AuthRequired("login required on douyin home"),
    ):
        snap = platform_auth_snapshot(cfg, "douyin", validate=True, refresh=True)

    assert snap.status == "expired"
    assert snap.configured is True
    assert snap.valid is False
    assert snap.auth_required is True


def test_platform_auth_ok_bilibili(tmp_path: Path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    session = ws / "sessions" / "bilibili.json"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text('{"cookies": [{"name": "SESSDATA", "value": "x"}]}', encoding="utf-8")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": 0, "data": {"isLogin": True, "uname": "u"}}

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch(
        "media2text.core.platform.session_validate.bilibili_client",
        return_value=mock_client,
    ):
        snap = platform_auth_snapshot(cfg, "bilibili", validate=True, refresh=True)

    assert snap.status == "ok"
    assert snap.valid is True
    assert snap.auth_required is False


def test_platform_auth_cache_and_invalidate(tmp_path: Path) -> None:
    invalidate_session_auth_cache()
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    session = ws / "sessions" / "bilibili.json"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("{}", encoding="utf-8")
    ok = PlatformAuthSnapshot(
        configured=True,
        valid=True,
        auth_required=False,
        status="ok",
    )

    with patch(
        "media2text.core.platform.session_validate._validate_bilibili",
        return_value=ok,
    ) as mocked:
        platform_auth_snapshot(cfg, "bilibili", validate=True, refresh=True)
        platform_auth_snapshot(cfg, "bilibili", validate=True, refresh=False)
        assert mocked.call_count == 1

        invalidate_session_auth_cache(workspace=ws, platform="bilibili")
        platform_auth_snapshot(cfg, "bilibili", validate=True, refresh=False)
        assert mocked.call_count == 2
