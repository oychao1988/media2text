"""History list media actions: delete local, restore from cloud, delete record."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException
from starlette.responses import StreamingResponse

from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.api.services.cloud_byte_proxy import stream_cloud_file
from media2text.core.cloud.aliyundrive import AliyunDriveClient
from media2text.core.config import AppConfig
from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import (
    AwemeRepo,
    CloudUploadRepo,
    CreatorRepo,
    LiveSessionRepo,
    MonitorTaskRepo,
)
from media2text.core.live.transcript_writer import resolve_summarize_paths
from media2text.core.summarize.errors import SummarizeConfigError, SummarizeError
from media2text.core.summarize.factory import create_summarize_backend, summarize_engine_available
from media2text.core.summarize.reader import transcript_path_for_media
from media2text.core.summarize.runner import summarize_one

HistoryKind = Literal["live", "vod"]


def _cloud_ready(
    status: str | None,
    file_id: str | None,
    *,
    relative_path: str | None = None,
) -> bool:
    if status in ("done", "uploaded"):
        return bool(file_id or relative_path)
    return False


def _resolve_media_path(
    workspace: Path,
    *,
    local_path: str | None,
    temp_path: str | None,
    manifest_path: str | None = None,
) -> Path | None:
    for raw in (manifest_path, local_path, temp_path):
        if not raw:
            continue
        rel = workspace_rel(workspace, raw)
        if not rel:
            if Path(raw).is_absolute():
                p = Path(raw)
                if p.is_file():
                    return p
            continue
        try:
            target = safe_workspace_path(workspace, rel)
        except Exception:
            continue
        if target.is_file():
            return target
    for raw in (local_path, temp_path, manifest_path):
        if not raw:
            continue
        rel = workspace_rel(workspace, raw)
        if rel:
            try:
                return safe_workspace_path(workspace, rel)
            except Exception:
                pass
        if Path(raw).is_absolute():
            return Path(raw)
    return None


def _primary_cloud_upload(conn, session_id: str):
    uploads = CloudUploadRepo(conn).list_for_session(session_id)
    for kind in ("mp4", "flv"):
        for row in uploads:
            if row.file_kind == kind and row.upload_status == "done" and row.cloud_file_id:
                return row
    return None


def _load_agent_manifest(workspace: Path, sec_uid: str) -> dict[str, Any] | None:
    path = workspace / "creators" / sec_uid / "agent-manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _path_matches_workspace_rel(workspace: Path, raw: str | None, rel_path: str) -> bool:
    if not raw:
        return False
    rel = workspace_rel(workspace, raw)
    if rel == rel_path:
        return True
    return raw == rel_path or raw.endswith(f"/{rel_path}") or raw.endswith(rel_path)


def _cloud_file_from_manifest_entry(entry: dict[str, Any] | None) -> str | None:
    if not entry:
        return None
    status = entry.get("cloud_upload_status")
    file_id = entry.get("cloud_file_id")
    rel_path = entry.get("cloud_relative_path")
    if _cloud_ready(status, file_id, relative_path=rel_path):
        return str(file_id) if file_id else None
    return None


def resolve_cloud_file_for_media_path(
    cfg: AppConfig,
    conn,
    workspace_rel_path: str,
) -> str | None:
    """Resolve Aliyun cloud_file_id for a workspace-relative media path."""
    ws = cfg.ensure_workspace()
    for row in conn.execute(
        """
        SELECT cloud_file_id, local_path, upload_status
        FROM cloud_uploads
        WHERE upload_status = 'done' AND cloud_file_id IS NOT NULL
        """
    ).fetchall():
        if _path_matches_workspace_rel(ws, row["local_path"], workspace_rel_path):
            return row["cloud_file_id"]

    for row in conn.execute(
        """
        SELECT cloud_file_id, cloud_upload_status, local_path, temp_path
        FROM live_sessions
        WHERE cloud_file_id IS NOT NULL
        """
    ).fetchall():
        if not _cloud_ready(row["cloud_upload_status"], row["cloud_file_id"]):
            continue
        if _path_matches_workspace_rel(ws, row["local_path"], workspace_rel_path):
            return row["cloud_file_id"]
        if _path_matches_workspace_rel(ws, row["temp_path"], workspace_rel_path):
            return row["cloud_file_id"]

    parts = Path(workspace_rel_path).parts
    if len(parts) >= 2 and parts[0] == "creators":
        sec_uid = parts[1]
        manifest = _load_agent_manifest(ws, sec_uid)
        if manifest:
            for key in ("live", "items", "archives"):
                for entry in manifest.get(key) or []:
                    if not isinstance(entry, dict):
                        continue
                    media_path = entry.get("media_path") or entry.get("local_path")
                    if _path_matches_workspace_rel(ws, media_path, workspace_rel_path):
                        found = _cloud_file_from_manifest_entry(entry)
                        if found:
                            return found
    return None


def try_cloud_media_range(
    cfg: AppConfig,
    conn,
    *,
    workspace_rel_path: str,
    range_header: str | None,
) -> StreamingResponse | None:
    if not cfg.aliyundrive.enabled:
        return None
    cloud_file_id = resolve_cloud_file_for_media_path(cfg, conn, workspace_rel_path)
    if not cloud_file_id:
        return None
    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return None
    ext = Path(workspace_rel_path).suffix.lower()
    media_type = {
        ".flv": "video/x-flv",
        ".mp4": "video/mp4",
        ".m4s": "video/mp4",
        ".webm": "video/webm",
    }.get(ext, "application/octet-stream")
    try:
        with AliyunDriveClient.open(token_path) as client:
            return stream_cloud_file(
                client,
                cloud_file_id,
                range_header=range_header,
                media_type=media_type,
            )
    except RuntimeError:
        raise HTTPException(status_code=502, detail="cloud media unavailable") from None
    except Exception:  # noqa: BLE001
        return None


def delete_local_media(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    ws = cfg.ensure_workspace()
    deleted: list[str] = []

    if kind == "live":
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            return {"ok": False, "error": "not_found"}
        if session.status in ("recording", "remuxing"):
            return {"ok": False, "error": "session_active"}

        for raw in (session.local_path, session.temp_path):
            if not raw:
                continue
            path = _resolve_media_path(ws, local_path=raw, temp_path=None)
            if path and path.is_file():
                path.unlink(missing_ok=True)
                deleted.append(workspace_rel(ws, str(path)) or str(path))
        LiveSessionRepo(conn).clear_local_path(item_id)
    else:
        aweme = AwemeRepo(conn).get(item_id)
        if not aweme or aweme.creator_id != creator_id:
            return {"ok": False, "error": "not_found"}
        if not aweme.local_path:
            return {"ok": False, "error": "no_local_path"}
        path = _resolve_media_path(ws, local_path=aweme.local_path, temp_path=None)
        if path and path.is_file():
            path.unlink(missing_ok=True)
            deleted.append(workspace_rel(ws, str(path)) or str(path))
        AwemeRepo(conn).clear_local_path(item_id)

    refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)
    return {
        "ok": True,
        "kind": kind,
        "item_id": item_id,
        "deleted_paths": deleted,
    }


def download_from_cloud(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
) -> dict[str, Any]:
    if kind != "live":
        return {"ok": False, "error": "cloud_not_supported_for_vod"}

    ad = cfg.aliyundrive
    if not ad.enabled:
        return {"ok": False, "error": "aliyundrive_disabled"}

    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    session = LiveSessionRepo(conn).get(item_id)
    if not session or session.creator_id != creator_id:
        return {"ok": False, "error": "not_found"}

    upload = _primary_cloud_upload(conn, item_id)
    cloud_file_id = upload.cloud_file_id if upload else session.cloud_file_id
    if not _cloud_ready(
        upload.upload_status if upload else session.cloud_upload_status,
        cloud_file_id,
        relative_path=(upload.cloud_relative_path if upload else None)
        or session.cloud_relative_path,
    ):
        return {"ok": False, "error": "cloud_not_available"}

    ws = cfg.ensure_workspace()
    target_raw = (
        upload.local_path
        if upload and upload.local_path
        else session.local_path or session.temp_path
    )
    rel_for_name = (upload.cloud_relative_path if upload else None) or session.cloud_relative_path
    if not target_raw and rel_for_name:
        name = Path(rel_for_name).name
        target_raw = str(ws / "creators" / creator.sec_uid / "live" / name)
    if not target_raw:
        return {"ok": False, "error": "no_restore_path"}

    target = _resolve_media_path(ws, local_path=target_raw, temp_path=None)
    if target is None:
        rel = workspace_rel(ws, target_raw)
        if not rel:
            return {"ok": False, "error": "invalid_restore_path"}
        target = safe_workspace_path(ws, rel)
    target.parent.mkdir(parents=True, exist_ok=True)

    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return {"ok": False, "error": "aliyundrive_not_logged_in"}

    try:
        with AliyunDriveClient.open(token_path) as client:
            data = client.download_bytes(str(cloud_file_id))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "cloud_download_failed", "detail": str(exc)}

    target.write_bytes(data)
    LiveSessionRepo(conn).update_status(item_id, local_path=str(target))
    refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)
    return {
        "ok": True,
        "kind": kind,
        "item_id": item_id,
        "local_path": workspace_rel(ws, str(target)),
        "bytes": len(data),
    }


def delete_history_record(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
    delete_files: bool = True,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    ws = cfg.ensure_workspace()

    if kind == "live":
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            return {"ok": False, "error": "not_found"}
        if session.status in ("recording", "remuxing"):
            return {"ok": False, "error": "session_active"}
        if delete_files:
            for raw in (session.local_path, session.temp_path):
                if not raw:
                    continue
                path = _resolve_media_path(ws, local_path=raw, temp_path=None)
                if path and path.is_file():
                    _delete_sidecars(path)
                    path.unlink(missing_ok=True)
        LiveSessionRepo(conn).delete(item_id)
    else:
        aweme = AwemeRepo(conn).get(item_id)
        if not aweme or aweme.creator_id != creator_id:
            return {"ok": False, "error": "not_found"}
        if delete_files and aweme.local_path:
            path = _resolve_media_path(ws, local_path=aweme.local_path, temp_path=None)
            if path and path.is_file():
                _delete_sidecars(path)
                path.unlink(missing_ok=True)
        AwemeRepo(conn).delete(item_id)

    refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)
    return {"ok": True, "kind": kind, "item_id": item_id}


def _delete_sidecars(media: Path) -> None:
    stem = media.with_suffix("")
    suffixes = (
        ".transcript.json",
        ".transcript.partial.json",
        ".transcript.md",
        ".summary.json",
        ".summary.md",
    )
    for suffix in suffixes:
        sidecar = Path(f"{stem}{suffix}")
        sidecar.unlink(missing_ok=True)


def _resolve_history_summarize_target(
    ws: Path,
    *,
    kind: HistoryKind,
    local_path: str | None,
    temp_path: str | None = None,
) -> Path | None:
    media = _resolve_media_path(ws, local_path=local_path, temp_path=temp_path)
    if media and media.is_file():
        return media
    base_raw = local_path or temp_path
    if not base_raw:
        return None
    rel = workspace_rel(ws, base_raw)
    candidates: list[Path] = []
    if rel:
        try:
            candidates.append(safe_workspace_path(ws, rel))
        except Exception:
            pass
    if Path(base_raw).is_absolute():
        candidates.append(Path(base_raw))
    for candidate in candidates:
        resolved = resolve_summarize_paths(candidate, workspace=ws)
        if resolved is not None:
            return resolved[0]
        transcript = transcript_path_for_media(candidate)
        if transcript.is_file():
            return transcript
    return None


def summarize_history_item(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
    force: bool = False,
) -> dict[str, Any]:
    if not cfg.summarize.enabled:
        return {"ok": False, "error": "summarize_disabled"}

    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    ws = cfg.ensure_workspace()
    target: Path | None = None

    if kind == "live":
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            return {"ok": False, "error": "not_found"}
        target = _resolve_history_summarize_target(
            ws,
            kind=kind,
            local_path=session.local_path,
            temp_path=session.temp_path,
        )
    else:
        aweme = AwemeRepo(conn).get(item_id)
        if not aweme or aweme.creator_id != creator_id:
            return {"ok": False, "error": "not_found"}
        target = _resolve_history_summarize_target(
            ws,
            kind=kind,
            local_path=aweme.local_path,
        )

    if target is None:
        return {"ok": False, "error": "no_transcript"}

    ok, reason = summarize_engine_available(cfg)
    if not ok:
        return {"ok": False, "error": "summarize_unavailable", "detail": reason}

    try:
        backend = create_summarize_backend(cfg)
    except SummarizeConfigError as exc:
        return {"ok": False, "error": "summarize_unavailable", "detail": str(exc)}

    try:
        item = summarize_one(target, cfg, backend, force=force)
    except SummarizeError as exc:
        return {"ok": False, "error": "summarize_failed", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "summarize_failed", "detail": str(exc)}

    refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=ws)
    summary_path = item.get("summary_path")
    rel_summary = workspace_rel(ws, summary_path) if summary_path else None
    return {
        "ok": True,
        "kind": kind,
        "item_id": item_id,
        "summarized": bool(item.get("summarized") or (summary_path and not item.get("skipped"))),
        "skipped": bool(item.get("skipped")),
        "summary_path": rel_summary,
    }


def retry_vod_download(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    item_id: str,
) -> dict[str, Any]:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator_not_found"}

    aweme = AwemeRepo(conn).get(item_id)
    if not aweme or aweme.creator_id != creator_id:
        return {"ok": False, "error": "not_found"}
    if aweme.sync_status != "failed":
        return {
            "ok": False,
            "error": "invalid_status",
            "status": aweme.sync_status,
        }

    if not AwemeRepo(conn).reset_failed_to_listed(item_id):
        return {"ok": False, "error": "retry_failed"}

    task_id = MonitorTaskRepo(conn).enqueue(
        creator_id=creator_id,
        task_type="download",
        dedupe_key=f"download:{creator_id}",
        priority=10,
        payload_json=f'{{"platform": "{creator.platform}"}}',
    )
    return {
        "ok": True,
        "item_id": item_id,
        "task_id": task_id,
        "queued": task_id is not None,
    }
