"""Creator session list: merge DB rows with agent-manifest.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.core.manifest import _summary_sidecar_path, _transcript_sidecar_path
from media2text.core.storage.repos import AwemeRepo, CloudUploadRepo, CreatorRepo


@dataclass(frozen=True)
class _CloudUploadIndex:
    by_session: dict[str, Any]
    by_local_path: dict[str, Any]


def _build_cloud_index(conn, *, creator_id: str, workspace: Path) -> _CloudUploadIndex:
    from media2text.core.storage.cloud_path import normalize_workspace_rel

    rows = conn.execute(
        """
        SELECT * FROM cloud_uploads
        WHERE creator_id = ?
          AND upload_status = 'done'
          AND cloud_file_id IS NOT NULL
        ORDER BY uploaded_at DESC
        """,
        (creator_id,),
    ).fetchall()
    by_session: dict[str, Any] = {}
    by_local_path: dict[str, Any] = {}
    for row in rows:
        upload = dict(row)
        sid = upload.get("session_id")
        if sid:
            existing = by_session.get(sid)
            if existing is None:
                by_session[sid] = upload
            elif upload.get("file_kind") in ("mp4", "flv") and existing.get("file_kind") not in (
                "mp4",
                "flv",
            ):
                by_session[sid] = upload
        rel = normalize_workspace_rel(workspace, upload.get("local_path"))
        if rel and rel not in by_local_path:
            by_local_path[rel] = upload
    return _CloudUploadIndex(by_session=by_session, by_local_path=by_local_path)


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


def _primary_cloud_upload(conn, session_id: str, *, cloud_index: _CloudUploadIndex | None = None):
    if cloud_index is not None:
        return cloud_index.by_session.get(session_id)
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


def _empty_cloud_fields() -> dict[str, Any]:
    return {
        "cloud_upload_status": None,
        "cloud_file_id": None,
        "cloud_relative_path": None,
        "cloud_available": False,
    }


def _session_cloud_key(kind: str, item_id: str) -> str:
    return f"{kind}:{item_id}"


def _cloud_upload_fields(upload) -> tuple[str | None, str | None, str | None]:
    if isinstance(upload, dict):
        return (
            upload.get("upload_status"),
            upload.get("cloud_file_id"),
            upload.get("cloud_relative_path"),
        )
    return upload.upload_status, upload.cloud_file_id, upload.cloud_relative_path


def _merge_cloud_fields(
    conn,
    item_id: str,
    data: dict[str, Any],
    m_entry: dict | None,
    *,
    cloud_index: _CloudUploadIndex | None = None,
) -> dict[str, Any]:
    status = data.get("cloud_upload_status")
    file_id = data.get("cloud_file_id")
    rel_path = data.get("cloud_relative_path")
    if m_entry:
        status = status or m_entry.get("cloud_upload_status")
        file_id = file_id or m_entry.get("cloud_file_id")
        rel_path = rel_path or m_entry.get("cloud_relative_path")
    upload = _primary_cloud_upload(conn, item_id, cloud_index=cloud_index)
    if upload:
        upload_status, upload_file_id, upload_rel = _cloud_upload_fields(upload)
        if upload_status == "done" and not status:
            status = "done"
        file_id = file_id or upload_file_id
        rel_path = rel_path or upload_rel
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


def _lite_has_transcript(
    m_entry: dict | None,
    *,
    row_transcript_path: str | None = None,
    transcribe_status: str | None = None,
) -> bool:
    if m_entry and m_entry.get("transcript_path"):
        return True
    if row_transcript_path:
        return True
    if transcribe_status in ("done", "completed"):
        return True
    return False


def _lite_has_summary(m_entry: dict | None) -> bool:
    return bool(m_entry and m_entry.get("summary_path"))


def _lite_sidecar_rel(workspace: Path, raw: str | None) -> str | None:
    return workspace_rel(workspace, raw)


def _build_live_item(
    *,
    conn,
    ws: Path,
    creator_id: str,
    data: dict[str, Any],
    m_entry: dict | None,
    cloud_index: _CloudUploadIndex | None = None,
    lite: bool = False,
    include_cloud: bool = True,
) -> dict[str, Any]:
    sid = data["id"]
    media_path = data.get("local_path") or data.get("temp_path")
    if m_entry and m_entry.get("media_path"):
        media_path = m_entry.get("media_path") or media_path

    ht = (
        _lite_has_transcript(
            m_entry,
            transcribe_status=data.get("transcribe_status"),
        )
        if lite
        else _has_transcript(ws, media_path, m_entry)
    )
    hs = _lite_has_summary(m_entry) if lite else _has_summary(ws, media_path, m_entry)
    cloud = (
        _merge_cloud_fields(conn, sid, data, m_entry, cloud_index=cloud_index)
        if include_cloud
        else _empty_cloud_fields()
    )
    if lite:
        hls_fields = {"media_format": None, "discontinuity_at": [], "part_durations": []}
        resolved_media_path = media_path
    else:
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
        "media_available": False
        if lite
        else (
            _media_available(ws, resolved_media_path)
            or _media_available(ws, data.get("local_path"))
            or _media_available(ws, data.get("temp_path"))
        ),
        "pipeline_mode": data.get("pipeline_mode"),
        "transcribe_status": data.get("transcribe_status"),
        **cloud,
        **hls_fields,
        "has_transcript": ht,
        "has_summary": hs,
        "transcript_path": (
            _lite_sidecar_rel(ws, str(m_entry["transcript_path"]))
            if lite and m_entry and m_entry.get("transcript_path")
            else _resolve_transcript_path(ws, media_path, m_entry)
        ),
        "summary_path": (
            _lite_sidecar_rel(ws, str(m_entry["summary_path"]))
            if lite and m_entry and m_entry.get("summary_path")
            else _resolve_summary_path(ws, media_path, m_entry)
        ),
        "display_label": _format_live_display_label(data.get("started_at")),
    }


def _merge_vod_cloud_fields(
    conn,
    ws: Path,
    media_path: str | None,
    *,
    status: str | None,
    file_id: str | None,
    rel_path: str | None,
    cloud_index: _CloudUploadIndex | None = None,
) -> dict[str, Any]:
    upload = None
    if cloud_index is not None:
        from media2text.core.storage.cloud_path import normalize_workspace_rel

        rel = normalize_workspace_rel(ws, media_path)
        if rel:
            upload = cloud_index.by_local_path.get(rel)
    if upload is None:
        upload = CloudUploadRepo(conn).find_done_by_local_path(ws, media_path)
    if upload:
        upload_status, upload_file_id, upload_rel = _cloud_upload_fields(upload)
        if upload_status == "done" and not status:
            status = "done"
        file_id = file_id or upload_file_id
        rel_path = rel_path or upload_rel
    return {
        "cloud_upload_status": status,
        "cloud_file_id": file_id,
        "cloud_relative_path": rel_path,
        "cloud_available": _cloud_available(status, file_id, rel_path),
    }


def _build_vod_item(
    *,
    conn,
    ws: Path,
    creator_id: str,
    row,
    m_entry: dict | None,
    cloud_index: _CloudUploadIndex | None = None,
    lite: bool = False,
    include_cloud: bool = True,
) -> dict[str, Any]:
    aweme_id = row.aweme_id
    media_path = row.local_path
    if m_entry and m_entry.get("media_path"):
        media_path = m_entry.get("media_path") or media_path
    ht = (
        _lite_has_transcript(
            m_entry,
            row_transcript_path=row.transcript_path,
            transcribe_status=row.transcribe_status,
        )
        if lite
        else _has_transcript(ws, media_path, m_entry)
    )
    hs = _lite_has_summary(m_entry) if lite else _has_summary(ws, media_path, m_entry)
    started_at = _vod_started_at(row.create_time)
    if include_cloud:
        manifest_cloud = {
            "cloud_upload_status": m_entry.get("cloud_upload_status") if m_entry else None,
            "cloud_file_id": m_entry.get("cloud_file_id") if m_entry else None,
            "cloud_relative_path": m_entry.get("cloud_relative_path") if m_entry else None,
        }
        merged = _merge_vod_cloud_fields(
            conn,
            ws,
            media_path,
            status=manifest_cloud["cloud_upload_status"],
            file_id=manifest_cloud["cloud_file_id"],
            rel_path=manifest_cloud["cloud_relative_path"],
            cloud_index=cloud_index,
        )
        cloud_status = merged["cloud_upload_status"]
        cloud_file_id = merged["cloud_file_id"]
        cloud_rel = merged["cloud_relative_path"]
        cloud_available = merged["cloud_available"]
    else:
        cloud_status = None
        cloud_file_id = None
        cloud_rel = None
        cloud_available = False

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
        "media_available": False if lite else _media_available(ws, media_path),
        "pipeline_mode": None,
        "transcribe_status": row.transcribe_status,
        "cloud_upload_status": cloud_status,
        "cloud_file_id": cloud_file_id,
        "cloud_relative_path": cloud_rel,
        "cloud_available": cloud_available,
        "has_transcript": ht,
        "has_summary": hs,
        "transcript_path": (
            _lite_sidecar_rel(ws, str(m_entry["transcript_path"]))
            if lite and m_entry and m_entry.get("transcript_path")
            else _resolve_transcript_path(
                ws,
                media_path,
                m_entry,
                row_transcript_path=row.transcript_path,
            )
        ),
        "summary_path": (
            _lite_sidecar_rel(ws, str(m_entry["summary_path"]))
            if lite and m_entry and m_entry.get("summary_path")
            else _resolve_summary_path(ws, media_path, m_entry)
        ),
        "display_label": row.title or row.aweme_id,
    }


def _has_transcript(
    workspace: Path,
    media_path: str | None,
    manifest_entry: dict | None,
) -> bool:
    if manifest_entry and manifest_entry.get("transcript_path"):
        rel = _resolve_sidecar_rel(workspace, str(manifest_entry["transcript_path"]))
        if rel:
            return True
    if not media_path:
        return False
    return _transcript_sidecar_path(media_path, workspace=workspace) is not None


def _resolve_transcript_path(
    workspace: Path,
    media_path: str | None,
    manifest_entry: dict | None,
    *,
    row_transcript_path: str | None = None,
) -> str | None:
    if manifest_entry and manifest_entry.get("transcript_path"):
        rel = _resolve_sidecar_rel(workspace, str(manifest_entry["transcript_path"]))
        if rel:
            return rel
    if row_transcript_path:
        rel = _resolve_sidecar_rel(workspace, row_transcript_path)
        if rel:
            return rel
    return _transcript_sidecar_path(media_path, workspace=workspace)


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
        raw = _summary_sidecar_path(media_path, workspace=workspace)
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
        return {"media_format": None, "discontinuity_at": [], "part_durations": []}

    manifest = _load_session_manifest_json(master.parent)
    media_format = "hls"
    discontinuity_at: list[float] = []
    part_durations: list[float] = []
    if manifest:
        media_format = str(manifest.get("media_format") or "hls")
        raw_disc = manifest.get("discontinuity_at") or []
        if isinstance(raw_disc, list):
            discontinuity_at = [float(x) for x in raw_disc if isinstance(x, (int, float))]
        raw_parts = manifest.get("parts") or []
        if isinstance(raw_parts, list):
            for item in raw_parts:
                if isinstance(item, dict) and item.get("duration_sec") is not None:
                    part_durations.append(float(item["duration_sec"]))
    return {
        "media_format": media_format,
        "discontinuity_at": discontinuity_at,
        "part_durations": part_durations,
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


def _parse_session_keys(keys: set[str]) -> tuple[set[str], set[str]]:
    live_ids: set[str] = set()
    vod_ids: set[str] = set()
    for raw in keys:
        if raw.startswith("live:"):
            live_ids.add(raw[5:])
        elif raw.startswith("vod:"):
            vod_ids.add(raw[4:])
    return live_ids, vod_ids


def _count_creator_session_refs(conn, creator_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM (
            SELECT id FROM live_sessions WHERE creator_id = ?
            UNION ALL
            SELECT aweme_id FROM awemes
            WHERE creator_id = ?
              AND sync_status IN ('downloaded', 'failed', 'listed')
        )
        """,
        (creator_id, creator_id),
    ).fetchone()
    return int(dict(row)["c"]) if row else 0


