"""History list media actions: delete local, restore from cloud, delete record."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.core.cloud.aliyundrive import AliyunDriveClient
from media2text.core.config import AppConfig
from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import (
    AwemeRepo,
    CloudUploadRepo,
    CreatorRepo,
    LiveSessionRepo,
)

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
