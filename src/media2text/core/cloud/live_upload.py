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
from media2text.core.cloud.cleanup import (
    RollingCleanupResult,
    format_rolling_cleanup_notify_body,
    is_recycle_bin_delete_error,
    is_video_cleanup_filename,
)
from media2text.core.cloud.paths import sanitize_path_segment
from media2text.core.config import AppConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.platform.profile import is_profile_stale, sync_creator_profile
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.live.segment_watcher import hls_parts_pending_upload
from media2text.core.storage.models import CreatorRow
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo
from media2text.core.summarize.writer import summary_paths_for_media

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


def _media_file_kind(media: Path) -> str:
    ext = media.suffix.lower()
    if ext == ".flv":
        return "flv"
    if ext == ".m3u8":
        return "m3u8"
    if ext == ".m4s":
        return "m4s"
    return "mp4"


def _hls_cloud_folder(
    cfg: AppConfig,
    *,
    creator: CreatorRow,
    creator_key: str,
    session_dir: Path,
) -> tuple[str, str]:
    ad = cfg.aliyundrive
    rel_base = f"{ad.root_folder}/{creator.platform}/{creator_key}/live/{session_dir.name}"
    return rel_base, session_dir.name


def _upload_file_to_cloud(
    client: AliyunDriveClient,
    *,
    cfg: AppConfig,
    conn,
    session_id: str,
    creator: CreatorRow,
    folder_id: str,
    rel_base: str,
    local_path: Path,
    file_kind: str,
    part_index: int | None = None,
) -> dict[str, str]:
    ad = cfg.aliyundrive
    uploads = CloudUploadRepo(conn)
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
        part_index=part_index,
    )
    rel_path = f"{rel_base}/{local_path.name}"
    if part_index is not None and local_path.parent.name == "parts":
        rel_path = f"{rel_base}/parts/{local_path.name}"
    check_mode, replace_id = _check_name_mode_for_upload(
        client, parent_file_id=folder_id, local_path=local_path
    )
    attempt = 0
    last_error: str | None = None
    while attempt <= ad.upload_retries:
        try:
            result = client.upload_file_streaming(
                local_path,
                parent_file_id=folder_id,
                remote_name=local_path.name,
                check_name_mode=check_mode,
                replace_file_id=replace_id,
            )
            file_id_raw = result.get("file_id")
            if not file_id_raw:
                remote = client.find_exact_name_in_parent(
                    local_path.name, parent_file_id=folder_id
                )
                file_id_raw = remote["file_id"] if remote else None
            file_id = str(file_id_raw or "")
            if not file_id:
                last_error = f"missing cloud file_id for {local_path.name}"
                uploads.mark_failed(upload_id, error=last_error)
                raise RuntimeError(last_error)
            uploads.mark_done(
                upload_id,
                cloud_file_id=file_id,
                cloud_relative_path=rel_path,
            )
            return {"cloud_file_id": file_id, "cloud_path": rel_path}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            attempt += 1
            if attempt > ad.upload_retries:
                uploads.mark_failed(upload_id, error=last_error)
                raise
    raise RuntimeError(last_error or "upload_failed")


