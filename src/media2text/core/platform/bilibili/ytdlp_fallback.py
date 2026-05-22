"""Best-effort Bilibili video download via yt-dlp when playurl resolve fails."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from media2text.core.platform.douyin.ytdlp_fallback import export_netscape_cookies


def ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


def download_via_ytdlp_bilibili(
    *,
    bvid: str,
    dest: Path,
    session_file: Path,
) -> None:
    if not ytdlp_available():
        raise RuntimeError("yt-dlp not installed")

    dest.parent.mkdir(parents=True, exist_ok=True)
    page_url = f"https://www.bilibili.com/video/{bvid}"

    with tempfile.TemporaryDirectory() as tmp:
        cookies_path = Path(tmp) / "cookies.txt"
        export_netscape_cookies(session_file, cookies_path)
        out_template = str(dest.parent / f"{bvid}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--cookies",
            str(cookies_path),
            "-f",
            "bv*+ba/b[ext=mp4]/b",
            "-o",
            out_template,
            page_url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
            raise RuntimeError(err[:500])

    if dest.is_file():
        return
    candidates = sorted(dest.parent.glob(f"{bvid}.*"))
    for path in candidates:
        if path.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            if path != dest:
                path.rename(dest)
            return
    raise RuntimeError("yt-dlp finished but output file not found")
