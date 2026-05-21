from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger()


def extract_video_thumbnail(
    *,
    ffmpeg: str,
    video_path: Path,
    output_path: Path | None = None,
    timeout_sec: float = 30.0,
) -> Path | None:
    if not video_path.is_file():
        return None
    out = output_path or video_path.with_suffix(".notify.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        "5",
        "-i",
        str(video_path),
        "-vf",
        "thumbnail,scale=640:-1",
        "-frames:v",
        "1",
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_sec, check=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("thumbnail_extract_failed", path=str(video_path), error=str(exc))
        return None
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        log.warning(
            "thumbnail_extract_empty",
            path=str(video_path),
            stderr=(proc.stderr or b"").decode(errors="replace")[-300:],
        )
        return None
    return out
