"""Live recording backup to personal Aliyun Drive after finalize."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from media2text.core.cloud.aliyundrive import (
    AliyunDriveClient,
    compute_pre_hash,
    decide_duplicate_action,
)
from media2text.core.cloud.paths import sanitize_path_segment
from media2text.core.config import AppConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.platform.profile import is_profile_stale, sync_creator_profile
from media2text.core.storage.models import CreatorRow
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo

log = structlog.get_logger()


def _transcribe_status_from_meta(cfg: AppConfig, transcribe_meta: dict[str, Any]) -> str:
    if not cfg.live.transcribe_on_complete:
        return "none"
    if transcribe_meta.get("transcribed"):
        return "done"
    if transcribe_meta.get("transcribe_skipped"):
        return "skipped"
    if transcribe_meta.get("transcribe_error"):
        return "failed"
    return "none"


def _transcribe_gate_open(cfg: AppConfig, mp4: Path, transcribe_meta: dict[str, Any]) -> tuple[bool, str | None]:
    if not cfg.live.transcribe_on_complete:
        return True, None
    if not cfg.aliyundrive.upload_transcripts:
        return True, None
    if transcribe_meta.get("transcribed"):
        return True, None
    if transcribe_meta.get("transcribe_skipped"):
        return True, None
    json_path = mp4.with_suffix(".transcript.json")
    if json_path.is_file():
        return True, None
    if transcribe_meta.get("transcribe_error"):
        return False, "transcribe_pending"
    return False, "transcribe_pending"


def _resolve_creator_key(cfg: AppConfig, conn, creator: CreatorRow) -> tuple[str | None, str | None]:
    ad = cfg.aliyundrive
    stale_days = cfg.monitor.profile_stale_days
    display_name = creator.display_name
    if not display_name or is_profile_stale(
        display_name=display_name,
        profile_synced_at=creator.profile_synced_at,
        stale_days=stale_days,
    ):
        sync_result = sync_creator_profile(cfg, creator.id)
        if sync_result.get("ok"):
            creator = CreatorRepo(conn).get(creator.id) or creator
            display_name = creator.display_name or sync_result.get("display_name")
        else:
            log.warning(
                "aliyundrive_profile_sync_failed",
                creator_id=creator.id,
                error=sync_result.get("error"),
            )
    if not display_name:
        return None, "profile_not_synced"
    if ad.creator_key != "nickname":
        return None, "unsupported_creator_key"
    key = sanitize_path_segment(display_name)
    if not key:
        return None, "profile_not_synced"
    return key, None


def _upload_paths(cfg: AppConfig, mp4: Path) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = [(mp4, "mp4")]
    if not cfg.aliyundrive.upload_transcripts:
        return items
    json_path = mp4.with_suffix(".transcript.json")
    md_path = mp4.with_suffix(".transcript.md")
    if json_path.is_file():
        items.append((json_path, "transcript_json"))
    if md_path.is_file():
        items.append((md_path, "transcript_md"))
    return items


def _check_name_mode_for_upload(
    client: AliyunDriveClient,
    *,
    parent_file_id: str,
    local_path: Path,
) -> tuple[str, str | None]:
    remote = client.find_exact_name_in_parent(local_path.name, parent_file_id=parent_file_id)
    action = decide_duplicate_action(
        local_size=local_path.stat().st_size,
        local_pre_hash=compute_pre_hash(local_path),
        remote_file=remote,
    )
    if action == "new":
        return "auto_rename", None
    if action == "overwrite":
        return "overwrite", str(remote["file_id"]) if remote else None
    return "auto_rename", None


def rolling_cleanup(
    client: AliyunDriveClient,
    *,
    cfg: AppConfig,
    conn,
    needed_bytes: int,
) -> list[str]:
    ad = cfg.aliyundrive
    if ad.on_insufficient_space != "rolling_cleanup":
        return []
    repo = CloudUploadRepo(conn)
    root = ad.root_folder.strip("/")
    require_transcripts = cfg.live.transcribe_on_complete and ad.upload_transcripts
    candidates = repo.list_cleanup_candidates(
        root_prefix=f"{root}/",
        require_transcripts=require_transcripts,
    )
    deleted_names: list[str] = []
    freed = 0
    cap = client.get_account_capacity()
    free = cap.free
    max_delete = ad.rolling_cleanup.max_delete_per_round

    for row in candidates:
        if free >= needed_bytes or len(deleted_names) >= max_delete:
            break
        if not row.cloud_file_id:
            continue
        try:
            client.trash(row.cloud_file_id)
            repo.delete_record(row.id)
            deleted_names.append(row.file_name)
            size = int(row.size or 0)
            freed += size
            free += size
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "aliyundrive_cleanup_failed",
                file_name=row.file_name,
                error=str(exc),
            )
    if deleted_names:
        log.info(
            "aliyundrive_rolling_cleanup",
            deleted=len(deleted_names),
            freed_bytes=freed,
        )
    return deleted_names


def maybe_upload_live_to_aliyundrive(
    cfg: AppConfig,
    conn,
    *,
    session_id: str,
    mp4: Path,
    creator: CreatorRow,
    transcribe_meta: dict[str, Any],
    notify: NotifyService | None = None,
) -> dict[str, Any]:
    ad = cfg.aliyundrive
    if not ad.enabled or not ad.upload_on_live_complete:
        return {}

    notify = notify or NotifyService(cfg)
    sessions = LiveSessionRepo(conn)

    transcribe_status = _transcribe_status_from_meta(cfg, transcribe_meta)
    sessions.update_status(session_id, transcribe_status=transcribe_status)

    gate_ok, gate_reason = _transcribe_gate_open(cfg, mp4, transcribe_meta)
    if not gate_ok:
        sessions.update_status(session_id, cloud_upload_status="skipped")
        meta = {"upload_skipped": True, "upload_skip_reason": gate_reason}
        notify.emit(
            NotifyEvent(
                kind=EventKind.UPLOAD_SKIPPED,
                title=creator_label(creator),
                body=f"云备份跳过：{gate_reason}\n{mp4.name}",
            )
        )
        return meta

    creator_key, skip_reason = _resolve_creator_key(cfg, conn, creator)
    if not creator_key:
        sessions.update_status(session_id, cloud_upload_status="skipped")
        meta = {"upload_skipped": True, "upload_skip_reason": skip_reason}
        notify.emit(
            NotifyEvent(
                kind=EventKind.UPLOAD_SKIPPED,
                title=creator_label(creator),
                body=f"云备份跳过：{skip_reason}\n{mp4.name}",
            )
        )
        return meta

    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        sessions.update_status(session_id, cloud_upload_status="skipped")
        meta = {"upload_skipped": True, "upload_skip_reason": "token_missing"}
        notify.emit(
            NotifyEvent(
                kind=EventKind.UPLOAD_SKIPPED,
                title=creator_label(creator),
                body=f"云备份跳过：未登录阿里云盘\n{mp4.name}",
            )
        )
        return meta

    try:
        with AliyunDriveClient.open(token_path) as client:
            return _upload_with_client(
                client,
                cfg=cfg,
                conn=conn,
                session_id=session_id,
                mp4=mp4,
                creator=creator,
                creator_key=creator_key,
                notify=notify,
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("aliyundrive_upload_failed", session_id=session_id, error=str(exc))
        sessions.update_status(session_id, cloud_upload_status="failed")
        notify.emit(
            NotifyEvent(
                kind=EventKind.UPLOAD_FAILED,
                title=creator_label(creator),
                body=f"云备份失败\n{mp4.name}\n{exc}",
            )
        )
        return {"upload_failed": True, "upload_error": str(exc)}


def _upload_with_client(
    client: AliyunDriveClient,
    *,
    cfg: AppConfig,
    conn,
    session_id: str,
    mp4: Path,
    creator: CreatorRow,
    creator_key: str,
    notify: NotifyService,
) -> dict[str, Any]:
    ad = cfg.aliyundrive
    sessions = LiveSessionRepo(conn)
    uploads = CloudUploadRepo(conn)

    cap = client.get_account_capacity()
    total_upload_size = sum(p.stat().st_size for p, _ in _upload_paths(cfg, mp4) if p.is_file())
    if cap.free < max(ad.min_free_bytes, total_upload_size):
        deleted = rolling_cleanup(
            client,
            cfg=cfg,
            conn=conn,
            needed_bytes=max(ad.min_free_bytes, total_upload_size),
        )
        if deleted and notify.enabled:
            lines = "\n".join(f"- {name}" for name in deleted)
            notify.emit(
                NotifyEvent(
                    kind=EventKind.UPLOAD_CLEANUP,
                    title=creator_label(creator),
                    body=f"云盘滚动清理，已删除 {len(deleted)} 个文件：\n{lines}",
                )
            )
        cap = client.get_account_capacity()
        if cap.free < max(ad.min_free_bytes, total_upload_size):
            sessions.update_status(session_id, cloud_upload_status="skipped")
            meta = {"upload_skipped": True, "upload_skip_reason": "insufficient_space"}
            notify.emit(
                NotifyEvent(
                    kind=EventKind.UPLOAD_SKIPPED,
                    title=creator_label(creator),
                    body=f"云备份跳过：空间不足\n{mp4.name}",
                )
            )
            return meta

    folder_id = client.ensure_folder_path(
        [ad.root_folder, creator.platform, creator_key, "live"],
        parent_file_id=ad.parent_file_id,
    )
    rel_base = f"{ad.root_folder}/{creator.platform}/{creator_key}/live"

    uploaded_files: list[Path] = []
    mp4_file_id: str | None = None
    mp4_rel_path: str | None = None
    last_error: str | None = None

    for local_path, file_kind in _upload_paths(cfg, mp4):
        if not local_path.is_file():
            continue
        size = local_path.stat().st_size
        pre_hash = compute_pre_hash(local_path)
        upload_id = uploads.create(
            session_id=session_id,
            creator_id=creator.id,
            platform=creator.platform,
            file_name=local_path.name,
            file_kind=file_kind,
            local_path=str(local_path),
            size=size,
            pre_hash=pre_hash,
        )
        rel_path = f"{rel_base}/{local_path.name}"
        check_mode, replace_id = _check_name_mode_for_upload(
            client, parent_file_id=folder_id, local_path=local_path
        )
        attempt = 0
        while attempt <= ad.upload_retries:
            try:
                result = client.upload_file_streaming(
                    local_path,
                    parent_file_id=folder_id,
                    remote_name=local_path.name,
                    check_name_mode=check_mode,
                    replace_file_id=replace_id,
                )
                file_id = str(result.get("file_id") or client.find_exact_name_in_parent(
                    local_path.name, parent_file_id=folder_id
                )["file_id"])
                uploads.mark_done(
                    upload_id,
                    cloud_file_id=file_id,
                    cloud_relative_path=rel_path,
                )
                uploaded_files.append(local_path)
                if file_kind == "mp4":
                    mp4_file_id = file_id
                    mp4_rel_path = rel_path
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                attempt += 1
                if attempt > ad.upload_retries:
                    uploads.mark_failed(upload_id, error=last_error)
                    sessions.update_status(session_id, cloud_upload_status="failed")
                    notify.emit(
                        NotifyEvent(
                            kind=EventKind.UPLOAD_FAILED,
                            title=creator_label(creator),
                            body=f"云备份失败\n{local_path.name}\n{last_error}",
                        )
                    )
                    return {"upload_failed": True, "upload_error": last_error}

    if ad.delete_local_after_upload:
        for path in uploaded_files:
            path.unlink(missing_ok=True)

    sessions.update_status(
        session_id,
        cloud_upload_status="done",
        cloud_file_id=mp4_file_id,
        cloud_relative_path=mp4_rel_path,
        local_path=None if ad.delete_local_after_upload and mp4 in uploaded_files else str(mp4),
    )

    notify.emit(
        NotifyEvent(
            kind=EventKind.UPLOAD_COMPLETED,
            title=creator_label(creator),
            body=f"云备份完成\n{mp4_rel_path or mp4.name}",
        )
    )
    return {
        "upload_completed": True,
        "cloud_file_id": mp4_file_id,
        "cloud_relative_path": mp4_rel_path,
        "cloud_upload_status": "done",
    }
