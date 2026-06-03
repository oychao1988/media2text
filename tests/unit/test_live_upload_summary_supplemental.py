from unittest.mock import MagicMock, patch

from media2text.core.cloud.live_upload import upload_summary_sidecars_if_needed
from media2text.core.config import AliyunDriveConfig, AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def test_upload_summary_sidecars_when_upload_already_done(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(
            enabled=True,
            upload_transcripts=True,
            upload_on_live_complete=True,
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAsupp",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_dir = tmp_path / "data/creators/MS4wLjABAAAAsupp/live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260603T120000Z.flv"
    flv.write_bytes(b"x" * 32)
    summary_md = flv.with_suffix(".summary.md")
    summary_md.write_text("# summary\n", encoding="utf-8")
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=None,
    )
    sessions.update_status(sid, cloud_upload_status="done")
    creator = creators.get(cid)

    token_path = cfg.aliyundrive_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text('{"refresh_token":"rt"}', encoding="utf-8")

    mock_client = MagicMock()
    mock_client.ensure_folder_path.return_value = "folder123"

    with (
        patch(
            "media2text.core.cloud.live_upload.AliyunDriveClient.open"
        ) as mock_open,
        patch(
            "media2text.core.cloud.live_upload._resolve_creator_key",
            return_value=("nickname", None),
        ),
        patch(
            "media2text.core.cloud.live_upload._upload_summary_sidecars",
            return_value={"upload_supplemental": True, "files": ["summary.md"]},
        ) as mock_upload,
    ):
        mock_open.return_value.__enter__.return_value = mock_client
        result = upload_summary_sidecars_if_needed(
            cfg,
            conn,
            session_id=sid,
            media=flv,
            creator=creator,
            notify=MagicMock(),
        )

    assert result.get("upload_supplemental") is True
    mock_upload.assert_called_once()


def test_upload_summary_sidecars_skips_when_upload_not_done(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        aliyundrive=AliyunDriveConfig(enabled=True, upload_transcripts=True),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    sessions = LiveSessionRepo(conn)
    cid = creators.add(
        sec_uid="MS4wLjABAAAAskip",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAskip/live/x.flv"
    flv.parent.mkdir(parents=True)
    flv.write_bytes(b"x")
    flv.with_suffix(".summary.md").write_text("# s", encoding="utf-8")
    sid = sessions.create(
        creator_id=cid,
        room_id="1",
        temp_path=str(flv),
        ffmpeg_pid=None,
    )
    creator = creators.get(cid)

    result = upload_summary_sidecars_if_needed(
        cfg,
        conn,
        session_id=sid,
        media=flv,
        creator=creator,
    )

    assert result == {}
