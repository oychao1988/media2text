"""Read live session transcripts and summaries from workspace sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.models import LiveSessionRow


def _media_path_for_session(row: LiveSessionRow) -> Path | None:
    raw = row.local_path or row.temp_path
    if not raw:
        return None
    return Path(raw)


def _read_json_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_transcript_payload(media_path: Path) -> dict[str, Any]:
    """Load partial or final transcript; return API shape."""
    partial_path = media_path.with_suffix(".transcript.partial.json")
    final_json = media_path.with_suffix(".transcript.json")

    payload = _read_json_sidecar(partial_path)
    if payload is not None:
        segments = payload.get("segments") or []
        return {
            "partial": True,
            "segments": segments if isinstance(segments, list) else [],
            "text": str(payload.get("text") or ""),
            "engine": payload.get("engine"),
            "model": payload.get("model"),
        }

    payload = _read_json_sidecar(final_json)
    if payload is not None:
        segments = payload.get("segments") or []
        return {
            "partial": False,
            "segments": segments if isinstance(segments, list) else [],
            "text": str(payload.get("text") or ""),
            "engine": payload.get("engine"),
            "model": payload.get("model"),
        }

    md_path = media_path.with_suffix(".transcript.md")
    if md_path.is_file():
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        return {
            "partial": False,
            "segments": [],
            "text": text,
            "engine": None,
            "model": None,
        }

    raise HTTPException(status_code=404, detail="transcript not found")


def read_summary_text(media_path: Path) -> str:
    summary_path = _summary_sidecar_path(str(media_path))
    if not summary_path:
        raise HTTPException(status_code=404, detail="summary not found")
    path = Path(summary_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="summary not found")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="summary read failed") from exc


def session_sidecar_paths(row: LiveSessionRow) -> dict[str, str | None]:
    media = _media_path_for_session(row)
    if media is None:
        return {
            "media_path": None,
            "transcript_path": None,
            "summary_path": None,
            "partial_transcript_path": None,
        }
    media_s = str(media)
    partial = media.with_suffix(".transcript.partial.json")
    return {
        "media_path": media_s,
        "transcript_path": _transcript_sidecar_path(media_s),
        "summary_path": _summary_sidecar_path(media_s),
        "partial_transcript_path": str(partial) if partial.is_file() else None,
    }


def is_session_finalized(row: LiveSessionRow) -> bool:
    return row.status in ("completed", "failed")