def upload_live_part(
    cfg: AppConfig,
    conn,
    *,
    session_id: str,
    session_dir: Path,
    part_index: int,
    part_path: Path,
    creator: CreatorRow,
    notify: NotifyService | None = None,
) -> dict[str, Any]:
    """Upload a single HLS .m4s part and refresh master.m3u8 (D16)."""
    ad = cfg.aliyundrive
    if not ad.enabled:
        return {"ok": False, "error": "aliyundrive_disabled"}

    notify = notify or NotifyService(cfg)
    creator_key, skip_reason = _resolve_creator_key(cfg, conn, creator)
    if not creator_key:
        return {"ok": False, "error": skip_reason or "profile_not_synced"}

    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return {"ok": False, "error": "token_missing"}

    rel_base, _ = _hls_cloud_folder(
        cfg, creator=creator, creator_key=creator_key, session_dir=session_dir
    )
    master = session_dir / "master.m3u8"
    init_mp4 = session_dir / "init.mp4"
    total_size = part_path.stat().st_size
    for extra in (master, init_mp4):
        if extra.is_file():
            total_size += extra.stat().st_size

    try:
        with AliyunDriveClient.open(token_path) as client:
            cap = client.get_account_capacity()
            if cap.free < max(ad.min_free_bytes, total_size):
                deleted = rolling_cleanup(
                    client,
                    cfg=cfg,
                    conn=conn,
                    needed_bytes=max(ad.min_free_bytes, total_size),
                )
                if deleted and notify.enabled:
                    notify.emit(
                        NotifyEvent(
                            kind=EventKind.UPLOAD_CLEANUP,
                            title=creator_label(creator),
                            body=format_rolling_cleanup_notify_body(deleted),
                        )
                    )
                cap = client.get_account_capacity()
                if cap.free < max(ad.min_free_bytes, total_size):
                    return {"ok": False, "error": "insufficient_space"}

            live_folder = [ad.root_folder, creator.platform, creator_key, "live", session_dir.name]
            folder_id = client.ensure_folder_path(
                live_folder,
                parent_file_id=ad.parent_file_id,
            )
            parts_folder_id = client.ensure_folder_path(
                ["parts"],
                parent_file_id=folder_id,
            )

            part_result = _upload_file_to_cloud(
                client,
                cfg=cfg,
                conn=conn,
                session_id=session_id,
                creator=creator,
                folder_id=parts_folder_id,
                rel_base=rel_base,
                local_path=part_path,
                file_kind="m4s",
                part_index=part_index,
            )

            if init_mp4.is_file():
                _upload_file_to_cloud(
                    client,
                    cfg=cfg,
                    conn=conn,
                    session_id=session_id,
                    creator=creator,
                    folder_id=folder_id,
                    rel_base=rel_base,
                    local_path=init_mp4,
                    file_kind="init_mp4",
                    part_index=None,
                )

            SegmentManifestRepo(conn).export_json(session_id, session_dir=session_dir)
            manifest_json = session_dir / "session.manifest.json"
            if manifest_json.is_file():
                _upload_file_to_cloud(
                    client,
                    cfg=cfg,
                    conn=conn,
                    session_id=session_id,
                    creator=creator,
                    folder_id=folder_id,
                    rel_base=rel_base,
                    local_path=manifest_json,
                    file_kind="manifest_json",
                    part_index=None,
                )

            if master.is_file():
                _upload_file_to_cloud(
                    client,
                    cfg=cfg,
                    conn=conn,
                    session_id=session_id,
                    creator=creator,
                    folder_id=folder_id,
                    rel_base=rel_base,
                    local_path=master,
                    file_kind="m3u8",
                    part_index=None,
                )

            return {"ok": True, **part_result}
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "upload_live_part_failed",
            session_id=session_id,
            part_index=part_index,
            error=str(exc),
        )
        return {"ok": False, "error": str(exc)}


