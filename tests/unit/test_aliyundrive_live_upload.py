from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.cloud.aliyundrive import decide_duplicate_action
from media2text.core.cloud.cleanup import RollingCleanupResult, format_rolling_cleanup_notify_body
from media2text.core.cloud.live_upload import (
    _resolve_creator_key,
    _transcribe_gate_open,
    maybe_upload_live_to_aliyundrive,
    rolling_cleanup,
)
from media2text.core.cloud.paths import file_pre_hash, sanitize_path_segment
from media2text.core.config import AliyunDriveConfig, AliyunDriveRollingCleanupConfig, AppConfig, LiveConfig
from media2text.core.storage.models import CreatorRow
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def _creator(**kwargs) -> CreatorRow:
    base = dict(
        id="c1",
        platform="douyin",
        sec_uid="MS4wLjABAAAAtest",
        display_name="Tony/C",
        profile_url="https://example.com/u",
        watch_live=1,
        monitor_enabled=1,
        unique_id="tony",
        avatar_url=None,
        signature=None,
        follower_count=None,
        profile_synced_at="2026-06-01T00:00:00Z",
        created_at="2026-01-01T00:00:00Z",
    )
    base.update(kwargs)
    return CreatorRow(**base)


def _session(conn, creator_id: str, *, transcribe_status: str | None = None) -> str:
    sid = LiveSessionRepo(conn).create(
        creator_id=creator_id,
        room_id="r1",
        temp_path="/tmp/x.flv",
        ffmpeg_pid=1,
    )
    LiveSessionRepo(conn).update_status(
        sid,
        status="completed",
        transcribe_status=transcribe_status,
        ended=True,
    )
    return sid


def test_sanitize_path_segment() -> None:
    assert sanitize_path_segment(" Tony/C ") == "TonyC"
    assert sanitize_path_segment('bad/name\\test') == "badnametest"
    assert sanitize_path_segment("   ") == ""
    assert sanitize_path_segment("x" * 120, max_len=10) == "x" * 10


def test_file_pre_hash(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"hello" + b"\x00" * 2000)
    h1 = file_pre_hash(path)
    h2 = file_pre_hash(path)
    assert h1 == h2
    assert len(h1) == 40


def test_decide_duplicate_action() -> None:
    assert decide_duplicate_action(local_size=10, local_pre_hash="abc", remote_file=None) == "new"
    assert (
        decide_duplicate_action(
            local_size=10,
            local_pre_hash="abc",
            remote_file={"size": 10, "pre_hash": "abc"},
        )
        == "overwrite"
    )
    assert (
        decide_duplicate_action(
            local_size=10,
            local_pre_hash="abc",
            remote_file={"size": 10, "pre_hash": "xyz"},
        )
        == "auto_rename"
    )
    assert (
        decide_duplicate_action(
            local_size=10,
            local_pre_hash="abc",
            remote_file={"size": 99, "pre_hash": "abc"},
        )
        == "auto_rename"
    )


