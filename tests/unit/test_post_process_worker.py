from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, TranscribeConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def test_run_post_process_job_transcribe_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(transcribe_on_complete=True),
        transcribe=TranscribeConfig(engine="whisper"),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAApp",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    mp4 = tmp_path / "data/creators/MS4wLjABAAAApp/live/x.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(mp4.with_suffix(".flv")),
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid, status="completed", local_path=str(mp4), ended=True
    )
    job = PostProcessJobRepo(conn).enqueue(
        session_id=sid, creator_id=cid, mp4_path=str(mp4)
    )

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
            return_value=(mp4.with_suffix(".transcript.json"), mp4.with_suffix(".transcript.md")),
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
    row = PostProcessJobRepo(conn).get(job)
    assert row is not None
    assert row.status == "done"
