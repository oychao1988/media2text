import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.live.hls_recorder import restore_hls_init_if_empty
from media2text.core.live.recording import LiveRecordingCore, RECONNECT_COOLDOWN_SEC
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db


def test_restore_hls_init_if_empty_copies_latest_archive(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "init.mp4").write_bytes(b"")
    (session_dir / "init-1.mp4").write_bytes(b"init-v1")
    (session_dir / "init-2.mp4").write_bytes(b"init-v2")

    assert restore_hls_init_if_empty(session_dir) is True
    assert (session_dir / "init.mp4").read_bytes() == b"init-v2"


def test_restore_hls_init_if_empty_skips_when_nonempty(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "init.mp4").write_bytes(b"ok")
    (session_dir / "init-1.mp4").write_bytes(b"archived")

    assert restore_hls_init_if_empty(session_dir) is False
    assert (session_dir / "init.mp4").read_bytes() == b"ok"


def test_hls_within_segment_quiet_period_long_segments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.live.media.segment_duration_sec = 600
    conn = open_db(cfg)
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        notify=MagicMock(),
    )
    session_dir = tmp_path / "sess"
    parts = session_dir / "parts"
    parts.mkdir(parents=True)
    seg = parts / "seg-00001.m4s"
    seg.write_bytes(b"x" * 1000)
    old = seg.stat().st_mtime
    os.utime(seg, (old - 120, old - 120))

    assert core._hls_within_segment_quiet_period(session_dir) is True

    os.utime(seg, (old - 700, old - 700))
    assert core._hls_within_segment_quiet_period(session_dir) is False
    conn.close()


def test_hls_stall_skipped_during_stream_reconnect_same_tick(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.live.media.segment_duration_sec = 600
    cfg.live.streaming_stt.enabled = True
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstall",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    session_dir = tmp_path / "data/creators/MS4wLjABAAAAstall/live/20260617T120000Z"
    session_dir.mkdir(parents=True)
    (session_dir / "parts").mkdir()
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    partial = session_dir / "master.transcript.partial.json"
    partial.write_text(json.dumps({"segments": [], "text": ""}), encoding="utf-8")
    old = partial.stat().st_mtime
    os.utime(partial, (old - 200, old - 200))

    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="room1",
        temp_path=str(master),
        ffmpeg_pid=9999,
        pipeline_mode="streaming",
    )
    conn.execute(
        "UPDATE live_sessions SET session_dir = ?, reconnect_attempts = 0 WHERE id = ?",
        (str(session_dir), sid),
    )
    conn.commit()

    sessions = LiveSessionRepo(conn)
    row = sessions.get(sid)
    creator = CreatorRepo(conn).get(cid)
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        processes={sid: MagicMock()},
        notify=MagicMock(),
    )
    core._streaming_transcript_anchor[sid] = session_dir / "anchor.flv"

    with (
        patch.object(core, "_reconnect_segment") as mock_segment,
        patch.object(core, "_reconnect_hls_ffmpeg_only") as mock_hls,
        patch.object(core, "_use_hls_recording", return_value=True),
    ):
        stream_ok = core._maybe_recover_stalled_stream(
            row, creator, ffmpeg_alive=True, stt_alive=True
        )
        assert stream_ok is True
        mock_segment.assert_called_once()
        core._maybe_recover_stalled_hls(
            row, creator, ffmpeg_alive=True, stt_alive=True
        )
        mock_hls.assert_not_called()
    conn.close()


def test_reconnect_cooldown_blocks_second_stall(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    core = LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=MagicMock(),
        platform="douyin",
        notify=MagicMock(),
    )
    sid = "session-cooldown"
    core._mark_reconnect_cooldown(sid)
    assert core._in_reconnect_cooldown(sid) is True
    core._stall_reconnect_cooldown_until[sid] = time.monotonic() - 1
    assert core._in_reconnect_cooldown(sid) is False
    conn.close()
