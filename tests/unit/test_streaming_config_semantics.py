from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.transcript_writer import TranscriptWriter
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)


def test_snapshot_pipeline_mode_legacy_when_stt_disabled() -> None:
    cfg = LiveConfig(
        pipeline_mode="streaming",
        streaming_stt=StreamingSttConfig(enabled=False),
    )
    assert cfg.is_streaming_pipeline() is False
    assert cfg.snapshot_pipeline_mode() == "legacy"


def test_use_streaming_false_when_stt_disabled_despite_db_streaming(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=False),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAdisabled",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        pipeline_mode="streaming",
    )

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    assert core._use_streaming_pipeline(sid) is False
    assert core._use_streaming_pipeline(None) is False


def test_streaming_finalize_remux_when_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            remux_on_complete=True,
            streaming_stt=StreamingSttConfig(enabled=True),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAremux",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAremux/live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260603T140000Z.flv"
    flv.write_bytes(b"x" * 128)
    mp4 = flv.with_suffix(".mp4")
    sid = sessions.create(
        creator_id=cid,
        room_id="101",
        temp_path=str(flv),
        ffmpeg_pid=6262,
        pipeline_mode="streaming",
    )

    mock_stt = MagicMock()
    writer = TranscriptWriter(flv)
    writer.add_final("hello", start=0.0, end=1.0)
    mock_stt.writer = writer

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    core._stt_sessions[sid] = mock_stt
    core._streaming_transcript_anchor[sid] = flv

    with (
        patch("media2text.core.live.session_finalize.stop_process"),
        patch("media2text.core.live.session_finalize.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.state_writer.refresh_manifest"),
        patch("media2text.core.live.session_finalize.index_transcript_safe"),
    ):
        def _touch_mp4(*, ffmpeg, src, dst):  # noqa: ARG001
            Path(dst).write_bytes(b"mp4")

        mock_remux.side_effect = _touch_mp4
        meta = core._finalize_recording(sid, str(flv), 6262)

    assert meta is not None
    assert meta["path"].endswith(".mp4")
    mock_remux.assert_called_once()
    row = sessions.get(sid)
    assert row is not None
    assert row.local_path == str(mp4)
    assert flv.is_file()
    events = PipelineEventRepo(conn).list_for_session(sid)
    stages = {(e.stage, e.status) for e in events}
    assert ("remux", "completed") in stages
    assert ("remux", "skipped") not in stages
    jobs = PostProcessJobRepo(conn).list_pending(limit=5)
    assert len(jobs) == 1
    assert jobs[0].mp4_path.endswith(".mp4")
