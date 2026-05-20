"""Best-effort video download via yt-dlp when primary resolve fails."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


def export_netscape_cookies(session_file: Path, dest: Path) -> None:
    data = json.loads(session_file.read_text())
    lines = ["# Netscape HTTP Cookie File", ""]
    for cookie in data.get("cookies", []):
        domain = str(cookie.get("domain") or "")
        if not domain:
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(cookie.get("path") or "/")
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expires = cookie.get("expires")
        expires_str = str(int(expires)) if expires not in (None, -1) else "0"
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if not name:
            continue
        lines.append(
            f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires_str}\t{name}\t{value}"
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def download_via_ytdlp(
    *,
    aweme_id: str,
    dest: Path,
    session_file: Path,
) -> None:
    if not ytdlp_available():
        raise RuntimeError("yt-dlp not installed")

    dest.parent.mkdir(parents=True, exist_ok=True)
    page_url = f"https://www.douyin.com/video/{aweme_id}"

    with tempfile.TemporaryDirectory() as tmp:
        cookies_path = Path(tmp) / "cookies.txt"
        export_netscape_cookies(session_file, cookies_path)
        out_template = str(dest.parent / f"{aweme_id}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--cookies",
            str(cookies_path),
            "-f",
            "best[ext=mp4]/best",
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
    candidates = sorted(dest.parent.glob(f"{aweme_id}.*"))
    for path in candidates:
        if path.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            if path != dest:
                path.rename(dest)
            return
    raise RuntimeError("yt-dlp finished but output file not found")
