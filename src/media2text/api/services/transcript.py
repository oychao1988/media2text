"""Read live session transcripts and summaries from workspace sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from media2text.core.live.transcript_writer import (
    find_summary_sidecar,
    list_segment_checkpoints,
    live_transcript_sidecar_mtime,
    load_merged_live_transcript,
    transcript_sidecar_media_paths,
)
from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.models import LiveSessionRow

if TYPE_CHECKING:
    from media2text.core.config import AppConfig


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


def _live_transcript_score(media_path: Path) -> tuple[float, int, float] | None:
    """Rank live sidecars (checkpoints + partial): end time, count, mtime."""
    merged = load_merged_live_transcript(media_path)
    if merged is None:
        return None
    segments = merged.get("segments") or []
    if not isinstance(segments, list) or not segments:
        return None
    seg_end = 0.0
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        try:
            seg_end = max(seg_end, float(seg.get("end") or 0))
        except (TypeError, ValueError):
            continue
    mtime = live_transcript_sidecar_mtime(media_path)
    if mtime is None:
        return None
    return (seg_end, len(segments), mtime)


def _pick_best_transcript_media(row: LiveSessionRow) -> Path | None:
    """Choose the media path whose transcript sidecar is most up to date."""
    best_score: tuple[float, int, float] | None = None
    best_media: Path | None = None

    for media in transcript_media_candidates(row):
        for candidate in transcript_sidecar_media_paths(media):
            partial = candidate.with_suffix(".transcript.partial.json")
            checkpoints = list_segment_checkpoints(candidate)
            if not partial.is_file() and not checkpoints:
                continue
            score = _live_transcript_score(candidate)
            if score is None:
                continue
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
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_transcript_payload(media_path: Path) -> dict[str, Any]:
    """Load partial or final transcript; return API shape."""
    final_json = media_path.with_suffix(".transcript.json")

    live_payload = load_merged_live_transcript(media_path)
    if live_payload is not None:
        return live_payload

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


def _find_cloud_sidecar_upload(
    conn,
    session_id: str,
    *,
    file_kinds: tuple[str, ...],
    prefer_kind: str | None = None,
) -> str | None:
    rows = conn.execute(
        """
        SELECT cloud_file_id, file_kind FROM cloud_uploads
        WHERE session_id = ? AND upload_status = 'done'
          AND file_kind IN ({})
        ORDER BY uploaded_at DESC
        """.format(",".join("?" * len(file_kinds))),
        (session_id, *file_kinds),
    ).fetchall()
    if not rows:
        return None
    if prefer_kind:
        for file_id, kind in rows:
            if kind == prefer_kind:
                return str(file_id)
    return str(rows[0][0])


def _read_transcript_from_cloud(
    cfg: AppConfig,
    conn,
    session_id: str,
) -> dict[str, Any]:
    from media2text.core.cloud.aliyundrive import AliyunDriveClient

    if not cfg.aliyundrive.enabled:
        raise HTTPException(status_code=404, detail="transcript not found")
    cloud_file_id = _find_cloud_sidecar_upload(
        conn,
        session_id,
        file_kinds=("transcript_json", "transcript_md"),
        prefer_kind="transcript_json",
    )
    if not cloud_file_id:
        raise HTTPException(status_code=404, detail="transcript not found")
    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        raise HTTPException(status_code=404, detail="transcript not found")
    try:
        with AliyunDriveClient.open(token_path) as client:
            raw = client.download_bytes(cloud_file_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="transcript not found") from exc
    if raw.lstrip().startswith(b"#") or raw.lstrip().startswith(b"---"):
        text = raw.decode("utf-8", errors="replace")
        return {"partial": False, "segments": [], "text": text}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=404, detail="transcript not found") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=404, detail="transcript not found")
    segments = payload.get("segments") or []
    return {
        "partial": False,
        "segments": segments if isinstance(segments, list) else [],
        "text": str(payload.get("text") or ""),
        "engine": payload.get("engine"),
        "model": payload.get("model"),
    }


def read_transcript_for_session(
    row: LiveSessionRow,
    *,
    cfg: AppConfig | None = None,
    conn=None,
) -> dict[str, Any]:
    """Load transcript for a session; picks the freshest sidecar across anchors."""
    media = resolve_transcript_media(row)
    if media is not None:
        return read_transcript_payload(media)
    if cfg is not None and conn is not None:
        return _read_transcript_from_cloud(cfg, conn, row.id)
    raise HTTPException(status_code=404, detail="transcript not found")


def read_summary_for_session(
    row: LiveSessionRow,
    *,
    cfg: AppConfig | None = None,
    conn=None,
    workspace: Path | None = None,
) -> str:
    media = _media_path_for_session(row)
    if media is not None:
        return read_summary_text(media, workspace=workspace)
    if cfg is not None and conn is not None and cfg.aliyundrive.enabled:
        from media2text.core.cloud.aliyundrive import AliyunDriveClient

        cloud_file_id = _find_cloud_sidecar_upload(
            conn,
            row.id,
            file_kinds=("summary_md", "summary_json"),
            prefer_kind="summary_md",
        )
        if cloud_file_id:
            token_path = cfg.aliyundrive_token_path()
            if token_path.is_file():
                try:
                    with AliyunDriveClient.open(token_path) as client:
                        raw = client.download_bytes(cloud_file_id)
                    return raw.decode("utf-8")
                except Exception:  # noqa: BLE001
                    pass
    raise HTTPException(status_code=404, detail="summary not found")


def transcript_mtime(row: LiveSessionRow) -> float | None:
    media = resolve_transcript_media(row)
    if media is None:
        return None
    mtimes: list[float] = []
    live_mtime = live_transcript_sidecar_mtime(media)
    if live_mtime is not None:
        mtimes.append(live_mtime)
    final = media.with_suffix(".transcript.json")
    if final.is_file():
        mtimes.append(final.stat().st_mtime)
    return max(mtimes) if mtimes else None


def read_summary_text(media_path: Path, *, workspace: Path | None = None) -> str:
    summary_path = find_summary_sidecar(media_path, workspace=workspace)
    if summary_path is None:
        raise HTTPException(status_code=404, detail="summary not found")
    try:
        return summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="summary read failed") from exc


def session_sidecar_paths(row: LiveSessionRow, *, workspace: Path | None = None) -> dict[str, str | None]:
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
        "transcript_path": _transcript_sidecar_path(transcript_s, workspace=workspace),
        "summary_path": _summary_sidecar_path(transcript_s, workspace=workspace),
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
