from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from media2text.core.config import AppConfig, NotifyConfig, NotifyFeishuConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.content import chunk_text, format_transcript_for_push, media_mp4_path
from media2text.core.notify.feishu import send_feishu_text
from media2text.core.notify.samples import find_latest_transcript_with_media
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
        patch("media2text.core.notify.service.send_feishu_post", return_value=True) as mock_post,
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
    assert mock_post.called or mock_feishu.called


def test_media_mp4_path_from_transcript_md() -> None:
    md = Path("live/20260520T124016Z.transcript.md")
    assert media_mp4_path(md) == Path("live/20260520T124016Z.mp4")
    assert media_mp4_path(Path("videos/1.mp4")) == Path("videos/1.mp4")


def test_format_transcript_for_push(tmp_path) -> None:
    md = tmp_path / "t.transcript.md"
    md.write_text("# Transcript: x\n\n- [0s] hello\n", encoding="utf-8")
    text = format_transcript_for_push(md)
    assert "hello" in text
    assert "#" not in text


def test_chunk_text() -> None:
    parts = chunk_text("a\n" * 100, max_chars=30)
    assert len(parts) >= 2
    assert "".join(parts).replace("\n", "") == "a" * 100


def test_find_latest_transcript_with_media(tmp_path) -> None:
    live = tmp_path / "data" / "creators" / "MS4w" / "live"
    live.mkdir(parents=True)
    md = live / "20260520T124016Z.transcript.md"
    mp4 = live / "20260520T124016Z.mp4"
    md.write_text("# t\n\nhello\n", encoding="utf-8")
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    found_md, found_mp4 = find_latest_transcript_with_media(tmp_path / "data")
    assert found_md == md
    assert found_mp4 == mp4


def test_send_feishu_text_success(monkeypatch) -> None:
    request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, json={"code": 0}, request=request)
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = response
    monkeypatch.setattr("media2text.core.notify.feishu.httpx.Client", lambda **_: mock_client)
    assert send_feishu_text(webhook_url="https://example.com/hook", text="hello") is True


def test_monitor_vod_notifications(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        notify=NotifyConfig(enabled=True, sound=False, feishu=NotifyFeishuConfig(enabled=False)),
    )
    from media2text.core.monitor.watcher import MonitorWatcher

    watcher = MonitorWatcher(cfg)
    creator = _creator()
    md = tmp_path / "data" / "creators" / "MS4w" / "videos" / "1.transcript.md"
    md.parent.mkdir(parents=True)
    md.write_text("# t\n\n- [0s] hi\n", encoding="utf-8")
    mp4 = md.with_suffix(".mp4")
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    with patch.object(watcher._notify, "emit") as mock_emit:
        watcher._emit_vod_notifications(
            creator,
            {
                "sync": {"new_count": 3},
                "transcribed": 1,
                "transcribed_paths": [str(md)],
            },
        )
    assert mock_emit.call_count == 2
    kinds = {call.args[0].kind for call in mock_emit.call_args_list}
    assert EventKind.NEW_AWEME in kinds
    assert EventKind.TRANSCRIBE_COMPLETED in kinds
