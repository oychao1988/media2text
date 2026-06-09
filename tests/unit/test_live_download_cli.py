from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from media2text.cli.live import app
from media2text.core.config import AppConfig
from media2text.core.live.download import download_live_session
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

runner = CliRunner(env={"NO_COLOR": "1"})


def _plain_help(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _seed_session(
    workspace: Path,
    *,
    parts: list[tuple[int, bytes]] | None = None,
    local_deleted: bool = False,
    cloud_uploads: bool = False,
) -> tuple[AppConfig, str, Path]:
    cfg = AppConfig.model_validate(
        {
            "workspace": str(workspace),
            "aliyundrive": {"enabled": cloud_uploads},
        }
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_live_dl",
        profile_url="https://www.douyin.com/user/sec_live_dl",
        monitor_enabled=True,
    )
    session_dir = workspace / "creators" / "sec_live_dl" / "live" / "20260609T120000Z"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")

    manifest = SegmentManifestRepo(conn)
    uploads = CloudUploadRepo(conn)

    for index, data in parts or []:
        rel = f"parts/seg-{index:05d}.m4s"
        part_path = session_dir / rel
        if not local_deleted:
            part_path.write_bytes(data)
        state = "local_deleted" if local_deleted else "closed"
        manifest.upsert_part(
            session_id="pending",
            part_index=index,
            rel_path=rel,
            state=state,
            bytes=len(data),
        )
        if cloud_uploads:
            upload_id = uploads.create(
                session_id="pending",
                creator_id=cid,
                platform="douyin",
                file_name=part_path.name,
                file_kind="m4s",
                local_path=str(part_path) if not local_deleted else None,
                size=len(data),
                part_index=index,
            )
            uploads.mark_done(
                upload_id,
                cloud_file_id=f"cloud-{index}",
                cloud_relative_path=f"media2text/douyin/Tony/live/{session_dir.name}/parts/{part_path.name}",
            )
            if local_deleted:
                manifest.mark_uploaded(
                    "pending",
                    index,
                    cloud_path=f"media2text/douyin/Tony/live/{session_dir.name}/parts/{part_path.name}",
                )

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=str(master),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )

    for index, _ in parts or []:
        manifest.upsert_part(
            session_id=sid,
            part_index=index,
            rel_path=f"parts/seg-{index:05d}.m4s",
            state="local_deleted" if local_deleted else "closed",
            bytes=len((parts or [])[index - 1][1]) if parts else None,
        )
        if cloud_uploads:
            for row in uploads.list_for_session("pending"):
                if row.part_index == index:
                    conn.execute(
                        "UPDATE cloud_uploads SET session_id = ? WHERE id = ?",
                        (sid, row.id),
                    )
            conn.commit()
            if local_deleted:
                manifest.mark_uploaded(
                    sid,
                    index,
                    cloud_path=f"media2text/douyin/Tony/live/{session_dir.name}/parts/seg-{index:05d}.m4s",
                )

    conn.execute("DELETE FROM live_session_parts WHERE session_id = 'pending'")
    conn.commit()
    conn.close()
    return cfg, sid, session_dir


def test_live_download_help() -> None:
    result = runner.invoke(app, ["download", "--help"])
    assert result.exit_code == 0
    help_text = _plain_help(result.stdout)
    assert "--parts" in help_text
    assert "--merge" in help_text
    assert "--keep-local" in help_text
    assert "--json" in help_text


