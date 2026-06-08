"""Legacy pipeline_mode regression (streaming STT spec S5).

Concentrates legacy finalize + post_process transcribe paths so streaming
changes are less likely to break v2 behavior silently.
"""

from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, TranscribeConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)


def _legacy_cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(pipeline_mode="legacy"),
    )


def _legacy_core(tmp_path, conn) -> LiveRecordingCore:
    return LiveRecordingCore(
        _legacy_cfg(tmp_path),
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={},
        notify=MagicMock(),
    )


def test_legacy_single_flv_remux_to_mp4(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _legacy_cfg(tmp_path)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAlegacy1",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAlegacy1/live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260603T120000Z.flv"
    flv.write_bytes(b"x" * 128)
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=4242,
        pipeline_mode="legacy",
    )

    core = _legacy_core(tmp_path, conn)
    with (
        patch("media2text.core.live.recording.stop_process"),
        patch("media2text.core.live.recording.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.recording.concat_to_mp4") as mock_concat,
        patch("media2text.core.manifest.refresh_manifest"),
    ):
        meta = core._finalize_recording(sid, str(flv), 4242)

    assert meta is not None
    assert meta["path"].endswith(".mp4")
    mock_remux.assert_called_once()
    mock_concat.assert_not_called()
    row = sessions.get(sid)
    assert row is not None
    assert row.local_path is not None
    assert row.local_path.endswith(".mp4")
    events = PipelineEventRepo(conn).list_for_session(sid)
    stages = {(e.stage, e.status) for e in events}
    assert ("remux", "skipped") not in stages
    assert any(e.stage == "remux" for e in events)


def test_legacy_multi_segment_concat_to_mp4(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _legacy_cfg(tmp_path)
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAlegacy2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAlegacy2/live"
    live_dir.mkdir(parents=True)
    seg0 = live_dir / "20260603T120000Z.flv"
    seg1 = live_dir / "20260603T120000Z_r1.flv"
    seg0.write_bytes(b"a" * 64)
    seg1.write_bytes(b"b" * 64)
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(seg1),
        ffmpeg_pid=5252,
        pipeline_mode="legacy",
    )
    sessions.append_segment_path(sid, str(seg0))

    core = _legacy_core(tmp_path, conn)
    with (
        patch("media2text.core.live.recording.stop_process"),
        patch("media2text.core.live.recording.remux_to_mp4") as mock_remux,
        patch("media2text.core.live.recording.concat_to_mp4") as mock_concat,
        patch("media2text.core.manifest.refresh_manifest"),
    ):
        meta = core._finalize_recording(sid, str(seg1), 5252)

    assert meta is not None
    mock_concat.assert_called_once()
    mock_remux.assert_not_called()
    assert meta["path"].endswith(".mp4")


def test_legacy_post_process_transcribe_when_no_sidecar(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(pipeline_mode="legacy", transcribe_on_complete=True),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAlegacy3",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    mp4 = tmp_path / "data/creators/MS4wLjABAAAAlegacy3/live/x.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(mp4.with_suffix(".flv")),
        ffmpeg_pid=1,
        pipeline_mode="legacy",
    )
    LiveSessionRepo(conn).update_status(
        sid, status="completed", local_path=str(mp4), ended=True
    )
    job = PostProcessJobRepo(conn).enqueue(
        session_id=sid, creator_id=cid, mp4_path=str(mp4)
    )

    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = MagicMock(
        text="legacy hi", segments=[], engine="whisper", model="tiny"
    )

    with (
        patch(
            "media2text.core.transcribe.factory.transcribe_engine_available",
            return_value=(True, None),
        ),
        patch(
            "media2text.core.transcribe.factory.create_transcribe_backend",
            return_value=mock_backend,
        ),
        patch(
            "media2text.core.live.post_process.write_transcript_outputs",
            return_value=(
                mp4.with_suffix(".transcript.json"),
                mp4.with_suffix(".transcript.md"),
            ),
        ),
        patch("media2text.core.live.post_process.index_transcript_safe"),
        patch("media2text.core.live.post_process.refresh_manifest"),
        patch(
            "media2text.core.summarize.hook.maybe_summarize_after_transcribe",
            return_value={},
        ),
        patch(
            "media2text.core.cloud.live_upload.maybe_upload_live_to_aliyundrive",
            return_value={},
        ),
    ):
        result = run_post_process_job(cfg, conn, job_id=job, notify=MagicMock())

    assert result["transcribed"] is True
    mock_backend.transcribe.assert_called_once()
    row = PostProcessJobRepo(conn).get(job)
    assert row is not None
    assert row.status == "done"
