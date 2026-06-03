from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)


def _streaming_cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            remux_on_complete=False,
            streaming_stt=StreamingSttConfig(enabled=True),
        ),
    )


def test_streaming_finalize_skips_remux(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _streaming_cfg(tmp_path)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAstream",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAstream/live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260603T120000Z.flv"
    flv.write_bytes(b"x" * 128)
    sid = sessions.create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=4242,
    )

    mock_stt = MagicMock()
    mock_stt.stop.return_value = (
        flv.with_suffix(".transcript.json"),
        flv.with_suffix(".transcript.md"),
    )
    flv.with_suffix(".transcript.json").write_text('{"text":"hi"}', encoding="utf-8")

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )
    core._stt_sessions[sid] = mock_stt

    with (
        patch("media2text.core.live.recording.stop_process"),
        patch("media2text.core.live.recording.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.recording.concat_to_mp4") as mock_concat,
        patch("media2text.core.live.recording.refresh_manifest"),
        patch("media2text.core.live.recording.index_transcript_safe"),
    ):
        meta = core._finalize_recording(sid, str(flv), 4242)

    assert meta is not None
    assert meta["path"].endswith(".flv")
    mock_remux.assert_not_called()
    mock_concat.assert_not_called()
    row = sessions.get(sid)
    assert row is not None
    assert row.local_path == str(flv)
    events = PipelineEventRepo(conn).list_for_session(sid)
    stages = {(e.stage, e.status) for e in events}
    assert ("remux", "skipped") in stages
    assert ("streaming_stt", "completed") in stages
    jobs = PostProcessJobRepo(conn).list_pending(limit=5)
    assert len(jobs) == 1
    assert jobs[0].mp4_path.endswith(".flv")
