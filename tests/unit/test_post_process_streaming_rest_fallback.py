from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, TranscribeConfig
from media2text.core.live.pipeline_events import record_event
from media2text.core.live.post_process import run_post_process_job
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def _setup_job(
    tmp_path,
    monkeypatch,
    *,
    pipeline_mode: str | None = "streaming",
    transcribe_status: str | None = "failed",
    write_transcript: bool = False,
):
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(pipeline_mode="streaming", transcribe_on_complete=False),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAStream",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    media = tmp_path / "data/creators/MS4wLjABAAAStream/live/x.flv"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"\x00" * 64)
    if write_transcript:
        media.with_suffix(".transcript.json").write_text(
            '{"engine":"deepgram","text":"hi","segments":[]}',
            encoding="utf-8",
        )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(media),
        ffmpeg_pid=None,
        pipeline_mode=pipeline_mode,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(media),
        transcribe_status=transcribe_status,
        ended=True,
    )
    job_id = PostProcessJobRepo(conn).enqueue(
        session_id=sid, creator_id=cid, mp4_path=str(media)
    )
    return cfg, conn, job_id, media


def test_streaming_missing_sidecar_forces_rest_despite_transcribe_off(
    tmp_path, monkeypatch
) -> None:
    cfg, conn, job_id, media = _setup_job(tmp_path, monkeypatch)
    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = MagicMock(
        text="hi", segments=[], engine="whisper", model="tiny"
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
                media.with_suffix(".transcript.json"),
                media.with_suffix(".transcript.md"),
            ),
        ),
        patch("media2text.core.live.post_process.index_transcript_safe"),
        patch(
            "media2text.core.summarize.hook.maybe_summarize_after_transcribe",
            return_value={},
        ),
        patch(
            "media2text.core.cloud.live_upload.maybe_upload_live_to_aliyundrive",
            return_value={},
        ),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=MagicMock())

    assert result["transcribed"] is True
    assert result["transcribe_engine"] == "whisper"
    mock_backend.transcribe.assert_called_once()


def test_streaming_with_sidecar_skips_rest(tmp_path, monkeypatch) -> None:
    cfg, conn, job_id, media = _setup_job(
        tmp_path,
        monkeypatch,
        write_transcript=True,
        transcribe_status="completed",
    )
    mock_backend = MagicMock()
    with (
        patch(
            "media2text.core.transcribe.factory.create_transcribe_backend",
            return_value=mock_backend,
        ),
        patch(
            "media2text.core.cloud.live_upload.maybe_upload_live_to_aliyundrive",
            return_value={},
        ),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=MagicMock())

    assert result["transcribed"] is True
    assert result.get("transcribe_engine") == "streaming"
    mock_backend.transcribe.assert_not_called()


def test_legacy_no_sidecar_skips_rest_when_transcribe_off(tmp_path, monkeypatch) -> None:
    cfg, conn, job_id, _media = _setup_job(
        tmp_path,
        monkeypatch,
        pipeline_mode="legacy",
        transcribe_status=None,
    )
    mock_backend = MagicMock()
    with patch(
        "media2text.core.transcribe.factory.create_transcribe_backend",
        return_value=mock_backend,
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=MagicMock())

    assert not result.get("transcribed")
    mock_backend.transcribe.assert_not_called()


def test_degraded_event_forces_rest(tmp_path, monkeypatch) -> None:
    cfg, conn, job_id, media = _setup_job(
        tmp_path,
        monkeypatch,
        pipeline_mode=None,
        transcribe_status=None,
    )
    session_id = PostProcessJobRepo(conn).get(job_id).session_id
    record_event(
        conn,
        session_id=session_id,
        stage="streaming_stt",
        status="degraded",
        detail={"reason": "stt_disconnect"},
    )
    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = MagicMock(
        text="ok", segments=[], engine="whisper", model="tiny"
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
                media.with_suffix(".transcript.json"),
                media.with_suffix(".transcript.md"),
            ),
        ),
        patch("media2text.core.live.post_process.index_transcript_safe"),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=MagicMock())

    assert result["transcribed"] is True
    mock_backend.transcribe.assert_called_once()
