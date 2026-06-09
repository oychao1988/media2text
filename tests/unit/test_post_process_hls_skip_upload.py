from unittest.mock import MagicMock, patch

from media2text.core.config import AliyunDriveConfig, AppConfig, SummarizeConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def _seed_hls_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        summarize=SummarizeConfig(enabled=True, on_transcribe_complete=True),
        aliyundrive=AliyunDriveConfig(enabled=True, upload_on_live_complete=True),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAhls",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAhls/live/20260609T120000Z"
    session_dir.mkdir(parents=True)
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    master.with_suffix(".transcript.json").write_text(
        '{"engine":"deepgram","text":"hi","segments":[]}',
        encoding="utf-8",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(master),
        ffmpeg_pid=None,
        pipeline_mode="streaming",
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(master),
        transcribe_status="completed",
        ended=True,
    )
    job_id = PostProcessJobRepo(conn).enqueue(
        session_id=sid, creator_id=cid, mp4_path=str(master)
    )
    jobs = PostProcessJobRepo(conn)
    jobs.mark_running(job_id)
    return cfg, conn, job_id


def test_hls_session_skips_whole_file_upload(tmp_path, monkeypatch) -> None:
    cfg, conn, job_id = _seed_hls_job(tmp_path, monkeypatch)
    notify = MagicMock()
    with (
        patch(
            "media2text.core.summarize.hook.maybe_summarize_after_transcribe",
            return_value={"summarized": True},
        ),
        patch(
            "media2text.core.live.post_process.maybe_upload_live_to_aliyundrive",
        ) as mock_upload,
        patch(
            "media2text.core.live.post_process.upload_summary_sidecars_if_needed",
            return_value={},
        ),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=notify)

    assert result.get("ok") is True
    assert result.get("transcribed") is True
    mock_upload.assert_not_called()
    assert "upload_completed" not in result
