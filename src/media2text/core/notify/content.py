from __future__ import annotations

import re
from pathlib import Path

_TIMESTAMP_PREFIX = re.compile(r"^-\s*\[[^\]]+\]\s*")


def extract_transcript_summary(path: Path, *, max_chars: int = 500) -> str:
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    parts: list[str] = []
    total = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = _TIMESTAMP_PREFIX.sub("", line)
        if not line:
            continue
        parts.append(line)
        total += len(line)
        if total >= max_chars:
            break
    summary = "\n".join(parts)
    if len(summary) > max_chars:
        return summary[: max_chars - 1] + "…"
    return summary


def media_mp4_path(path: Path) -> Path:
    """Sibling `.mp4` for `*.transcript.md`; otherwise `.mp4` via stem swap."""
    name = path.name
    if name.endswith(".transcript.md"):
        return path.parent / f"{name[: -len('.transcript.md')]}.mp4"
    return path.with_suffix(".mp4")


def format_transcript_for_push(path: Path) -> str:
    """Plain transcript text for Feishu text messages (strip markdown title line)."""
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") and not lines:
            continue
        if s.startswith("- "):
            s = _TIMESTAMP_PREFIX.sub("", s)
        lines.append(s)
    return "\n".join(lines).strip()


def chunk_text(text: str, *, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            break_at = text.rfind("\n", start, end)
            if break_at > start + max_chars // 4:
                end = break_at + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def build_media_link(*, base_url: str, workspace: Path, media_path: Path) -> str | None:
    base = base_url.strip().rstrip("/")
    if not base:
        return None
    try:
        rel = media_path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return None
    return f"{base}/{rel.as_posix()}"


def post_paragraphs(
    *,
    title_line: str,
    body: str,
    summary: str | None,
    paths: list[tuple[str, str | None]],
) -> list[list[dict]]:
    """Build Feishu post content paragraphs (zh_cn content array)."""
    paragraphs: list[list[dict]] = []
    head = f"[media2text] {title_line}\n{body}".strip()
    if head:
        paragraphs.append([{"tag": "text", "text": head}])
    if summary:
        paragraphs.append([{"tag": "text", "text": f"\n摘要：\n{summary}"}])
    for label, link in paths:
        if link and link.startswith(("http://", "https://")):
            paragraphs.append(
                [
                    {"tag": "text", "text": f"\n{label}："},
                    {"tag": "a", "text": "打开", "href": link},
                ]
            )
        elif link:
            paragraphs.append([{"tag": "text", "text": f"\n{label}：\n{link}"}])
    if not paragraphs:
        paragraphs.append([{"tag": "text", "text": title_line}])
    return paragraphs
