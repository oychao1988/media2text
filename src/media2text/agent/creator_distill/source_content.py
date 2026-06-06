"""Resolve local summary/transcript for a distill evolve source_id."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceContent:
    source_id: str
    kind: str
    summary_path: str | None
    transcript_path: str | None
    text: str


def _read(path: Path | None, *, max_chars: int) -> str:
    if path is None or not path.is_file() or max_chars <= 0:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:max_chars]


def resolve_source_content(
    *,
    workspace: Path,
    sec_uid: str,
    source_id: str,
    conn,
    max_chars: int = 40_000,
) -> SourceContent | None:
    """Load summary (preferred) or transcript for a live session / aweme id."""
    summary_path: Path | None = None
    transcript_path: Path | None = None
    kind = "live"

    row = conn.execute(
        "SELECT id, local_path FROM live_sessions WHERE id = ?",
        (source_id,),
    ).fetchone()
    if row and row["local_path"]:
        media = Path(str(row["local_path"]))
        if not media.is_absolute():
            media = workspace / media
        summary_path = media.with_suffix(".summary.md")
        transcript_path = media.with_suffix(".transcript.md")
        if not transcript_path.is_file():
            tp = media.with_suffix(".transcript.json")
            transcript_path = tp if tp.is_file() else None

    manifest_path = workspace / "creators" / sec_uid / "agent-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        for item in manifest.get("live") or []:
            if str(item.get("id")) != source_id:
                continue
            kind = "live"
            if item.get("summary_path"):
                p = Path(str(item["summary_path"]))
                summary_path = p if p.is_absolute() else workspace / "creators" / sec_uid / p
            if item.get("transcript_path"):
                p = Path(str(item["transcript_path"]))
                transcript_path = p if p.is_absolute() else workspace / "creators" / sec_uid / p
            break
        for item in manifest.get("vod") or manifest.get("items") or []:
            if str(item.get("id")) != source_id:
                continue
            kind = "vod"
            if item.get("summary_path"):
                p = Path(str(item["summary_path"]))
                summary_path = p if p.is_absolute() else workspace / "creators" / sec_uid / p
            if item.get("transcript_path"):
                p = Path(str(item["transcript_path"]))
                transcript_path = p if p.is_absolute() else workspace / "creators" / sec_uid / p
            break

    text = _read(summary_path, max_chars=max_chars)
    used_kind = "summary"
    if not text.strip():
        text = _read(transcript_path, max_chars=max_chars)
        used_kind = "transcript"
    if not text.strip():
        return None

    return SourceContent(
        source_id=source_id,
        kind=kind if used_kind == "summary" else used_kind,
        summary_path=str(summary_path) if summary_path else None,
        transcript_path=str(transcript_path) if transcript_path else None,
        text=text,
    )
