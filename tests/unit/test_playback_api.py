from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.responses import StreamingResponse

from media2text.api.deps import get_cfg
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
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


def _seed_hls_multi_part_session(workspace: Path) -> tuple[str, Path]:
    """Two-part HLS session with discontinuity (dogfood-shaped)."""
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_hls_multi_part",
        profile_url="https://www.douyin.com/user/sec_hls_multi_part",
        monitor_enabled=True,
    )
    session_dir = workspace / "creators" / "sec_hls_multi_part" / "live" / "20260611T110019Z"
    parts_dir = session_dir / "parts"
    parts_dir.mkdir(parents=True)
    (parts_dir / "seg-00001.m4s").write_bytes(b"fake-m4s-part-1")
    (parts_dir / "seg-00002.m4s").write_bytes(b"fake-m4s-part-2")
    (session_dir / "init.mp4").write_bytes(b"fake-init")
    master = session_dir / "master.m3u8"
    master.write_text(
        "\n".join(
            [
                "#EXTM3U",
                '#EXT-X-MAP:URI="init.mp4"',
                "#EXT-X-DISCONTINUITY",
                "#EXTINF:600.0,",
                "seg-00001.m4s",
                "#EXTINF:30.76,",
                "seg-00002.m4s",
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
    for part_index, size in ((1, 16), (2, 16)):
        SegmentManifestRepo(conn).upsert_part(
            session_id=sid,
            part_index=part_index,
            rel_path=f"parts/seg-{part_index:05d}.m4s",
            state="closed",
            bytes=size,
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
    conn = open_db(AppConfig.model_validate({"workspace": str(workspace)}))
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
    conn = open_db(AppConfig.model_validate({"workspace": str(workspace)}))
    with patch(
        "media2text.api.routes.playback.AliyunDriveClient.open",
        return_value=client,
    ):
        redirect = _cloud_init_redirect(cfg, conn, session_id=sid)
    conn.close()
    assert redirect is not None
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://cloud.example/init.mp4"


def _enable_aliyun_for_client(api_client, workspace: Path) -> AppConfig:
    cfg = api_client.app.dependency_overrides[get_cfg]()
    cfg.aliyundrive.enabled = True
    token_path = workspace / "sessions" / "aliyundrive.token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text('{"refresh_token":"x"}', encoding="utf-8")
    api = getattr(api_client.app.state, "api_app", None)
    if api is not None:
        api.dependency_overrides[get_cfg] = api_client.app.dependency_overrides[get_cfg]
    return cfg


def _enable_aliyun(cfg: AppConfig, workspace: Path) -> None:
    cfg.aliyundrive.enabled = True
    token_path = workspace / "sessions" / "aliyundrive.token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text('{"refresh_token":"x"}', encoding="utf-8")


def _mock_cloud_stream(*, status_code: int, content: bytes, content_range: str | None = None):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    headers = {"content-type": "video/mp4", "content-length": str(len(content))}
    if content_range:
        headers["content-range"] = content_range
    mock_resp.headers = headers
    mock_resp.iter_bytes.return_value = [content]
    mock_upstream = MagicMock()
    mock_upstream.__enter__ = MagicMock(return_value=mock_resp)
    mock_upstream.__exit__ = MagicMock(return_value=False)
    return mock_upstream


def test_playback_m3u8_preserves_discontinuity_tags(api_client, workspace) -> None:
    sid, _ = _seed_hls_multi_part_session(workspace)
    r = api_client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert "#EXT-X-DISCONTINUITY" in r.text
    assert f"/api/sessions/{sid}/parts/1" in r.text
    assert f"/api/sessions/{sid}/parts/2" in r.text


def test_get_part_cloud_proxies_range_part2(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_multi_part_session(workspace)
    (session_dir / "parts" / "seg-00002.m4s").unlink()

    conn = open_db(AppConfig.model_validate({"workspace": str(workspace)}))
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="local_deleted",
        bytes=16,
    )
    conn.close()

    mock_resp = StreamingResponse(
        iter([b"fake-m4s-part-2"]),
        status_code=206,
        headers={"Content-Range": "bytes 0-15/16"},
        media_type="video/mp4",
    )
    mock_upload = MagicMock(cloud_file_id="cf-part-2")
    with (
        patch(
            "media2text.api.routes.playback.find_part_upload",
            return_value=mock_upload,
        ),
        patch(
            "media2text.api.routes.playback._stream_cloud_upload",
            return_value=mock_resp,
        ) as mock_stream,
    ):
        r = api_client.get(f"/api/sessions/{sid}/parts/2", headers={"Range": "bytes=0-15"})
    assert r.status_code == 206
    assert r.content == b"fake-m4s-part-2"
    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["range_header"] == "bytes=0-15"
    assert r.headers.get("location") is None


def test_multi_part_cloud_proxy_part1_and_part2_return_206(api_client, workspace) -> None:
    """US10: both parts use Range proxy (not 302) when local segments are missing."""
    sid, session_dir = _seed_hls_multi_part_session(workspace)
    for part_index in (1, 2):
        (session_dir / "parts" / f"seg-{part_index:05d}.m4s").unlink()

    conn = open_db(AppConfig.model_validate({"workspace": str(workspace)}))
    for part_index in (1, 2):
        SegmentManifestRepo(conn).upsert_part(
            session_id=sid,
            part_index=part_index,
            rel_path=f"parts/seg-{part_index:05d}.m4s",
            state="uploaded",
            bytes=16,
        )
    conn.close()

    def _fake_stream(_cfg, upload, *, range_header, media_type="video/mp4"):
        part_num = upload.cloud_file_id.split("-")[-1]
        body = f"part-{part_num}".encode()
        return StreamingResponse(
            iter([body]),
            status_code=206,
            headers={"Content-Range": f"bytes 0-{len(body) - 1}/{len(body)}"},
            media_type=media_type,
        )

    def _find_upload(_conn, *, session_id, part_index):
        return MagicMock(cloud_file_id=f"cf-part-{part_index}")

    with patch(
        "media2text.api.routes.playback.find_part_upload",
        side_effect=_find_upload,
    ), patch(
        "media2text.api.routes.playback._stream_cloud_upload",
        side_effect=_fake_stream,
    ):
        for part_index in (1, 2):
            r = api_client.get(
                f"/api/sessions/{sid}/parts/{part_index}",
                headers={"Range": "bytes=0-"},
            )
            assert r.status_code == 206, f"part {part_index}"
            assert r.headers.get("location") is None
            assert r.content == f"part-{part_index}".encode()


def test_get_part_cloud_proxies_range(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_session(workspace)
    (session_dir / "parts" / "seg-00001.m4s").unlink()

    conn = open_db(AppConfig.model_validate({"workspace": str(workspace)}))
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="local_deleted",
        bytes=14,
    )
    conn.close()

    mock_resp = StreamingResponse(
        iter([b"fake-m4s-data"]),
        status_code=206,
        headers={"Content-Range": "bytes 0-13/14"},
        media_type="video/mp4",
    )
    mock_upload = MagicMock(cloud_file_id="cf-part-1")
    with (
        patch(
            "media2text.api.routes.playback.find_part_upload",
            return_value=mock_upload,
        ),
        patch(
            "media2text.api.routes.playback._stream_cloud_upload",
            return_value=mock_resp,
        ) as mock_stream,
    ):
        r = api_client.get(f"/api/sessions/{sid}/parts/1", headers={"Range": "bytes=0-13"})
    assert r.status_code == 206
    assert r.content == b"fake-m4s-data"
    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["range_header"] == "bytes=0-13"


def test_get_part_cloud_proxies_full_range(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_session(workspace)
    (session_dir / "parts" / "seg-00001.m4s").unlink()

    conn = open_db(AppConfig.model_validate({"workspace": str(workspace)}))
    SegmentManifestRepo(conn).upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="uploaded",
        bytes=14,
    )
    conn.close()

    captured: dict = {}
    mock_upload = MagicMock(cloud_file_id="cf-part-1")

    def _fake_stream(_cfg, upload, *, range_header, media_type="video/mp4"):
        captured["upload"] = upload
        captured["range"] = range_header
        return StreamingResponse(
            iter([b"fake-m4s-data"]),
            status_code=206,
            headers={"Content-Range": "bytes 0-13/14", "Accept-Ranges": "bytes"},
            media_type=media_type,
        )

    with (
        patch(
            "media2text.api.routes.playback.find_part_upload",
            return_value=mock_upload,
        ),
        patch("media2text.api.routes.playback._stream_cloud_upload", side_effect=_fake_stream),
    ):
        r = api_client.get(f"/api/sessions/{sid}/parts/1", headers={"Range": "bytes=0-"})
    assert r.status_code == 206
    assert captured.get("range") == "bytes=0-"
    assert r.headers.get("location") is None


def test_playback_init_cloud_proxies_range(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_session(workspace, with_init=True)
    (session_dir / "init.mp4").unlink()

    mock_resp = StreamingResponse(
        iter([b"fake-init"]),
        status_code=206,
        headers={"Content-Range": "bytes 0-8/9"},
        media_type="video/mp4",
    )
    mock_upload = MagicMock(cloud_file_id="cloud-init")
    with (
        patch(
            "media2text.api.routes.playback.find_init_upload",
            return_value=mock_upload,
        ),
        patch(
            "media2text.api.routes.playback._stream_cloud_upload",
            return_value=mock_resp,
        ) as mock_stream,
    ):
        r = api_client.get(f"/api/sessions/{sid}/init.mp4", headers={"Range": "bytes=0-8"})
    assert r.status_code == 206
    assert r.content == b"fake-init"
    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["range_header"] == "bytes=0-8"


def test_playback_m3u8_from_cloud_when_local_master_missing(api_client, workspace) -> None:
    sid, session_dir = _seed_hls_session(workspace)
    (session_dir / "master.m3u8").unlink()
    cfg = _enable_aliyun_for_client(api_client, workspace)

    conn = open_db(cfg)
    from media2text.core.storage.repos import CloudUploadRepo

    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=LiveSessionRepo(conn).get(sid).creator_id,
        platform="douyin",
        file_name="master.m3u8",
        file_kind="m3u8",
        size=100,
        pre_hash="abc",
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cloud-m3u8",
        cloud_relative_path="media2text/douyin/u/live/master.m3u8",
    )
    conn.close()

    cloud_text = "\n".join(
        [
            "#EXTM3U",
            "#EXTINF:120.0,",
            "parts/seg-00001.m4s",
            "#EXT-X-ENDLIST",
        ]
    ) + "\n"

    mock_http = MagicMock()
    mock_http.status_code = 200
    mock_http.text = cloud_text
    drive = MagicMock()
    drive.get_download_url.return_value = "https://cloud.example/master.m3u8"
    drive.__enter__ = MagicMock(return_value=drive)
    drive.__exit__ = MagicMock(return_value=False)

    with (
        patch("media2text.api.routes.playback.AliyunDriveClient.open", return_value=drive),
        patch("media2text.api.routes.playback.httpx.get", return_value=mock_http) as mock_get,
    ):
        r = api_client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert mock_get.call_args.kwargs["headers"]["Referer"] == "https://www.aliyundrive.com/"
    assert f"/api/sessions/{sid}/parts/1" in r.text
    assert "parts/seg-00001.m4s" not in r.text


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
