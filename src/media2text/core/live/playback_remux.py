"""Remux local HLS (fMP4) to a single MP4 for players that need one init (Safari)."""

from __future__ import annotations

import subprocess
from pathlib import Path

PLAYBACK_MP4_NAME = "playback.mp4"
PLAYBACK_MP4_TMP = "playback.mp4.tmp"


def playback_mp4_path(session_dir: Path) -> Path:
    return session_dir / PLAYBACK_MP4_NAME


def playback_mp4_is_fresh(session_dir: Path) -> bool:
    master = session_dir / "master.m3u8"
    out = playback_mp4_path(session_dir)
    if not master.is_file() or not out.is_file():
        return False
    return out.stat().st_mtime >= master.stat().st_mtime


def remux_hls_to_playback_mp4(
    session_dir: Path,
    *,
    ffmpeg: str,
) -> Path:
    """Build or refresh session_dir/playback.mp4 from master.m3u8."""
    master = session_dir / "master.m3u8"
    if not master.is_file():
        raise FileNotFoundError(f"playlist not found: {master}")

    out = playback_mp4_path(session_dir)
    if playback_mp4_is_fresh(session_dir):
        return out

    tmp = session_dir / PLAYBACK_MP4_TMP
    if tmp.is_file():
        tmp.unlink(missing_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(master),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(tmp),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"ffmpeg remux failed: {detail}")

    tmp.replace(out)
    return out
