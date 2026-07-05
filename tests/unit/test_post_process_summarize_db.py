import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, SummarizeConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    PipelineEventRepo,
    PostProcessJobRepo,
)
from media2text.core.workspace import open_db


def _seed_summarize_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        summarize=SummarizeConfig(enabled=True, on_transcribe_complete=True),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsum",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    mp4 = tmp_path / "data/creators/MS4wLjABAAAAsum/live/x.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    mp4.with_suffix(".transcript.json").write_text(
        '{"engine":"whisper","text":"hi","segments":[]}',
        encoding="utf-8",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(mp4.with_suffix(".flv")),
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        local_path=str(mp4),
        transcribe_status="completed",
        ended=True,
    )
    job_id = PostProcessJobRepo(conn).enqueue(
        session_id=sid, creator_id=cid, mp4_path=str(mp4)
    )
    PostProcessJobRepo(conn).mark_running(job_id)
    return cfg, conn, job_id, sid


def test_summarize_releases_db_during_llm(tmp_path, monkeypatch) -> None:
    cfg, conn, job_id, _sid = _seed_summarize_job(tmp_path, monkeypatch)

    def slow_summarize(*_a, **_k):
        with patch(
            "media2text.core.live.post_process.gateway_write",
            side_effect=AssertionError("gateway_write called during LLM"),
        ):
            time.sleep(0.02)
        return {"summarized": True, "summary_path": "x.summary.md"}

    notify = MagicMock()
    with (
        patch(
            "media2text.core.summarize.hook.maybe_summarize_after_transcribe",
            side_effect=slow_summarize,
        ),
        patch("media2text.core.live.post_process.refresh_manifest"),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=notify)

    assert result.get("ok") is True
    assert result.get("summarized") is True


def test_summarize_failure_marks_pipeline_event_failed(tmp_path, monkeypatch) -> None:
    cfg, conn, job_id, sid = _seed_summarize_job(tmp_path, monkeypatch)
    notify = MagicMock()

    with (
        patch(
            "media2text.core.summarize.hook.maybe_summarize_after_transcribe",
            side_effect=RuntimeError("llm down"),
        ),
        patch("media2text.core.live.post_process.refresh_manifest"),
    ):
        result = run_post_process_job(cfg, conn, job_id=job_id, notify=notify)

    assert result.get("summarize_error") == "llm down"
    events = PipelineEventRepo(conn).list_for_session(sid)
    summarize_events = [e for e in events if e.stage == "summarize"]
    assert len(summarize_events) == 1
    assert summarize_events[0].status == "failed"
    assert summarize_events[0].duration_ms is not None
