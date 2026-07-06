from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, LiveMediaConfig, SummarizeConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo
from media2text.core.workspace import open_db


def test_hls_finalize_uploads_sidecars_not_whole_mp4(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            media=LiveMediaConfig(format="hls"),
        ),
        summarize=SummarizeConfig(enabled=False),
    )
    cfg.aliyundrive.enabled = True
    conn = open_db(cfg)

    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAhlsfin",
        profile_url="https://x",
        display_name="anchor",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAhlsfin/live/20260609T120000Z"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    (parts_dir / "seg-00001.m4s").write_bytes(b"seg")
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    anchor = session_dir / "20260609T120000Z.flv"
    anchor.write_bytes(b"")
    (anchor.with_suffix(".transcript.json")).write_text("{}", encoding="utf-8")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(master),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )

    sidecar_calls: list[str] = []
    upload_whole_calls: list[str] = []

    def fake_sidecars(*args, **kwargs):
        sidecar_calls.append(kwargs.get("session_id", ""))
        return {"upload_completed": True}

    def fake_whole_upload(*args, **kwargs):
        upload_whole_calls.append(str(kwargs.get("mp4")))
        return {"upload_completed": True}

    monkeypatch.setattr(
        "media2text.core.live.session_finalize.upload_hls_session_sidecars",
        fake_sidecars,
    )
    monkeypatch.setattr(
        "media2text.core.cloud.live_upload.maybe_upload_live_to_aliyundrive",
        fake_whole_upload,
    )

    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        notify=MagicMock(),
    )
    core._streaming_transcript_anchor[sid] = anchor
    core._hls_part_index[sid] = 1

    with patch.object(core, "_process_alive", return_value=False):
        result = core._finalize_recording_streaming_hls(sid, str(master), 0)

    assert result is not None
    assert sidecar_calls == [sid]
    assert not upload_whole_calls
    jobs = PostProcessJobRepo(conn).list_pending(limit=10)
    assert jobs == []


def test_hls_post_process_skips_whole_file_upload(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.aliyundrive.enabled = True
    cfg.summarize.enabled = False
    conn = open_db(cfg)

    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAposthls",
        profile_url="https://x",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAposthls/live/anchor"
    session_dir.mkdir(parents=True)
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    anchor = session_dir / "anchor.flv"
    (anchor.with_suffix(".transcript.json")).write_text("{}", encoding="utf-8")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(master),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )
    LiveSessionRepo(conn).update_status(sid, transcribe_status="completed", status="completed")
    job_id = PostProcessJobRepo(conn).enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=str(master),
    )

    upload_called = {"n": 0}

    def fake_upload(*args, **kwargs):
        upload_called["n"] += 1
        return {}

    monkeypatch.setattr(
        "media2text.core.live.post_process.maybe_upload_live_to_aliyundrive",
        fake_upload,
    )

    result = run_post_process_job(cfg, conn, job_id=job_id, notify=MagicMock())
    assert result["ok"] is True
    assert upload_called["n"] == 0
