from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse

from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.workspace import open_db
from media2text.core.config import AppConfig

pytestmark = pytest.mark.desktop


def _seed_hls_session(workspace: Path, *, with_init: bool = False) -> tuple[str, Path]:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_hls_playback",
        profile_url="https://www.douyin.com/user/sec_hls_playback",
        monitor_enabled=True,
    )
    session_dir = workspace / "creators" / "sec_hls_playback" / "live" / "20260609T120000Z"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    part_path = parts_dir / "seg-00001.m4s"
    part_path.write_bytes(b"fake-m4s-data")
    if with_init:
        (session_dir / "init.mp4").write_bytes(b"fake-init")
    master_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-TARGETDURATION:600",
    ]
    if with_init:
        master_lines.append('#EXT-X-MAP:URI="init.mp4"')
    master_lines.extend(
        [
            "#EXTINF:120.0,",
            "parts/seg-00001.m4s",
            "#EXT-X-ENDLIST",
        ]
    )
    master = session_dir / "master.m3u8"
    master.write_text("\n".join(master_lines) + "\n", encoding="utf-8")
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=str(master),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
        bytes=part_path.stat().st_size,
    )
    conn.close()
    return sid, session_dir


def _seed_hls_session_bare_seg_uris(workspace: Path) -> str:
    """ffmpeg -hls_flags append_list writes seg-NNNNN.m4s without parts/ prefix."""
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_hls_bare_seg",
        profile_url="https://www.douyin.com/user/sec_hls_bare_seg",
        monitor_enabled=True,
    )
    session_dir = workspace / "creators" / "sec_hls_bare_seg" / "live" / "20260611T110019Z"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    (parts_dir / "seg-00005.m4s").write_bytes(b"fake-m4s-5")
    master = session_dir / "master.m3u8"
    master.write_text(
        "\n".join(
            [
                "#EXTM3U",
                '#EXT-X-MAP:URI="init.mp4"',
                "#EXTINF:600.0,",
                "seg-00005.m4s",
                "#EXT-X-ENDLIST",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path=str(master),
        session_dir=str(session_dir),
        pipeline_mode="streaming",
    )
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=5,
        rel_path="parts/seg-00005.m4s",
        state="closed",
    )
    conn.close()
    return sid


def test_playback_m3u8_rewrites_bare_seg_uris(api_client, workspace) -> None:
    sid = _seed_hls_session_bare_seg_uris(workspace)
    r = api_client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert f"/api/sessions/{sid}/parts/5" in r.text
    assert "seg-00005.m4s" not in r.text


def test_playback_m3u8_returns_event_playlist(api_client, workspace) -> None:
    sid, _ = _seed_hls_session(workspace)
    r = api_client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert "EXTM3U" in r.text
    assert f"/api/sessions/{sid}/parts/1" in r.text
    assert "parts/seg-00001.m4s" not in r.text
    assert "application/vnd.apple.mpegurl" in r.headers.get("content-type", "")


def test_playback_part_streams_local_file(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_session(workspace)
    r = api_client.get(f"/api/sessions/{sid}/parts/1")
    assert r.status_code == 200
    assert r.content == (session_dir / "parts" / "seg-00001.m4s").read_bytes()
    assert "video/mp4" in r.headers.get("content-type", "")


def test_playback_part_missing_returns_404(api_client, workspace) -> None:
    sid, _ = _seed_hls_session(workspace)
    r = api_client.get(f"/api/sessions/{sid}/parts/99")
    assert r.status_code == 404


def test_playback_m3u8_missing_session(api_client, workspace) -> None:
    r = api_client.get("/api/sessions/does-not-exist/playback.m3u8")
    assert r.status_code == 404


def test_playback_m3u8_rewrites_init_uri(api_client, workspace) -> None:
    sid, _ = _seed_hls_session(workspace, with_init=True)
    r = api_client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert f'/api/sessions/{sid}/init.mp4' in r.text
    assert 'URI="init.mp4"' not in r.text


def test_playback_init_streams_local_file(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_session(workspace, with_init=True)
    r = api_client.get(f"/api/sessions/{sid}/init.mp4")
    assert r.status_code == 200
    assert r.content == (session_dir / "init.mp4").read_bytes()


def test_cloud_init_redirect_resolves_upload_record(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    cfg.aliyundrive.enabled = True
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_cloud_init",
        profile_url="https://x",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r1",
        temp_path="/x",
        session_dir=str(workspace / "live"),
    )
    from media2text.core.storage.repos import CloudUploadRepo

    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="init.mp4",
        file_kind="init_mp4",
        size=9,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-init",
        cloud_relative_path="media2text/douyin/u/live/init.mp4",
    )
    conn.close()
    cfg.aliyundrive_token_path().write_text('{"refresh_token":"x"}', encoding="utf-8")

    from media2text.api.routes.playback import _cloud_init_redirect

    client = MagicMock()
    client.get_download_url.return_value = "https://cloud.example/init.mp4"
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    conn = open_db(cfg)
    with patch(
        "media2text.api.routes.playback.AliyunDriveClient.open",
        return_value=client,
    ):
        redirect = _cloud_init_redirect(cfg, conn, session_id=sid)
    conn.close()
    assert redirect is not None
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://cloud.example/init.mp4"


def test_playback_init_cloud_redirect(api_client, workspace, monkeypatch) -> None:
    sid, session_dir = _seed_hls_session(workspace, with_init=True)
    (session_dir / "init.mp4").unlink()

    monkeypatch.setattr(
        "media2text.api.routes.playback._cloud_init_redirect",
        lambda _cfg, _conn, *, session_id: RedirectResponse(
            url=f"https://cloud.example/{session_id}/init.mp4",
            status_code=302,
        ),
    )

    r = api_client.get(f"/api/sessions/{sid}/init.mp4", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == f"https://cloud.example/{sid}/init.mp4"


def test_playback_mp4_endpoint(api_client, workspace, monkeypatch) -> None:
    sid, session_dir = _seed_hls_session(workspace, with_init=True)

    monkeypatch.setattr(
        "media2text.api.routes.playback.remux_hls_to_playback_mp4",
        lambda session_dir, *, ffmpeg: session_dir / "playback.mp4",
    )
    fake = session_dir / "playback.mp4"
    fake.write_bytes(b"remuxed-mp4")

    r = api_client.get(f"/api/sessions/{sid}/playback.mp4")
    assert r.status_code == 200
    assert r.content == b"remuxed-mp4"
    assert "video/mp4" in r.headers.get("content-type", "")