def test_live_download_all_parts_local(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg, sid, session_dir = _seed_session(
        tmp_path / "data",
        parts=[(1, b"part-one"), (2, b"part-two")],
    )
    conn = open_db(cfg)
    payload = download_live_session(cfg, conn, session_id=sid, parts="all")
    conn.close()

    assert payload["ok"] is True
    assert payload["parts_downloaded"] == 2
    assert payload["keep_local"] is False
    assert all(item["source"] == "local" for item in payload["downloads"])
    assert (session_dir / "parts" / "seg-00001.m4s").read_bytes() == b"part-one"


def test_live_download_selected_parts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg, sid, _ = _seed_session(
        tmp_path / "data",
        parts=[(1, b"a"), (2, b"b"), (3, b"c")],
    )
    conn = open_db(cfg)
    payload = download_live_session(cfg, conn, session_id=sid, parts="1,3")
    conn.close()

    assert payload["ok"] is True
    assert payload["parts_downloaded"] == 2
    assert payload["parts_requested"] == [1, 3]


def test_live_download_from_cloud_mock(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    token = tmp_path / "data" / "sessions" / "aliyundrive.token.json"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("{}", encoding="utf-8")

    cfg, sid, session_dir = _seed_session(
        tmp_path / "data",
        parts=[(1, b"cloud-part")],
        local_deleted=True,
        cloud_uploads=True,
    )

    mock_client = MagicMock()
    mock_client.download_bytes.return_value = b"cloud-part"
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    def factory(_path):
        return mock_client

    conn = open_db(cfg)
    payload = download_live_session(
        cfg,
        conn,
        session_id=sid,
        parts="all",
        keep_local=True,
        client_factory=factory,
    )
    conn.close()

    assert payload["ok"] is True
    assert payload["parts_downloaded"] == 1
    assert payload["downloads"][0]["source"] == "cloud"
    mock_client.download_bytes.assert_called_once_with("cloud-1")
    assert (session_dir / "parts" / "seg-00001.m4s").read_bytes() == b"cloud-part"


def test_live_download_merge_success(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg, sid, session_dir = _seed_session(
        tmp_path / "data",
        parts=[(1, b"p1"), (2, b"p2")],
    )
    conn = open_db(cfg)
    with patch("media2text.core.live.download.concat_to_mp4") as mock_concat:
        mock_concat.side_effect = lambda **kwargs: kwargs["dst"].write_bytes(b"merged")
        payload = download_live_session(
            cfg,
            conn,
            session_id=sid,
            parts="all",
            merge=True,
            output_dir=session_dir / "download",
        )
    conn.close()

    assert payload["ok"] is True
    assert payload["merge"] is True
    assert payload["merged_path"] == str(session_dir / "download" / f"{session_dir.name}.mp4")
    mock_concat.assert_called_once()


def test_live_download_merge_failure_keeps_parts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg, sid, session_dir = _seed_session(
        tmp_path / "data",
        parts=[(1, b"p1"), (2, b"p2")],
    )
    conn = open_db(cfg)
    with patch("media2text.core.live.download.concat_to_mp4") as mock_concat:
        mock_concat.side_effect = RuntimeError("ffmpeg boom")
        payload = download_live_session(
            cfg,
            conn,
            session_id=sid,
            parts="all",
            merge=True,
            output_dir=session_dir / "download",
        )
    conn.close()

    assert payload["ok"] is False
    assert payload["merge"] is False
    assert payload["merge_error"] == "ffmpeg boom"
    assert payload["parts_downloaded"] == 2
    assert (session_dir / "download" / "seg-00001.m4s").is_file()
    assert (session_dir / "download" / "seg-00002.m4s").is_file()


def test_live_download_cli_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _, sid, _ = _seed_session(
        tmp_path / "data",
        parts=[(1, b"cli-part")],
    )
    result = runner.invoke(app, ["download", sid, "--parts", "all", "--json"])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert '"parts_downloaded": 1' in result.stdout
    assert '"command": "live download"' in result.stdout


def test_live_download_session_not_found(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    payload = download_live_session(cfg, conn, session_id="missing")
    conn.close()
    assert payload["ok"] is False
    assert payload["error"] == "session_not_found"

    result = runner.invoke(app, ["download", "missing", "--json"])
    assert result.exit_code == 1
    assert '"session_not_found"' in result.stdout
