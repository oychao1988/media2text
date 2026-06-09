from pathlib import Path

import pytest

from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.workspace import open_db
from media2text.core.config import AppConfig

pytestmark = pytest.mark.desktop


def _seed_hls_session(workspace: Path) -> tuple[str, Path]:
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
    master = session_dir / "master.m3u8"
    master.write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:7",
                "#EXT-X-TARGETDURATION:600",
                "#EXTINF:120.0,",
                "parts/seg-00001.m4s",
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
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
        bytes=part_path.stat().st_size,
    )
    conn.close()
    return sid, session_dir


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
    assert "video/iso.segment" in r.headers.get("content-type", "")


def test_playback_part_missing_returns_404(api_client, workspace) -> None:
    sid, _ = _seed_hls_session(workspace)
    r = api_client.get(f"/api/sessions/{sid}/parts/99")
    assert r.status_code == 404


def test_playback_m3u8_missing_session(api_client, workspace) -> None:
    r = api_client.get("/api/sessions/does-not-exist/playback.m3u8")
    assert r.status_code == 404