def _page_creator_session_refs(
    conn,
    creator_id: str,
    *,
    limit: int,
    offset: int,
) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT kind, item_id FROM (
            SELECT 'live' AS kind, id AS item_id, COALESCE(started_at, '') AS sort_at
            FROM live_sessions
            WHERE creator_id = ?
            UNION ALL
            SELECT 'vod' AS kind, aweme_id AS item_id,
                   COALESCE(datetime(create_time, 'unixepoch'), '') AS sort_at
            FROM awemes
            WHERE creator_id = ?
              AND sync_status IN ('downloaded', 'failed', 'listed')
        )
        ORDER BY sort_at DESC
        LIMIT ? OFFSET ?
        """,
        (creator_id, creator_id, limit, offset),
    ).fetchall()
    return [(str(dict(r)["kind"]), str(dict(r)["item_id"])) for r in rows]


def _fetch_live_rows_by_ids(conn, ids: set[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM live_sessions WHERE id IN ({placeholders})",
        tuple(ids),
    ).fetchall()
    return {str(dict(r)["id"]): dict(r) for r in rows}


def _fetch_aweme_rows_by_ids(conn, ids: set[str]) -> dict[str, Any]:
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM awemes WHERE aweme_id IN ({placeholders})",
        tuple(ids),
    ).fetchall()
    from media2text.core.storage.repos import AwemeRow

    out: dict[str, Any] = {}
    for row in rows:
        aweme = AwemeRow(**dict(row))
        out[aweme.aweme_id] = aweme
    return out


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
    include_cloud: bool = True,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    use_fast = (
        not include_cloud
        and has_transcript is None
        and has_summary is None
        and status is None
    )
    if use_fast:
        return _list_creator_sessions_fast(
            conn,
            workspace=workspace,
            creator_id=creator_id,
            creator=creator,
            limit=limit,
            offset=offset,
        )

    manifest = _load_manifest(workspace, creator.sec_uid)
    manifest_live = _manifest_live_by_id(manifest)
    manifest_vod = _manifest_vod_by_id(manifest)
    ws = workspace
    cloud_index = _build_cloud_index(conn, creator_id=creator_id, workspace=ws) if include_cloud else None
    use_lite = has_transcript is None and has_summary is None

    rows = conn.execute(
        """
        SELECT * FROM live_sessions
        WHERE creator_id = ?
        ORDER BY started_at DESC
        """,
        (creator_id,),
    ).fetchall()

    sessions: list[tuple[dict[str, Any], dict[str, Any]]] = []
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
            cloud_index=cloud_index,
            lite=use_lite,
            include_cloud=include_cloud,
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
        sessions.append((item, {"kind": "live", "data": data, "m_entry": m_entry}))

    awemes = AwemeRepo(conn).list_for_creator(creator_id)
    for row in awemes:
        if row.sync_status not in ("downloaded", "failed", "listed"):
            continue
        m_entry = manifest_vod.get(row.aweme_id)
        item = _build_vod_item(
            conn=conn,
            ws=ws,
            creator_id=creator_id,
            row=row,
            m_entry=m_entry,
            cloud_index=cloud_index,
            lite=use_lite,
            include_cloud=include_cloud,
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
        if status and item.get("status") != status:
            continue
        sessions.append((item, {"kind": "vod", "row": row, "m_entry": m_entry}))

    sessions.sort(
        key=lambda pair: pair[0].get("started_at") or "",
        reverse=True,
    )

    total = len(sessions)
    page_pairs = sessions[offset : offset + limit]
    if use_lite and include_cloud:
        page: list[dict[str, Any]] = []
        for _lite_item, ctx in page_pairs:
            if ctx["kind"] == "live":
                page.append(
                    _build_live_item(
                        conn=conn,
                        ws=ws,
                        creator_id=creator_id,
                        data=ctx["data"],
                        m_entry=ctx["m_entry"],
                        cloud_index=cloud_index,
                        lite=False,
                        include_cloud=True,
                    )
                )
            else:
                page.append(
                    _build_vod_item(
                        conn=conn,
                        ws=ws,
                        creator_id=creator_id,
                        row=ctx["row"],
                        m_entry=ctx["m_entry"],
                        cloud_index=cloud_index,
                        lite=False,
                        include_cloud=True,
                    )
                )
    else:
        page = [pair[0] for pair in page_pairs]
    live_groups_raw = (manifest or {}).get("live_groups") or []
    live_groups: list[dict[str, Any]] = []
    for group in live_groups_raw:
        if not isinstance(group, dict):
            continue
        entry = dict(group)
        if include_cloud:
            rel = _resolve_sidecar_rel(ws, entry.get("summary_path"))
        else:
            rel = workspace_rel(ws, entry.get("summary_path"))
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


def _live_groups_from_manifest(
    ws: Path,
    manifest: dict[str, Any] | None,
    *,
    resolve_files: bool,
) -> list[dict[str, Any]]:
    live_groups_raw = (manifest or {}).get("live_groups") or []
    live_groups: list[dict[str, Any]] = []
    for group in live_groups_raw:
        if not isinstance(group, dict):
            continue
        entry = dict(group)
        if resolve_files:
            rel = _resolve_sidecar_rel(ws, entry.get("summary_path"))
        else:
            rel = workspace_rel(ws, entry.get("summary_path"))
        if rel:
            entry["summary_path"] = rel
        else:
            entry.pop("summary_path", None)
        live_groups.append(entry)
    return live_groups


def _list_creator_sessions_fast(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    creator,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    ws = workspace
    manifest = _load_manifest(ws, creator.sec_uid)
    manifest_live = _manifest_live_by_id(manifest)
    manifest_vod = _manifest_vod_by_id(manifest)

    total = _count_creator_session_refs(conn, creator_id)
    page_refs = _page_creator_session_refs(conn, creator_id, limit=limit, offset=offset)
    live_ids = {item_id for kind, item_id in page_refs if kind == "live"}
    vod_ids = {item_id for kind, item_id in page_refs if kind == "vod"}
    live_by_id = _fetch_live_rows_by_ids(conn, live_ids)
    vod_by_id = _fetch_aweme_rows_by_ids(conn, vod_ids)

    page: list[dict[str, Any]] = []
    for kind, item_id in page_refs:
        if kind == "live":
            data = live_by_id.get(item_id)
            if not data:
                continue
            page.append(
                _build_live_item(
                    conn=conn,
                    ws=ws,
                    creator_id=creator_id,
                    data=data,
                    m_entry=manifest_live.get(item_id),
                    cloud_index=None,
                    lite=True,
                    include_cloud=False,
                )
            )
        else:
            row = vod_by_id.get(item_id)
            if row is None:
                continue
            page.append(
                _build_vod_item(
                    conn=conn,
                    ws=ws,
                    creator_id=creator_id,
                    row=row,
                    m_entry=manifest_vod.get(item_id),
                    cloud_index=None,
                    lite=True,
                    include_cloud=False,
                )
            )

    return {
        "ok": True,
        "creator_id": creator_id,
        "sessions": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "live_groups": _live_groups_from_manifest(ws, manifest, resolve_files=False),
    }


def _session_enrich_fields(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "cloud_upload_status",
        "cloud_file_id",
        "cloud_relative_path",
        "cloud_available",
        "has_transcript",
        "has_summary",
        "media_available",
        "media_path",
        "media_format",
        "discontinuity_at",
        "part_durations",
        "transcript_path",
        "summary_path",
    )
    return {key: item.get(key) for key in keys}


def list_creator_session_cloud(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    keys: set[str] | None = None,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    manifest = _load_manifest(workspace, creator.sec_uid)
    manifest_live = _manifest_live_by_id(manifest)
    manifest_vod = _manifest_vod_by_id(manifest)
    ws = workspace
    cloud_index = _build_cloud_index(conn, creator_id=creator_id, workspace=ws)
    items: dict[str, dict[str, Any]] = {}

    live_ids: set[str] | None = None
    vod_ids: set[str] | None = None
    if keys is not None:
        live_ids, vod_ids = _parse_session_keys(keys)

    if keys is None or live_ids:
        query_ids = live_ids
        if query_ids is None:
            rows = conn.execute(
                "SELECT id FROM live_sessions WHERE creator_id = ?",
                (creator_id,),
            ).fetchall()
            query_ids = {str(dict(r)["id"]) for r in rows}
        for sid, data in _fetch_live_rows_by_ids(conn, query_ids).items():
            key = _session_cloud_key("live", sid)
            m_entry = manifest_live.get(sid)
            full = _build_live_item(
                conn=conn,
                ws=ws,
                creator_id=creator_id,
                data=data,
                m_entry=m_entry,
                cloud_index=cloud_index,
                lite=False,
                include_cloud=True,
            )
            items[key] = _session_enrich_fields(full)

    if keys is None or vod_ids:
        query_ids = vod_ids
        if query_ids is None:
            rows = conn.execute(
                """
                SELECT aweme_id FROM awemes
                WHERE creator_id = ?
                  AND sync_status IN ('downloaded', 'failed', 'listed')
                """,
                (creator_id,),
            ).fetchall()
            query_ids = {str(dict(r)["aweme_id"]) for r in rows}
        for aweme_id, row in _fetch_aweme_rows_by_ids(conn, query_ids).items():
            if row.sync_status not in ("downloaded", "failed", "listed"):
                continue
            key = _session_cloud_key("vod", aweme_id)
            m_entry = manifest_vod.get(aweme_id)
            full = _build_vod_item(
                conn=conn,
                ws=ws,
                creator_id=creator_id,
                row=row,
                m_entry=m_entry,
                cloud_index=cloud_index,
                lite=False,
                include_cloud=True,
            )
            items[key] = _session_enrich_fields(full)

    return {"ok": True, "creator_id": creator_id, "items": items}
