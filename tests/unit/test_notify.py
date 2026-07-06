from unittest.mock import MagicMock, patch

import httpx

from media2text.core.config import AppConfig, NotifyConfig, NotifyFeishuConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.feishu import send_feishu_text
from media2text.core.storage.models import CreatorRow


def _creator() -> CreatorRow:
    return CreatorRow(
        id="c1",
        platform="douyin",
        sec_uid="MS4wLjABAAAAtest",
        display_name="测试博主",
        profile_url="https://example.com/u",
        watch_live=1,
        monitor_enabled=1,
        unique_id="test_user",
        avatar_url=None,
        signature=None,
        follower_count=None,
        profile_synced_at=None,
        created_at="2026-01-01T00:00:00Z",
    )


def test_notify_disabled_is_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", notify=NotifyConfig(enabled=False))
    svc = NotifyService(cfg)
    with (
        patch("media2text.core.notify.service.play_sound") as mock_sound,
        patch("media2text.core.notify.service.send_feishu_text") as mock_feishu,
    ):
        svc.emit(NotifyEvent(kind=EventKind.LIVE_STARTED, title="t", body="b"))
    mock_sound.assert_not_called()
    mock_feishu.assert_not_called()


def test_notify_emits_sound_and_feishu(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOTIFY_FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=True),
    )
    svc = NotifyService(cfg)
    with (
        patch("media2text.core.notify.service.play_sound") as mock_sound,
        patch("media2text.core.notify.service.send_feishu_text", return_value=True) as mock_feishu,
    ):
        svc.emit(
            NotifyEvent(
                kind=EventKind.NEW_AWEME,
                title="博主",
                body="同步到 2 个新作品",
            )
        )
    mock_sound.assert_called_once()
    mock_feishu.assert_called_once()
    args, kwargs = mock_feishu.call_args
    assert "新作品" in kwargs["text"]


def test_send_feishu_text_success(monkeypatch) -> None:
    request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, json={"code": 0}, request=request)
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = response
    monkeypatch.setattr("media2text.core.notify.feishu.httpx.Client", lambda **_: mock_client)
    assert send_feishu_text(webhook_url="https://example.com/hook", text="hello") is True


def test_monitor_vod_notifications(tmp_path, monkeypatch) -> None:
    from media2text.core.live.monitor_executor import _emit_sync_notifications

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=False, feishu=NotifyFeishuConfig(enabled=False)),
    )
    notify = NotifyService(cfg)
    creator = _creator()
    with patch.object(notify, "emit") as mock_emit:
        _emit_sync_notifications(
            creator,
            {"new_count": 3},
            new_content_kind=EventKind.NEW_AWEME,
            notify=notify,
        )
    mock_emit.assert_called_once()
    event = mock_emit.call_args[0][0]
    assert event.kind == EventKind.NEW_AWEME
    assert "3" in event.body


def test_monitor_archive_notifications(tmp_path, monkeypatch) -> None:
    from media2text.core.live.monitor_executor import _emit_sync_notifications

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=False, feishu=NotifyFeishuConfig(enabled=False)),
    )
    notify = NotifyService(cfg)
    creator = _creator()
    with patch.object(notify, "emit") as mock_emit:
        _emit_sync_notifications(
            creator,
            {"new_count": 1},
            new_content_kind=EventKind.NEW_ARCHIVE,
            notify=notify,
        )
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].kind == EventKind.NEW_ARCHIVE
