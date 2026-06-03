from unittest.mock import MagicMock

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo


def test_session_pipeline_mode_snapshot_overrides_runtime_config(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(pipeline_mode="legacy"),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsnap",
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
    assert core._use_streaming_pipeline(sid) is True
    assert core._use_streaming_pipeline(None) is False


def test_post_process_job_media_path_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAmedia",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
    )
    flv = str(tmp_path / "data/creators/x/live/20260603T120000Z.flv")
    job_id = PostProcessJobRepo(conn).enqueue(
        session_id=sid,
        creator_id=cid,
        mp4_path=flv,
    )
    job = PostProcessJobRepo(conn).get(job_id)
    assert job is not None
    assert job.media_path == flv
    assert job.media_path == job.mp4_path
