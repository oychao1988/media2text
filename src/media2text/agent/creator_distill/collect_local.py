"""Local glob scan for creator distill bootstrap (CD3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from media2text.core.config import LocalScanConfig


@dataclass(frozen=True)
class LocalFileHit:
    rel_path: str
    kind: str
    chars: int
    text: str


def _kind_for_path(path: Path) -> str:
    name = path.name.lower()
    if "summary" in name:
        return "summary"
    if "transcript" in name:
        return "transcript"
    if name == "content.md":
        return "dynamic"
    return "source"


def scan_local_files(
    *,
    workspace: Path,
    sec_uid: str,
    local_scan: LocalScanConfig,
    budget: int,
) -> list[LocalFileHit]:
    if not local_scan.enabled or budget <= 0:
        return []
    root = workspace / "creators" / sec_uid
    if not root.is_dir():
        return []
    seen: set[str] = set()
    hits: list[LocalFileHit] = []
    for pattern in local_scan.globs:
        for path in sorted(root.glob(pattern)):
            if len(hits) >= local_scan.max_files or budget <= 0:
                break
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            if len(text) > budget:
                text = text[:budget]
            rel = (
                str(path.relative_to(workspace))
                if path.is_relative_to(workspace)
                else str(path)
            )
            hits.append(
                LocalFileHit(
                    rel_path=rel,
                    kind=_kind_for_path(path),
                    chars=len(text),
                    text=text,
                )
            )
            budget -= len(text)
    return hits
