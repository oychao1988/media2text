from pathlib import Path
from unittest.mock import patch

import pytest

from media2text.core.live.playback_remux import (
    playback_mp4_is_fresh,
    remux_hls_to_playback_mp4,
)

pytestmark = pytest.mark.desktop


def test_playback_mp4_is_fresh_when_newer_than_master(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    master = session_dir / "master.m3u8"
    out = session_dir / "playback.mp4"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    out.write_bytes(b"mp4")
    import os
    import time

    time.sleep(0.01)
    os.utime(master, (master.stat().st_atime, master.stat().st_mtime - 10))
    assert playback_mp4_is_fresh(session_dir) is True


def test_remux_hls_to_playback_mp4_invokes_ffmpeg(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    master = session_dir / "master.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"fake-mp4")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    with patch("media2text.core.live.playback_remux.subprocess.run", fake_run):
        path = remux_hls_to_playback_mp4(session_dir, ffmpeg="ffmpeg")
    assert path == session_dir / "playback.mp4"
    assert path.read_bytes() == b"fake-mp4"
