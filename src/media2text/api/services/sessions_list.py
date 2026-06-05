"""Creator session list: merge DB rows with agent-manifest.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.repos import CreatorRepo


def _load_manifest(workspace: Path, sec_uid: str) -> dict[str, Any] | None:
    path = workspace / "creators" / sec_uid / "agent-manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _manifest_live_by_id(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not manifest:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in manifest.get("live") or []:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def _has_transcript(media_path: str | None, manifest_entry: dict | None) -> bool:
    if manifest_entry and manifest_entry.get("transcript_path"):
        return True
    if not media_path:
        return False
    base = Path(media_path)
    for name in (
        f"{base.stem}.transcript.json",
        f"{base.stem}.transcript.partial.json",
        f"{base.stem}.transcript.md",
    ):
        if (base.parent / name).is_file():
            return True
    return _transcript_sidecar_path(media_path) is not None


def _resolve_sidecar_rel(
    workspace: Path,
    raw: str | None,
) -> str | None:
    rel = workspace_rel(workspace, raw)
    if not rel:
        return None
    try:
        target = safe_workspace_path(workspace, rel)
    except HTTPException:
        return None
    return rel if target.is_file() else None


def _resolve_summary_path(
    workspace: Path,
    media_path: str | None,
    manifest_entry: dict | None,
) -> str | None:
    raw: str | None = None
    if manifest_entry and manifest_entry.get("summary_path"):
        raw = str(manifest_entry["summary_path"])
    else:
        raw = _summary_sidecar_path(media_path)
    return _resolve_sidecar_rel(workspace, raw)


def _has_summary(
    workspace: Path,
    media_path: str | None,
    manifest_entry: dict | None,
) -> bool:
    return _resolve_summary_path(workspace, media_path, manifest_entry) is not None


def _media_available(workspace: Path, media_path: str | None) -> bool:
    if not media_path:
        return False
    # 尝试 workspace 相对路径
    rel = workspace_rel(workspace, media_path)
    if rel:
        try:
            target = safe_workspace_path(workspace, rel)
            if target.is_file():
                return True
        except HTTPException:
            pass
    # 绝对路径且文件真实存在（不在 workspace 下也能播放）
    if Path(media_path).is_absolute() and Path(media_path).is_file():
        return True
    return False


def list_creator_sessions(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    limit: int = 50,
    offset: int = 0,
    has_transcript: bool | None = None,
    has_summary: bool | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    manifest = _load_manifest(workspace, creator.sec_uid)
    manifest_live = _manifest_live_by_id(manifest)
    ws = workspace

    rows = conn.execute(
        """
        SELECT * FROM live_sessions
        WHERE creator_id = ?
        ORDER BY started_at DESC
        """,
        (creator_id,),
    ).fetchall()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        sid = data["id"]
        m_entry = manifest_live.get(sid)
        media_path = data.get("local_path") or data.get("temp_path")
        if m_entry and m_entry.get("media_path"):
            media_path = m_entry.get("media_path") or media_path

        ht = _has_transcript(media_path, m_entry)
        hs = _has_summary(ws, media_path, m_entry)
        if has_transcript is True and not ht:
            continue
        if has_transcript is False and ht:
            continue
        if has_summary is True and not hs:
            continue
        if has_summary is False and hs:
            continue
        st = data.get("status")
        if status and st != status:
            continue

        item: dict[str, Any] = {
            "session_id": sid,
            "creator_id": creator_id,
            "started_at": data.get("started_at"),
            "ended_at": data.get("ended_at"),
            "status": st,
            "local_path": workspace_rel(ws, data.get("local_path")),
            "temp_path": workspace_rel(ws, data.get("temp_path")),
            "media_path": workspace_rel(ws, media_path),
            "media_available": _media_available(ws, media_path),
            "pipeline_mode": data.get("pipeline_mode"),
            "transcribe_status": data.get("transcribe_status"),
            "cloud_upload_status": data.get("cloud_upload_status"),
            "has_transcript": ht,
            "has_summary": hs,
            "transcript_path": _resolve_sidecar_rel(
                ws,
                m_entry.get("transcript_path") if m_entry else _transcript_sidecar_path(media_path),
            ),
            "summary_path": _resolve_summary_path(ws, media_path, m_entry),
        }
        sessions.append(item)

    total = len(sessions)
    page = sessions[offset : offset + limit]
    live_groups_raw = (manifest or {}).get("live_groups") or []
    live_groups: list[dict[str, Any]] = []
    for group in live_groups_raw:
        if not isinstance(group, dict):
            continue
        entry = dict(group)
        rel = _resolve_sidecar_rel(ws, entry.get("summary_path"))
        if rel:
            entry["summary_path"] = rel
        else:
            entry.pop("summary_path", None)
        live_groups.append(entry)

    return {
        "ok": True,
        "creator_id": creator_id,
        "sessions": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "live_groups": live_groups,
    }
