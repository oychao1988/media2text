import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AliyunDriveConfig, AppConfig, SummarizeConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def test_upload_does_not_wait_for_slow_summarize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        summarize=SummarizeConfig(enabled=True, on_transcribe_complete=True),
        aliyundrive=AliyunDriveConfig(enabled=True, upload_on_live_complete=True),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    jobs = PostProcessJobRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAApost",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAApost/live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260603T120000Z.flv"
    flv.write_bytes(b"x" * 32)
    flv.with_suffix(".transcript.json").write_text(
        '{"engine":"deepgram","text":"hi","segments":[]}',
        encoding="utf-8",
    )
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=None,
    )
    job_id = jobs.enqueue(session_id=sid, creator_id=cid, mp4_path=str(flv))
    jobs.mark_running(job_id)

    order: list[str] = []
    upload_elapsed: list[float] = []

    def slow_summarize(*_a, **_k):
        order.append("summarize_start")
        time.sleep(0.4)
        order.append("summarize_end")
        return {"summarized": True, "summary_path": str(flv.with_suffix(".summary.md"))}

    def fast_upload(*_a, **_k):
        order.append("upload_start")
        t0 = time.monotonic()
        upload_elapsed.append(time.monotonic() - t0)
        return {"upload_completed": True, "cloud_upload_status": "done"}

    notify = MagicMock()
    with (
        patch(
            "media2text.core.summarize.hook.maybe_summarize_after_transcribe",
            side_effect=slow_summarize,
        ),
        patch(
            "media2text.core.live.post_process.maybe_upload_live_to_aliyundrive",
            side_effect=fast_upload,
        ),
        patch(
            "media2text.core.live.post_process.upload_summary_sidecars_if_needed",
            return_value={},
        ),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=notify)

    assert result.get("ok") is True
    assert "upload_start" in order
    assert "summarize_start" in order
    upload_idx = order.index("upload_start")
    summarize_end_idx = order.index("summarize_end")
    assert upload_idx < summarize_end_idx
    assert upload_elapsed and upload_elapsed[0] < 0.15