def upload_hls_session_sidecars(
    cfg: AppConfig,
    conn,
    *,
    session_id: str,
    session_dir: Path,
    anchor: Path,
    creator: CreatorRow,
    notify: NotifyService | None = None,
) -> dict[str, Any]:
    """Finalize: single upload of transcript/summary/manifest sidecars (D15)."""
    ad = cfg.aliyundrive
    if not ad.enabled or not ad.upload_on_live_complete:
        return {}

    notify = notify or NotifyService(cfg)
    creator_key, skip_reason = _resolve_creator_key(cfg, conn, creator)
    if not creator_key:
        return {"upload_skipped": True, "upload_skip_reason": skip_reason}

    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return {"upload_skipped": True, "upload_skip_reason": "token_missing"}

    rel_base, _ = _hls_cloud_folder(
        cfg, creator=creator, creator_key=creator_key, session_dir=session_dir
    )
    sidecar_paths: list[tuple[Path, str]] = []
    manifest = session_dir / "session.manifest.json"
    if manifest.is_file():
        sidecar_paths.append((manifest, "manifest_json"))
    if ad.upload_transcripts:
        for path, kind in [
            (anchor.with_suffix(".transcript.json"), "transcript_json"),
            (anchor.with_suffix(".transcript.md"), "transcript_md"),
        ]:
            if path.is_file():
                sidecar_paths.append((path, kind))
        summary_md, summary_json = summary_paths_for_media(anchor)
        if summary_md.is_file():
            sidecar_paths.append((summary_md, "summary_md"))
        if summary_json.is_file():
            sidecar_paths.append((summary_json, "summary_json"))

    if not sidecar_paths:
        return {}

    try:
        with AliyunDriveClient.open(token_path) as client:
            folder_id = client.ensure_folder_path(
                [ad.root_folder, creator.platform, creator_key, "live", session_dir.name],
                parent_file_id=ad.parent_file_id,
            )
            uploaded: list[str] = []
            for local_path, file_kind in sidecar_paths:
                _upload_file_to_cloud(
                    client,
                    cfg=cfg,
                    conn=conn,
                    session_id=session_id,
                    creator=creator,
                    folder_id=folder_id,
                    rel_base=rel_base,
                    local_path=local_path,
                    file_kind=file_kind,
                    part_index=None,
                )
                uploaded.append(local_path.name)
            sessions = LiveSessionRepo(conn)
            parts_pending = hls_parts_pending_upload(
                conn, session_id, session_dir=session_dir
            )
            upload_status = "partial" if parts_pending else "done"
            sessions.update_status(session_id, cloud_upload_status=upload_status)
            if uploaded:
                body = f"直播 sidecar 云备份完成\n{session_dir.name}\n{', '.join(uploaded)}"
                if parts_pending:
                    body += "\n（视频分段仍待上传或本地缺失）"
                notify.emit(
                    NotifyEvent(
                        kind=EventKind.UPLOAD_COMPLETED,
                        title=creator_label(creator),
                        body=body,
                    )
                )
            return {
                "upload_completed": True,
                "files": uploaded,
                "cloud_upload_status": upload_status,
                "parts_pending": parts_pending,
            }
    except Exception as exc:  # noqa: BLE001
        log.exception("upload_hls_sidecars_failed", session_id=session_id, error=str(exc))
        LiveSessionRepo(conn).update_status(session_id, cloud_upload_status="failed")
        return {"upload_failed": True, "upload_error": str(exc)}


def is_hls_session_media(media: Path) -> bool:
    return media.suffix.lower() == ".m3u8" or media.name == "master.m3u8"


def _upload_paths(cfg: AppConfig, mp4: Path) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = [(mp4, _media_file_kind(mp4))]
    if not cfg.aliyundrive.upload_transcripts:
        return items
    json_path = mp4.with_suffix(".transcript.json")
    md_path = mp4.with_suffix(".transcript.md")
    if json_path.is_file():
        items.append((json_path, "transcript_json"))
    if md_path.is_file():
        items.append((md_path, "transcript_md"))
    summary_md, summary_json = summary_paths_for_media(mp4)
    if summary_md.is_file():
        items.append((summary_md, "summary_md"))
    if summary_json.is_file():
        items.append((summary_json, "summary_json"))
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