def test_list_cleanup_candidates_filters_transcripts(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    uploads = CloudUploadRepo(conn)

    creator_id = creators.add(
        sec_uid="sec1",
        profile_url="https://example.com/u",
        platform="douyin",
    )
    ready_session = _session(conn, creator_id, transcribe_status="done")
    mp4_id = uploads.create(
        session_id=ready_session,
        creator_id=creator_id,
        platform="douyin",
        file_name="a.mp4",
        file_kind="mp4",
        size=100,
        pre_hash="h1",
    )
    json_id = uploads.create(
        session_id=ready_session,
        creator_id=creator_id,
        platform="douyin",
        file_name="a.transcript.json",
        file_kind="transcript_json",
        size=10,
        pre_hash="h2",
    )
    uploads.mark_done(
        mp4_id,
        cloud_file_id="f-mp4",
        cloud_relative_path="media2text/douyin/u/live/a.mp4",
    )
    uploads.mark_done(
        json_id,
        cloud_file_id="f-json",
        cloud_relative_path="media2text/douyin/u/live/a.transcript.json",
    )

    pending_session = _session(conn, creator_id, transcribe_status="failed")
    pending_mp4 = uploads.create(
        session_id=pending_session,
        creator_id=creator_id,
        platform="douyin",
        file_name="b.mp4",
        file_kind="mp4",
        size=100,
        pre_hash="h3",
    )
    uploads.mark_done(
        pending_mp4,
        cloud_file_id="f-b",
        cloud_relative_path="media2text/douyin/u/live/b.mp4",
    )

    candidates = uploads.list_cleanup_candidates(
        root_prefix="media2text/",
        require_transcripts=True,
    )
    names = {c.file_name for c in candidates}
    assert "a.mp4" in names
    assert "a.transcript.json" not in names  # transcripts/summaries preserved
    assert "b.mp4" not in names


def test_list_cleanup_candidates_includes_completed_streaming_sessions(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creator_id = CreatorRepo(conn).add(
        sec_uid="sec1",
        profile_url="https://example.com/u",
        platform="douyin",
    )
    session_id = _session(conn, creator_id, transcribe_status="completed")
    upload_id = CloudUploadRepo(conn).create(
        session_id=session_id,
        creator_id=creator_id,
        platform="douyin",
        file_name="stream.mp4",
        file_kind="mp4",
        size=100,
        pre_hash="h1",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="f-stream",
        cloud_relative_path="media2text/douyin/u/live/stream.mp4",
    )

    candidates = CloudUploadRepo(conn).list_cleanup_candidates(
        root_prefix="media2text/",
        require_transcripts=False,
    )
    assert {c.file_name for c in candidates} == {"stream.mp4"}


def test_transcribe_gate_blocks_without_sidecar(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(transcribe_on_complete=True),
        aliyundrive=AliyunDriveConfig(upload_transcripts=True),
    )
    mp4 = tmp_path / "live.mp4"
    mp4.write_bytes(b"video")
    ok, reason = _transcribe_gate_open(cfg, mp4, {})
    assert ok is False
    assert reason == "transcribe_pending"


def test_maybe_upload_skipped_when_disabled(tmp_path: Path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data", aliyundrive=AliyunDriveConfig(enabled=False))
    conn = open_db(cfg)
    mp4 = tmp_path / "live.mp4"
    mp4.write_bytes(b"video")
    meta = maybe_upload_live_to_aliyundrive(
        cfg,
        conn,
        session_id="s1",
        mp4=mp4,
        creator=_creator(),
        transcribe_meta={},
    )
    assert meta == {}


def test_maybe_upload_skipped_profile_not_synced(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(enabled=True),
    )
    conn = open_db(cfg)
    mp4 = tmp_path / "live.mp4"
    mp4.write_bytes(b"video")
    creator = _creator(display_name=None)
    with patch(
        "media2text.core.cloud.live_upload.sync_creator_profile",
        return_value={"ok": False, "error": "offline"},
    ):
        meta = maybe_upload_live_to_aliyundrive(
            cfg,
            conn,
            session_id="s1",
            mp4=mp4,
            creator=creator,
            transcribe_meta={},
        )
    assert meta.get("upload_skipped") is True
    assert meta.get("upload_skip_reason") == "profile_not_synced"


def test_rolling_cleanup_deletes_oldest_permanently(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(
            enabled=True,
            root_folder="media2text",
            on_insufficient_space="rolling_cleanup",
        ),
    )
    conn = open_db(cfg)
    creator_id = CreatorRepo(conn).add(sec_uid="s", profile_url="https://x", platform="douyin")
    session_id = _session(conn, creator_id, transcribe_status="done")
    upload_id = CloudUploadRepo(conn).create(
        session_id=session_id,
        creator_id=creator_id,
        platform="douyin",
        file_name="old.mp4",
        file_kind="mp4",
        size=500,
        pre_hash="x",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-old",
        cloud_relative_path="media2text/douyin/u/live/old.mp4",
    )

    client = MagicMock()
    client.get_account_capacity.return_value = MagicMock(free=0)
    deleted = rolling_cleanup(client, cfg=cfg, conn=conn, needed_bytes=1000)
    assert deleted == RollingCleanupResult(db=("old.mp4",))
    client.delete_file_permanently.assert_called_once_with("cloud-old")
    client.trash.assert_not_called()


def test_rolling_cleanup_drops_stale_recycle_bin_db_record(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(
            enabled=True,
            root_folder="media2text",
            on_insufficient_space="rolling_cleanup",
        ),
    )
    conn = open_db(cfg)
    creator_id = CreatorRepo(conn).add(sec_uid="s", profile_url="https://x", platform="douyin")
    session_id = _session(conn, creator_id, transcribe_status="done")
    upload_id = CloudUploadRepo(conn).create(
        session_id=session_id,
        creator_id=creator_id,
        platform="douyin",
        file_name="trashed.mp4",
        file_kind="mp4",
        size=500,
        pre_hash="x",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-trashed",
        cloud_relative_path="media2text/douyin/u/live/trashed.mp4",
    )

    client = MagicMock()
    client.get_account_capacity.return_value = MagicMock(free=0)
    client.delete_file_permanently.side_effect = RuntimeError(
        '/v3/file/delete failed 400: {"code":"OperationNotSupport",'
        '"message":"This operation is not supported. file in system recycle bin is not supported"}'
    )
    deleted = rolling_cleanup(client, cfg=cfg, conn=conn, needed_bytes=1000)
    assert deleted == RollingCleanupResult(db=("trashed.mp4",))
    assert CloudUploadRepo(conn).list_for_session(session_id) == []


def test_rolling_cleanup_drops_missing_cloud_file_db_record(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(
            enabled=True,
            root_folder="media2text",
            on_insufficient_space="rolling_cleanup",
        ),
    )
    conn = open_db(cfg)
    creator_id = CreatorRepo(conn).add(sec_uid="s", profile_url="https://x", platform="douyin")
    session_id = _session(conn, creator_id, transcribe_status="done")
    upload_id = CloudUploadRepo(conn).create(
        session_id=session_id,
        creator_id=creator_id,
        platform="douyin",
        file_name="missing.mp4",
        file_kind="mp4",
        size=500,
        pre_hash="x",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-missing",
        cloud_relative_path="media2text/douyin/u/live/missing.mp4",
    )

    client = MagicMock()
    client.get_account_capacity.return_value = MagicMock(free=0)
    client.delete_file_permanently.side_effect = RuntimeError(
        '/v3/file/delete failed 404: {"code":"NotFound.FileId","message":"The resource cannot be found."}'
    )
    deleted = rolling_cleanup(client, cfg=cfg, conn=conn, needed_bytes=1000)
    assert deleted == RollingCleanupResult(db=("missing.mp4",))
    assert CloudUploadRepo(conn).list_for_session(session_id) == []


def test_rolling_cleanup_dedupes_and_drops_all_stale_rows(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(
            enabled=True,
            root_folder="media2text",
            on_insufficient_space="rolling_cleanup",
        ),
    )
    conn = open_db(cfg)
    creator_id = CreatorRepo(conn).add(sec_uid="s", profile_url="https://x", platform="douyin")
    session_id = _session(conn, creator_id, transcribe_status="done")
    repo = CloudUploadRepo(conn)
    for _ in range(3):
        upload_id = repo.create(
            session_id=session_id,
            creator_id=creator_id,
            platform="douyin",
            file_name="dup.mp4",
            file_kind="mp4",
            size=500,
            pre_hash="x",
        )
        repo.mark_done(
            upload_id,
            cloud_file_id="cloud-dup",
            cloud_relative_path="media2text/douyin/u/live/dup.mp4",
        )

    client = MagicMock()
    client.get_account_capacity.return_value = MagicMock(free=0)
    client.delete_file_permanently.side_effect = RuntimeError(
        '/v3/file/delete failed 404: {"code":"NotFound.FileId","message":"The resource cannot be found."}'
    )
    deleted = rolling_cleanup(client, cfg=cfg, conn=conn, needed_bytes=1000)
    assert deleted == RollingCleanupResult(db=("dup.mp4",))
    assert CloudUploadRepo(conn).list_for_session(session_id) == []
    client.delete_file_permanently.assert_called_once_with("cloud-dup")


def test_list_cleanup_candidates_video_only_when_no_transcript_gate(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    uploads = CloudUploadRepo(conn)

    creator_id = creators.add(
        sec_uid="sec1",
        profile_url="https://example.com/u",
        platform="douyin",
    )
    session_id = _session(conn, creator_id, transcribe_status="done")
    m4s_id = uploads.create(
        session_id=session_id,
        creator_id=creator_id,
        platform="douyin",
        file_name="seg-00001.m4s",
        file_kind="m4s",
        size=1000,
        pre_hash="h1",
    )
    json_id = uploads.create(
        session_id=session_id,
        creator_id=creator_id,
        platform="douyin",
        file_name="a.transcript.json",
        file_kind="transcript_json",
        size=10,
        pre_hash="h2",
    )
    uploads.mark_done(
        m4s_id,
        cloud_file_id="f-m4s",
        cloud_relative_path="media2text/douyin/u/live/parts/seg-00001.m4s",
    )
    uploads.mark_done(
        json_id,
        cloud_file_id="f-json",
        cloud_relative_path="media2text/douyin/u/live/a.transcript.json",
    )

    candidates = uploads.list_cleanup_candidates(
        root_prefix="media2text/",
        require_transcripts=False,
    )
    names = {c.file_name for c in candidates}
    assert names == {"seg-00001.m4s"}


def test_rolling_cleanup_purges_recycle_bin_videos(tmp_path: Path) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(
            enabled=True,
            root_folder="media2text",
            on_insufficient_space="rolling_cleanup",
            rolling_cleanup=AliyunDriveRollingCleanupConfig(purge_recycle_bin=True),
        ),
    )
    conn = open_db(cfg)
    client = MagicMock()
    client.get_account_capacity.return_value = MagicMock(free=0)
    client.list_recycle_bin.return_value = [
        {
            "type": "file",
            "file_id": "rb-json",
            "name": "notes.transcript.json",
            "size": 100,
            "updated_at": "2026-01-01T00:00:00Z",
        },
        {
            "type": "file",
            "file_id": "rb-mp4",
            "name": "old-live.mp4",
            "size": 5000,
            "updated_at": "2026-01-02T00:00:00Z",
        },
    ]

    deleted = rolling_cleanup(client, cfg=cfg, conn=conn, needed_bytes=100_000)
    assert deleted == RollingCleanupResult(recycle_bin=("old-live.mp4",))
    client.delete_file_permanently.assert_called_once_with("rb-mp4")


def test_format_rolling_cleanup_notify_body_sections() -> None:
    body = format_rolling_cleanup_notify_body(
        RollingCleanupResult(db=("a.mp4",), recycle_bin=("b.mp4",))
    )
    assert "[DB 记录]" in body
    assert "[回收站]" in body
    assert "- a.mp4" in body
    assert "- b.mp4" in body


def test_resolve_creator_key_sanitizes_nickname(tmp_path: Path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    key, reason = _resolve_creator_key(cfg, conn, _creator(display_name=" Tony/C "))
    assert reason is None
    assert key == "TonyC"
