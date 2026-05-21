from __future__ import annotations

from pathlib import Path

from media2text.core.notify.content import media_mp4_path


def find_latest_transcript_with_media(workspace: Path) -> tuple[Path | None, Path | None]:
    """Return (transcript.md, mp4) for the newest live item that has both files."""
    best: tuple[Path, Path] | None = None
    best_mtime = 0.0
    for md in workspace.glob("creators/*/live/*.transcript.md"):
        mp4 = media_mp4_path(md)
        if not mp4.is_file():
            continue
        mtime = max(md.stat().st_mtime, mp4.stat().st_mtime)
        if mtime > best_mtime:
            best_mtime = mtime
            best = (md, mp4)
    if best is None:
        return None, None
    return best