def _purge_recycle_bin_videos(
    client: AliyunDriveClient,
    *,
    needed_bytes: int,
    free: int,
    max_delete: int,
    already_deleted: int,
) -> tuple[list[str], int, int]:
    """Permanently delete oldest video files still in recycle bin.

    Returns (deleted_names, updated_free, freed_bytes).
    """
    deleted_names: list[str] = []
    freed = 0
    try:
        items = client.list_recycle_bin()
    except Exception as exc:  # noqa: BLE001
        log.warning("aliyundrive_recyclebin_list_failed", error=str(exc))
        return deleted_names, free, freed

    video_items = [
        item
        for item in items
        if item.get("type") == "file"
        and item.get("file_id")
        and is_video_cleanup_filename(str(item.get("name") or ""))
    ]
    video_items.sort(key=lambda i: str(i.get("updated_at") or i.get("trashed_at") or ""))

    for item in video_items:
        if free >= needed_bytes or (already_deleted + len(deleted_names)) >= max_delete:
            break
        file_id = str(item["file_id"])
        name = str(item.get("name") or file_id)
        try:
            client.delete_file_permanently(file_id)
            deleted_names.append(name)
            size = int(item.get("size") or 0)
            freed += size
            free += size
            log.info(
                "aliyundrive_recyclebin_purged",
                file_name=name,
                file_id=file_id,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "aliyundrive_recyclebin_purge_failed",
                file_name=name,
                error=str(exc),
            )
    return deleted_names, free, freed


