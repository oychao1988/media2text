"""Read live session transcripts and summaries from workspace sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from media2text.core.live.transcript_writer import transcript_sidecar_media_paths
from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.models import LiveSessionRow


def _media_path_for_session(row: LiveSessionRow) -> Path | None:
    raw = row.local_path or row.temp_path
    if not raw:
        return None
    return Path(raw)


def _parse_segment_paths(row: LiveSessionRow) -> list[str]:
    if not row.segment_paths_json:
        return []
    try:
        data = json.loads(row.segment_paths_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(p) for p in data if p]


def transcript_media_candidates(row: LiveSessionRow) -> list[Path]:
    """FLV paths that may host transcript sidecars (anchor first, then current)."""
    seen: set[str] = set()
    out: list[Path] = []

    def add(path: Path) -> None:
        for candidate in transcript_sidecar_media_paths(path):
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)

    for raw in _parse_segment_paths(row):
        add(Path(raw))
    for raw in (row.temp_path, row.local_path):
        if not raw:
            continue
        add(Path(raw))
    return out


def _partial_sidecar_score(path: Path) -> tuple[float, int, float]:
    """Rank partial sidecars: higher segment end, then count, then mtime."""
    seg_end = 0.0
    seg_count = 0
    payload = _read_json_sidecar(path)
    if payload:
        segments = payload.get("segments") or []
        if isinstance(segments, list):
            seg_count = len(segments)
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                try:
                    seg_end = max(seg_end, float(seg.get("end") or 0))
                except (TypeError, ValueError):
                    continue
    return (seg_end, seg_count, path.stat().st_mtime)


def _pick_best_transcript_media(row: LiveSessionRow) -> Path | None:
    """Choose the media path whose transcript sidecar is most up to date."""
    best_score: tuple[float, int, float] | None = None
    best_media: Path | None = None

    for media in transcript_media_candidates(row):
        for candidate in transcript_sidecar_media_paths(media):
            partial = candidate.with_suffix(".transcript.partial.json")
            if not partial.is_file():
                continue
            score = _partial_sidecar_score(partial)
            if best_score is None or score > best_score:
                best_score = score
                best_media = candidate

    if best_media is not None:
        return best_media

    for media in transcript_media_candidates(row):
        for candidate in transcript_sidecar_media_paths(media):
            for suffix in (".transcript.json", ".transcript.md"):
                if candidate.with_suffix(suffix).is_file():
                    return candidate
    return None


def resolve_transcript_media(row: LiveSessionRow) -> Path | None:
    """Media path for the freshest partial (or final/md) transcript sidecar."""
    return _pick_best_transcript_media(row)


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


def read_transcript_for_session(row: LiveSessionRow) -> dict[str, Any]:
    """Load transcript for a session; picks the freshest sidecar across anchors."""
    media = resolve_transcript_media(row)
    if media is None:
        raise HTTPException(status_code=404, detail="transcript not found")
    return read_transcript_payload(media)


def transcript_mtime(row: LiveSessionRow) -> float | None:
    media = resolve_transcript_media(row)
    if media is None:
        return None
    mtimes: list[float] = []
    partial = media.with_suffix(".transcript.partial.json")
    if partial.is_file():
        mtimes.append(partial.stat().st_mtime)
    final = media.with_suffix(".transcript.json")
    if final.is_file():
        mtimes.append(final.stat().st_mtime)
    return max(mtimes) if mtimes else None


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
    transcript_media = resolve_transcript_media(row)
    if media is None and transcript_media is None:
        return {
            "media_path": None,
            "transcript_path": None,
            "summary_path": None,
            "partial_transcript_path": None,
        }
    media_s = str(media) if media is not None else str(transcript_media)
    transcript_s = str(transcript_media) if transcript_media is not None else media_s
    partial_path: Path | None = None
    if transcript_media is not None:
        candidate_partial = transcript_media.with_suffix(".transcript.partial.json")
        if candidate_partial.is_file():
            partial_path = candidate_partial
    return {
        "media_path": media_s,
        "transcript_path": _transcript_sidecar_path(transcript_s),
        "summary_path": _summary_sidecar_path(transcript_s),
        "partial_transcript_path": str(partial_path) if partial_path else None,
    }


def is_session_finalized(row: LiveSessionRow) -> bool:
    return row.status in ("completed", "failed")


# Private WebSocket close code: session no longer accepts live transcript stream.
WS_CLOSE_SESSION_FINALIZED = 4410


def transcript_session_meta(row: LiveSessionRow) -> dict[str, Any]:
    return {
        "session_status": row.status,
        "session_finalized": is_session_finalized(row),
    }
