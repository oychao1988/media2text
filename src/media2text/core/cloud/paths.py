"""Cloud path helpers for Aliyun Drive uploads."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_INVALID_PATH_CHARS = re.compile(r'[/\\:*?"<>|]')


def sanitize_path_segment(name: str, *, max_len: int = 100) -> str:
    """Strip invalid path chars and trim; truncate if too long."""
    cleaned = _INVALID_PATH_CHARS.sub("", name).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len].rstrip()


def file_pre_hash(path: Path) -> str:
    """SHA1 of first 1 KiB (aligo pre_hash convention)."""
    with path.open("rb") as fh:
        head = fh.read(1024)
    return hashlib.sha1(head).hexdigest()