def rolling_cleanup(
    client: AliyunDriveClient,
    *,
    cfg: AppConfig,
    conn,
    needed_bytes: int,
) -> RollingCleanupResult:
    ad = cfg.aliyundrive
    if ad.on_insufficient_space != "rolling_cleanup":
        return RollingCleanupResult()
    repo = CloudUploadRepo(conn)
    root = ad.root_folder.strip("/")
    require_transcripts = cfg.live.transcribe_on_complete and ad.upload_transcripts
    candidates = repo.list_cleanup_candidates(
        root_prefix=f"{root}/",
        require_transcripts=require_transcripts,
    )
    db_deleted: list[str] = []
    recycle_bin_deleted: list[str] = []
    freed = 0
    cap = client.get_account_capacity()
    free = cap.free
    max_delete = ad.rolling_cleanup.max_delete_per_round
    deleted_count = 0

    for row in candidates:
        if free >= needed_bytes or deleted_count >= max_delete:
            break
        if not row.cloud_file_id:
            continue
        try:
            client.delete_file_permanently(row.cloud_file_id)
            repo.delete_record(row.id)
            db_deleted.append(row.file_name)
            deleted_count += 1
            size = int(row.size or 0)
            freed += size
            free += size
        except Exception as exc:  # noqa: BLE001
            if is_recycle_bin_delete_error(exc):
                # File already trashed; drop stale DB row and rely on recycle-bin purge.
                repo.delete_record(row.id)
                db_deleted.append(row.file_name)
                deleted_count += 1
                log.info(
                    "aliyundrive_cleanup_stale_recycle",
                    file_name=row.file_name,
                )
            else:
                log.warning(
                    "aliyundrive_cleanup_failed",
                    file_name=row.file_name,
                    error=str(exc),
                )

    if (
        ad.rolling_cleanup.purge_recycle_bin
        and free < needed_bytes
        and deleted_count < max_delete
    ):
        rb_names, free, rb_freed = _purge_recycle_bin_videos(
            client,
            needed_bytes=needed_bytes,
            free=free,
            max_delete=max_delete,
            already_deleted=deleted_count,
        )
        recycle_bin_deleted.extend(rb_names)
        deleted_count += len(rb_names)
        freed += rb_freed

    result = RollingCleanupResult(
        db=tuple(db_deleted),
        recycle_bin=tuple(recycle_bin_deleted),
    )
    if result:
        log.info(
            "aliyundrive_rolling_cleanup",
            deleted=result.total,
            db=len(result.db),
            recycle_bin=len(result.recycle_bin),
            freed_bytes=freed,
        )
    return result


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
            notify.emit(
                NotifyEvent(
                    kind=EventKind.UPLOAD_CLEANUP,
                    title=creator_label(creator),
                    body=format_rolling_cleanup_notify_body(deleted),
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
                file_id_raw = result.get("file_id")
                if not file_id_raw:
                    remote = client.find_exact_name_in_parent(
                        local_path.name, parent_file_id=folder_id
                    )
                    file_id_raw = remote["file_id"] if remote else None
                file_id = str(file_id_raw or "")
                if not file_id:
                    last_error = f"missing cloud file_id for {local_path.name}"
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
                uploads.mark_done(
                    upload_id,
                    cloud_file_id=file_id,
                    cloud_relative_path=rel_path,
                )
                uploaded_files.append(local_path)
                if file_kind in ("mp4", "flv"):
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


def upload_summary_sidecars_if_needed(
    cfg: AppConfig,
    conn,
    *,
    session_id: str,
    media: Path,
    creator: CreatorRow,
    notify: NotifyService | None = None,
) -> dict[str, Any]:
    """Upload .summary.* after summarize finished if initial upload already completed."""
    ad = cfg.aliyundrive
    if not ad.enabled or not ad.upload_transcripts:
        return {}

    summary_md, summary_json = summary_paths_for_media(media)
    if not summary_md.is_file() and not summary_json.is_file():
        return {}

    sessions = LiveSessionRepo(conn)
    row = sessions.get(session_id)
    if not row or row.cloud_upload_status != "done":
        return {}

    uploads = CloudUploadRepo(conn)
    done_kinds = {
        u.file_kind
        for u in uploads.list_for_session(session_id)
        if u.upload_status == "done"
    }
    if "summary_md" in done_kinds and "summary_json" in done_kinds:
        return {}
    if not summary_md.is_file() and not summary_json.is_file():
        return {}

    notify = notify or NotifyService(cfg)
    token_path = cfg.aliyundrive_token_path()
    if not token_path.is_file():
        return {"upload_supplemental_skipped": True, "reason": "token_missing"}

    creator_key, skip_reason = _resolve_creator_key(cfg, conn, creator)
    if not creator_key:
        return {"upload_supplemental_skipped": True, "reason": skip_reason}

    try:
        with AliyunDriveClient.open(token_path) as client:
            return _upload_summary_sidecars(
                client,
                cfg=cfg,
                conn=conn,
                session_id=session_id,
                media=media,
                creator=creator,
                creator_key=creator_key,
                notify=notify,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("aliyundrive_summary_supplemental_failed", error=str(exc))
        return {"upload_supplemental_failed": str(exc)}


def _upload_summary_sidecars(
    client: AliyunDriveClient,
    *,
    cfg: AppConfig,
    conn,
    session_id: str,
    media: Path,
    creator: CreatorRow,
    creator_key: str,
    notify: NotifyService,
) -> dict[str, Any]:
    ad = cfg.aliyundrive
    uploads = CloudUploadRepo(conn)
    folder_id = client.ensure_folder_path(
        [ad.root_folder, creator.platform, creator_key, "live"],
        parent_file_id=ad.parent_file_id,
    )
    rel_base = f"{ad.root_folder}/{creator.platform}/{creator_key}/live"
    uploaded: list[str] = []
    summary_md, summary_json = summary_paths_for_media(media)
    done_kinds = {
        u.file_kind
        for u in uploads.list_for_session(session_id)
        if u.upload_status == "done"
    }

    for local_path, file_kind in [
        (summary_md, "summary_md"),
        (summary_json, "summary_json"),
    ]:
        if not local_path.is_file() or file_kind in done_kinds:
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
        result = client.upload_file_streaming(
            local_path,
            parent_file_id=folder_id,
            remote_name=local_path.name,
            check_name_mode=check_mode,
            replace_file_id=replace_id,
        )
        file_id = result.get("file_id")
        if not file_id:
            remote = client.find_exact_name_in_parent(
                local_path.name, parent_file_id=folder_id
            )
            file_id = remote["file_id"] if remote else None
        if not file_id:
            raise RuntimeError(f"upload missing file_id for {local_path.name}")
        uploads.mark_done(
            upload_id,
            cloud_file_id=str(file_id),
            cloud_relative_path=rel_path,
        )
        uploaded.append(local_path.name)

    if uploaded:
        log.info("aliyundrive_summary_supplemental", files=uploaded)
        return {"upload_supplemental": True, "files": uploaded}
    return {}
