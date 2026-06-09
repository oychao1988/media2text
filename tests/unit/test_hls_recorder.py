from unittest.mock import MagicMock, patch

from media2text.core.config import LiveCompressConfig
from media2text.core.live.hls_recorder import (
    append_discontinuity_to_playlist,
    build_hls_recorder_args,
    finalize_hls_endlist,
    rotate_hls_after_reconnect,
    spawn_hls_recorder,
    stop_hls_recorder,
)
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def test_hls_recorder_builds_event_playlist_args(tmp_path) -> None:
    out_dir = tmp_path / "session"
    args = build_hls_recorder_args(
        ffmpeg="ffmpeg",
        stream_url="http://example.com/live.flv",
        session_dir=out_dir,
        segment_sec=600,
        compress_cfg=LiveCompressConfig(enabled=False),
    )
    assert "-f" in args and "hls" in args
    assert "-hls_playlist_type" in args
    assert "event" in args
    assert "-hls_segment_type" in args
    assert "fmp4" in args
    assert str(out_dir / "master.m3u8") in args
    assert "seg-%05d.m4s" in " ".join(args)


def test_hls_recorder_compress_args_when_enabled(tmp_path) -> None:
    args = build_hls_recorder_args(
        ffmpeg="ffmpeg",
        stream_url="http://example.com/live.flv",
        session_dir=tmp_path / "session",
        segment_sec=600,
        compress_cfg=LiveCompressConfig(enabled=True, video_bitrate="2M"),
    )
    joined = " ".join(args)
    assert "hevc_videotoolbox" in joined
    assert "2M" in joined


@patch("media2text.core.live.hls_recorder.subprocess.Popen")
def test_spawn_hls_recorder(mock_popen, tmp_path) -> None:
    mock_popen.return_value = MagicMock()
    proc = spawn_hls_recorder(
        ffmpeg="ffmpeg",
        stream_url="http://x",
        session_dir=tmp_path / "s",
        segment_sec=60,
        compress_cfg=LiveCompressConfig(),
        start_segment_number=3,
    )
    assert proc is mock_popen.return_value
    cmd = mock_popen.call_args[0][0]
    assert "-start_number" in cmd
    idx = cmd.index("-start_number")
    assert cmd[idx + 1] == "3"


def test_stop_hls_recorder_delegates_to_stop_process() -> None:
    proc = MagicMock()
    proc.poll.return_value = None
    with patch("media2text.core.live.hls_recorder.stop_process") as mock_stop:
        stop_hls_recorder(proc, timeout=5)
    mock_stop.assert_called_once_with(proc, timeout=5)


def test_finalize_hls_endlist_appends_marker(tmp_path) -> None:
    master = tmp_path / "master.m3u8"
    master.write_text("#EXTM3U\n#EXT-X-VERSION:7\n", encoding="utf-8")
    finalize_hls_endlist(tmp_path)
    text = master.read_text(encoding="utf-8")
    assert "#EXT-X-ENDLIST" in text


def test_hls_reconnect_appends_discontinuity_and_new_index(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAhls",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAhls/live/20260609T120000Z"
    session_dir.mkdir(parents=True)
    (session_dir / "parts").mkdir()
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(master),
        session_dir=str(session_dir),
    )
    repo = SegmentManifestRepo(conn)
    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="closed",
    )
    repo.upsert_part(
        session_id=sid,
        part_index=2,
        rel_path="parts/seg-00002.m4s",
        state="closed",
    )

    rotate_hls_after_reconnect(
        conn=conn,
        session_id=sid,
        session_dir=session_dir,
        next_index=3,
        discontinuity_seq=1,
    )
    text = master.read_text(encoding="utf-8")
    assert "EXT-X-DISCONTINUITY" in text

    repo.upsert_part(
        session_id=sid,
        part_index=3,
        rel_path="parts/seg-00003.m4s",
        state="recording",
        discontinuity_seq=1,
    )
    row = repo.get_part(sid, 3)
    assert row is not None
    assert row.part_index == 3
    assert row.discontinuity_seq == 1


def test_append_discontinuity_appends_each_reconnect(tmp_path) -> None:
    master = tmp_path / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    append_discontinuity_to_playlist(tmp_path)
    append_discontinuity_to_playlist(tmp_path)
    assert master.read_text(encoding="utf-8").count("#EXT-X-DISCONTINUITY") == 2


def test_append_discontinuity_before_endlist(tmp_path) -> None:
    master = tmp_path / "master.m3u8"
    master.write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")
    append_discontinuity_to_playlist(tmp_path)
    text = master.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    assert lines[-1] == "#EXT-X-ENDLIST"
    assert lines[-2] == "#EXT-X-DISCONTINUITY"


def test_rotate_hls_after_reconnect_twice_appends_two_markers(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    rotate_hls_after_reconnect(
        conn=None,
        session_id="s1",
        session_dir=session_dir,
        next_index=2,
        discontinuity_seq=1,
    )
    rotate_hls_after_reconnect(
        conn=None,
        session_id="s1",
        session_dir=session_dir,
        next_index=3,
        discontinuity_seq=2,
    )
    assert master.read_text(encoding="utf-8").count("#EXT-X-DISCONTINUITY") == 2
