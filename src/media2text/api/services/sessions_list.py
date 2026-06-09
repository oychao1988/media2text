"""Creator session list: merge DB rows with agent-manifest.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.repos import AwemeRepo, CloudUploadRepo, CreatorRepo


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


def _manifest_vod_by_id(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not manifest:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key in ("items", "archives"):
        for item in manifest.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
    return out


def _primary_cloud_upload(conn, session_id: str):
    uploads = CloudUploadRepo(conn).list_for_session(session_id)
    for kind in ("mp4", "flv"):
        for row in uploads:
            if row.file_kind == kind and row.upload_status == "done" and row.cloud_file_id:
                return row
    return None


def _cloud_available(
    status: str | None,
    file_id: str | None,
    relative_path: str | None = None,
) -> bool:
    if status in ("done", "uploaded"):
        return bool(file_id or relative_path)
    return False


def _merge_cloud_fields(
    conn,
    item_id: str,
    data: dict[str, Any],
    m_entry: dict | None,
) -> dict[str, Any]:
    status = data.get("cloud_upload_status")
    file_id = data.get("cloud_file_id")
    rel_path = data.get("cloud_relative_path")
    if m_entry:
        status = status or m_entry.get("cloud_upload_status")
        file_id = file_id or m_entry.get("cloud_file_id")
        rel_path = rel_path or m_entry.get("cloud_relative_path")
    upload = _primary_cloud_upload(conn, item_id)
    if upload:
        if upload.upload_status == "done" and not status:
            status = "done"
        file_id = file_id or upload.cloud_file_id
        rel_path = rel_path or upload.cloud_relative_path
    return {
        "cloud_upload_status": status,
        "cloud_file_id": file_id,
        "cloud_relative_path": rel_path,
        "cloud_available": _cloud_available(status, file_id, rel_path),
    }


def _vod_started_at(create_time: int | None) -> str | None:
    if not create_time:
        return None
    return datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()


def _format_live_display_label(started_at: str | None) -> str:
    if not started_at:
        return "直播"
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        local = dt.astimezone()
        return f"{local.strftime('%Y-%m-%d %H:%M')} 直播"
    except ValueError:
        return "直播"


def _build_live_item(
    *,
    conn,
    ws: Path,
    creator_id: str,
    data: dict[str, Any],
    m_entry: dict | None,
) -> dict[str, Any]:
    sid = data["id"]
    media_path = data.get("local_path") or data.get("temp_path")
    if m_entry and m_entry.get("media_path"):
        media_path = m_entry.get("media_path") or media_path

    ht = _has_transcript(media_path, m_entry)
    hs = _has_summary(ws, media_path, m_entry)
    cloud = _merge_cloud_fields(conn, sid, data, m_entry)
    hls_fields = _hls_playback_fields(ws, media_path, data)
    resolved_media_path = hls_fields.pop("media_path", None) or media_path

    return {
        "kind": "live",
        "item_id": sid,
        "session_id": sid,
        "aweme_id": None,
        "title": None,
        "creator_id": creator_id,
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
        "status": data.get("status"),
        "local_path": workspace_rel(ws, data.get("local_path")),
        "temp_path": workspace_rel(ws, data.get("temp_path")),
        "media_path": workspace_rel(ws, resolved_media_path),
        "media_available": _media_available(ws, resolved_media_path)
        or _media_available(ws, data.get("local_path"))
        or _media_available(ws, data.get("temp_path")),
        "pipeline_mode": data.get("pipeline_mode"),
        "transcribe_status": data.get("transcribe_status"),
        **cloud,
        **hls_fields,
        "has_transcript": ht,
        "has_summary": hs,
        "transcript_path": _resolve_sidecar_rel(
            ws,
            m_entry.get("transcript_path") if m_entry else _transcript_sidecar_path(media_path),
        ),
        "summary_path": _resolve_summary_path(ws, media_path, m_entry),
        "display_label": _format_live_display_label(data.get("started_at")),
    }


def _build_vod_item(
    *,
    ws: Path,
    creator_id: str,
    row,
    m_entry: dict | None,
) -> dict[str, Any]:
    aweme_id = row.aweme_id
    media_path = row.local_path
    if m_entry and m_entry.get("media_path"):
        media_path = m_entry.get("media_path") or media_path
    ht = _has_transcript(media_path, m_entry)
    hs = _has_summary(ws, media_path, m_entry)
    started_at = _vod_started_at(row.create_time)
    manifest_cloud = {
        "cloud_upload_status": m_entry.get("cloud_upload_status") if m_entry else None,
        "cloud_file_id": m_entry.get("cloud_file_id") if m_entry else None,
        "cloud_relative_path": m_entry.get("cloud_relative_path") if m_entry else None,
    }
    cloud_status = manifest_cloud["cloud_upload_status"]
    cloud_file_id = manifest_cloud["cloud_file_id"]
    cloud_rel = manifest_cloud["cloud_relative_path"]

    return {
        "kind": "vod",
        "item_id": aweme_id,
        "session_id": aweme_id,
        "aweme_id": aweme_id,
        "title": row.title,
        "creator_id": creator_id,
        "started_at": started_at,
        "ended_at": None,
        "status": row.sync_status,
        "media_type": row.media_type or "video",
        "local_path": workspace_rel(ws, row.local_path),
        "temp_path": None,
        "media_path": workspace_rel(ws, media_path),
        "media_available": _media_available(ws, media_path),
        "pipeline_mode": None,
        "transcribe_status": row.transcribe_status,
        "cloud_upload_status": cloud_status,
        "cloud_file_id": cloud_file_id,
        "cloud_relative_path": cloud_rel,
        "cloud_available": _cloud_available(cloud_status, cloud_file_id, cloud_rel),
        "has_transcript": ht,
        "has_summary": hs,
        "transcript_path": _resolve_sidecar_rel(
            ws,
            m_entry.get("transcript_path") if m_entry else row.transcript_path or _transcript_sidecar_path(media_path),
        ),
        "summary_path": _resolve_summary_path(ws, media_path, m_entry),
        "display_label": row.title or row.aweme_id,
    }


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


_GALLERY_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _hls_master_path(target: Path) -> Path | None:
    if target.is_file() and target.name == "master.m3u8":
        return target
    if target.is_dir():
        master = target / "master.m3u8"
        if master.is_file():
            return master
    return None


def _path_has_local_media(target: Path) -> bool:
    if target.is_file():
        return True
    if target.is_dir():
        if _hls_master_path(target) is not None:
            return True
        return any(
            child.is_file() and child.suffix.lower() in _GALLERY_SUFFIXES
            for child in target.iterdir()
        )
    return False


def _load_session_manifest_json(session_dir: Path) -> dict[str, Any] | None:
    manifest_path = session_dir / "session.manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _hls_playback_fields(ws: Path, media_path: str | None, row_data: dict[str, Any]) -> dict[str, Any]:
    session_dir_raw = row_data.get("session_dir") or row_data.get("local_path")
    master: Path | None = None
    if session_dir_raw:
        try:
            target = Path(session_dir_raw)
            if not target.is_absolute():
                rel = workspace_rel(ws, session_dir_raw)
                if rel:
                    target = safe_workspace_path(ws, rel)
            master = _hls_master_path(target)
        except HTTPException:
            master = None
    if master is None and media_path:
        try:
            rel = workspace_rel(ws, media_path)
            if rel:
                master = _hls_master_path(safe_workspace_path(ws, rel))
        except HTTPException:
            master = None
    if master is None:
        return {"media_format": None, "discontinuity_at": []}

    manifest = _load_session_manifest_json(master.parent)
    discontinuity_at: list[float] = []
    media_format = "hls"
    if manifest:
        media_format = str(manifest.get("media_format") or "hls")
        raw_disc = manifest.get("discontinuity_at") or []
        if isinstance(raw_disc, list):
            discontinuity_at = [float(x) for x in raw_disc if isinstance(x, (int, float))]
    return {
        "media_format": media_format,
        "discontinuity_at": discontinuity_at,
        "media_path": workspace_rel(ws, str(master)) or media_path,
    }


def _media_available(workspace: Path, media_path: str | None) -> bool:
    if not media_path:
        return False
    # 尝试 workspace 相对路径
    rel = workspace_rel(workspace, media_path)
    if rel:
        try:
            target = safe_workspace_path(workspace, rel)
            if _path_has_local_media(target):
                return True
        except HTTPException:
            pass
    # 绝对路径且文件/图集目录真实存在（不在 workspace 下也能播放）
    abs_target = Path(media_path)
    if abs_target.is_absolute() and _path_has_local_media(abs_target):
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
    manifest_vod = _manifest_vod_by_id(manifest)
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
        item = _build_live_item(
            conn=conn,
            ws=ws,
            creator_id=creator_id,
            data=data,
            m_entry=m_entry,
        )
        ht = item["has_transcript"]
        hs = item["has_summary"]
        if has_transcript is True and not ht:
            continue
        if has_transcript is False and ht:
            continue
        if has_summary is True and not hs:
            continue
        if has_summary is False and hs:
            continue
        st = item.get("status")
        if status and st != status:
            continue
        sessions.append(item)

    awemes = AwemeRepo(conn).list_for_creator(creator_id)
    for row in awemes:
        if row.sync_status not in ("downloaded", "failed", "listed"):
            continue
        m_entry = manifest_vod.get(row.aweme_id)
        item = _build_vod_item(ws=ws, creator_id=creator_id, row=row, m_entry=m_entry)
        ht = item["has_transcript"]
        hs = item["has_summary"]
        if has_transcript is True and not ht:
            continue
        if has_transcript is False and ht:
            continue
        if has_summary is True and not hs:
            continue
        if has_summary is False and hs:
            continue
        if status and item.get("status") != status:
            continue
        sessions.append(item)

    sessions.sort(
        key=lambda s: s.get("started_at") or "",
        reverse=True,
    )

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
