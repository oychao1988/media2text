from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.cloud.live_upload import upload_live_part
from media2text.core.config import AppConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.models import CreatorRow
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def _creator(**kwargs) -> CreatorRow:
    base = dict(
        id="c1",
        platform="douyin",
        sec_uid="MS4wLjABAAAAhlsup",
        display_name="Tony",
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


def test_upload_live_part_uploads_init_and_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.aliyundrive.enabled = True
    token_path = tmp_path / "data/sessions/aliyundrive.token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text('{"refresh_token":"x"}', encoding="utf-8")

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAhlsup",
        profile_url="https://x",
        display_name="Tony",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAhlsup/live/anchor"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    part_path = parts_dir / "seg-00001.m4s"
    part_path.write_bytes(b"segment")
    (session_dir / "init.mp4").write_bytes(b"init")
    (session_dir / "master.m3u8").write_text("#EXTM3U\n", encoding="utf-8")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(session_dir / "master.m3u8"),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
        bytes=part_path.stat().st_size,
        duration_sec=120.0,
    )

    uploads: list[tuple[str, str | None]] = []

    def fake_upload(*_a, **kwargs):
        uploads.append((kwargs["file_kind"], kwargs.get("part_index")))
        return {"cloud_file_id": "f1", "cloud_path": "media2text/douyin/Tony/live/anchor/x"}

    client = MagicMock()
    client.get_account_capacity.return_value = MagicMock(free=10_000_000_000)
    client.ensure_folder_path.return_value = "folder-id"
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    with (
        patch("media2text.core.cloud.live_upload.AliyunDriveClient.open", return_value=client),
        patch("media2text.core.cloud.live_upload._upload_file_to_cloud", side_effect=fake_upload),
    ):
        result = upload_live_part(
            cfg,
            conn,
            session_id=sid,
            session_dir=session_dir,
            part_index=1,
            part_path=part_path,
            creator=_creator(id=cid),
        )

    assert result["ok"] is True
    kinds = [kind for kind, _ in uploads]
    assert "m4s" in kinds
    assert "init_mp4" in kinds
    assert "manifest_json" in kinds
    assert "m3u8" in kinds
    assert (session_dir / "session.manifest.json").is_file()
