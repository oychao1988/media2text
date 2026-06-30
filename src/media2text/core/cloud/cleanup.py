"""Rolling cleanup helpers for Aliyun Drive live backups."""

from __future__ import annotations

VIDEO_CLEANUP_FILE_KINDS: frozenset[str] = frozenset({"mp4", "flv", "m4s", "init_mp4"})


def is_video_cleanup_file_kind(file_kind: str) -> bool:
    return file_kind in VIDEO_CLEANUP_FILE_KINDS


def is_video_cleanup_filename(name: str) -> bool:
    lower = name.lower().strip()
    if not lower:
        return False
    if lower == "init.mp4":
        return True
    if lower.endswith((".mp4", ".flv", ".m4s")):
        return True
    return lower.startswith("seg-") and lower.endswith(".m4s")
