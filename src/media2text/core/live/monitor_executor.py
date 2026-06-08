from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from media2text.core.archive.hook import index_transcript_safe
from media2text.core.config import AppConfig
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.notify.outbox import NotifyDaemonGuard
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.platform.bilibili.dynamic import sync_creator_dynamics
from media2text.core.platform.vod import download_pending, sync_creator
from media2text.core.storage.repos import (
    AwemeRepo,
    CreatorRepo,
    LiveSessionRepo,
    MonitorTaskRepo,
)
from media2text.core.transcribe.errors import TranscribeConfigError
from media2text.core.transcribe.factory import (
    create_transcribe_backend,
    transcribe_engine_available,
)
from media2text.core.transcribe.whisper import write_transcript_outputs
from media2text.core.workspace import open_db

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()

_PLAYWRIGHT_SEM = threading.Semaphore(1)
_PLAYWRIGHT_TASK_TYPES = frozenset({"sync_catalog", "download", "sync_dynamic"})


def run_monitor_task(
    cfg: AppConfig,
    conn,
    *,
    task_id: str,
    watcher: MonitorWatcher | None = None,
    notify: NotifyService | None = None,
) -> dict[str, Any]:
    repo = MonitorTaskRepo(conn)
    task = repo.get(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found", "task_id": task_id}
    if task.status != "running":
        return {"ok": False, "error": f"invalid_status:{task.status}", "task_id": task_id}

    notify_svc = notify or NotifyService(cfg)
    try:
        if task.task_type in _PLAYWRIGHT_TASK_TYPES:
            with _PLAYWRIGHT_SEM:
                result = _dispatch_task(
                    cfg, conn, task, watcher=watcher, notify=notify_svc
                )
        else:
            result = _dispatch_task(
                cfg, conn, task, watcher=watcher, notify=notify_svc
            )
        repo.mark_done(task_id)
        result["ok"] = True
        result["task_id"] = task_id
        return result
    except Exception as exc:  # noqa: BLE001
        outcome = repo.fail_or_retry(
            task_id,
            error=str(exc),
            max_retries=cfg.monitor.task_max_retries,
        )
        log.exception(
            "monitor_task_failed",
            task_id=task_id,
            task_type=task.task_type,
            outcome=outcome,
        )
        return {"ok": False, "error": str(exc), "task_id": task_id, "outcome": outcome}


def _dispatch_task(
    cfg: AppConfig,
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
    notify: NotifyService,
) -> dict[str, Any]:
    if task.task_type == "finalize":
        return _run_finalize(cfg, conn, task, watcher=watcher)
    if task.task_type == "prepare_live_recording":
        return _run_prepare_live_recording(cfg, conn, task, watcher=watcher)
    if task.task_type == "reconnect_recording":
        return _run_reconnect_recording(cfg, conn, task, watcher=watcher)
    if task.task_type == "start_streaming_stt":
        return _run_start_streaming_stt(cfg, conn, task, watcher=watcher)
    if task.task_type == "reconnect_streaming_stt":
        return _run_reconnect_streaming_stt(cfg, conn, task, watcher=watcher)
    if task.task_type == "sync_catalog":
        return _run_sync_catalog(cfg, conn, task, notify=notify)
    if task.task_type == "download":
        return _run_download(cfg, conn, task, notify=notify)
    if task.task_type == "sync_dynamic":
        return _run_sync_dynamic(cfg, conn, task, notify=notify)
    if task.task_type == "pipeline_run":
        return _run_pipeline_run(cfg, task)
    raise ValueError(f"unknown_monitor_task_type:{task.task_type}")


def _core_for_task(
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
) -> LiveRecordingCore:
    if watcher is None:
        raise RuntimeError("live_worker_requires_watcher")
    creator = CreatorRepo(conn).get(task.creator_id)
    if not creator:
        raise ValueError(f"creator_not_found:{task.creator_id}")
    return watcher.core_for_platform(conn, creator.platform)


def _run_prepare_live_recording(
    cfg: AppConfig,
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
) -> dict[str, Any]:
    payload = json.loads(task.payload_json or "{}")
    live_info = LiveRecordingCore.live_info_from_payload(payload)
    core = _core_for_task(conn, task, watcher=watcher)
    return core.run_prepare_live_recording(
        task.creator_id,
        live_info=live_info,
    )


def _run_reconnect_recording(
    cfg: AppConfig,
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
) -> dict[str, Any]:
    payload = json.loads(task.payload_json or "{}")
    session_id = payload.get("session_id")
    if not session_id:
        raise ValueError("reconnect_recording_missing_session_id")
    core = _core_for_task(conn, task, watcher=watcher)
    return core.run_reconnect_recording(session_id)


def _run_start_streaming_stt(
    cfg: AppConfig,
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
) -> dict[str, Any]:
    payload = json.loads(task.payload_json or "{}")
    session_id = payload.get("session_id")
    if not session_id:
        raise ValueError("start_streaming_stt_missing_session_id")
    core = _core_for_task(conn, task, watcher=watcher)
    return core.run_start_streaming_stt(session_id)


def _run_reconnect_streaming_stt(
    cfg: AppConfig,
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
) -> dict[str, Any]:
    payload = json.loads(task.payload_json or "{}")
    session_id = payload.get("session_id")
    if not session_id:
        raise ValueError("reconnect_streaming_stt_missing_session_id")
    core = _core_for_task(conn, task, watcher=watcher)
    return core.run_reconnect_streaming_stt(session_id)


def _run_finalize(
    cfg: AppConfig,
    conn,
    task,
    *,
    watcher: MonitorWatcher | None,
) -> dict[str, Any]:
    if watcher is None:
        raise RuntimeError("finalize_requires_watcher")
    payload = json.loads(task.payload_json or "{}")
    session_id = payload.get("session_id")
    if not session_id:
        raise ValueError("finalize_missing_session_id")
    session = LiveSessionRepo(conn).get(session_id)
    if not session:
        raise ValueError(f"session_not_found:{session_id}")
    creator = CreatorRepo(conn).get(session.creator_id)
    if not creator:
        raise ValueError(f"creator_not_found:{session.creator_id}")
    core = watcher.core_for_platform(conn, creator.platform)
    meta = core._finalize_recording(
        session_id, session.temp_path, session.ffmpeg_pid or 0
    )
    return {"finalized": meta} if meta else {}


def _run_sync_catalog(
    cfg: AppConfig,
    conn,
    task,
    *,
    notify: NotifyService,
) -> dict[str, Any]:
    payload = json.loads(task.payload_json or "{}")
    platform = payload.get("platform", "")
    new_content_kind = (
        EventKind.NEW_AWEME if platform == "douyin" else EventKind.NEW_ARCHIVE
    )
    outcome = sync_creator(cfg, task.creator_id)
    creator = CreatorRepo(conn).get(task.creator_id)
    if creator:
        _emit_sync_notifications(creator, outcome, new_content_kind=new_content_kind, notify=notify)
    if outcome.get("ok"):
        CreatorRepo(conn).mark_sync_needs_download(task.creator_id)
    return {"sync": outcome}


def _run_download(
    cfg: AppConfig,
    conn,
    task,
    *,
    notify: NotifyService,
) -> dict[str, Any]:
    download_result = download_pending(cfg, creator_id=task.creator_id)
    transcribed = 0
    available, _reason = transcribe_engine_available(cfg)
    if available:
        try:
            backend = create_transcribe_backend(cfg)
        except TranscribeConfigError:
            backend = None
        if backend is not None:
            awemes = AwemeRepo(conn)
            for row in awemes.list_downloaded_without_transcript(creator_id=task.creator_id):
                if not row.local_path:
                    continue
                if (row.media_type or "video") == "gallery":
                    continue
                media = Path(row.local_path)
                if media.is_dir():
                    continue
                try:
                    result = backend.transcribe(media, language=cfg.transcribe.language)
                    json_path, _ = write_transcript_outputs(media, result)
                    index_transcript_safe(cfg, json_path)
                    awemes.mark_transcribed(row.aweme_id, transcript_path=str(json_path))
                    transcribed += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "monitor_download_transcribe_failed",
                        aweme_id=row.aweme_id,
                        error=str(exc),
                    )
    creator = CreatorRepo(conn).get(task.creator_id)
    if creator and transcribed > 0:
        notify.emit(
            NotifyEvent(
                kind=EventKind.TRANSCRIBE_COMPLETED,
                title=creator_label(creator),
                body=f"作品转录完成 {transcribed} 条",
            )
        )
    return {"download": download_result, "transcribed": transcribed}


def _run_sync_dynamic(
    cfg: AppConfig,
    conn,
    task,
    *,
    notify: NotifyService,
) -> dict[str, Any]:
    outcome = sync_creator_dynamics(cfg, task.creator_id)
    creator = CreatorRepo(conn).get(task.creator_id)
    if creator and int(outcome.get("new_count") or 0) > 0 and notify:
        notify.emit(
            NotifyEvent(
                kind=EventKind.NEW_DYNAMIC,
                title=creator_label(creator),
                body=f"同步到 {outcome['new_count']} 条新动态",
            )
        )
    return {"dynamic": outcome}


def _run_pipeline_run(cfg: AppConfig, task) -> dict[str, Any]:
    from media2text.core.pipeline.runner import run_pipeline

    return run_pipeline(cfg, creator_id=task.creator_id)


def _emit_sync_notifications(
    creator,
    outcome: dict,
    *,
    new_content_kind: EventKind,
    notify: NotifyService,
) -> None:
    label = creator_label(creator)
    new_count = int(outcome.get("new_count") or 0)
    if new_count > 0:
        noun = "新投稿" if new_content_kind == EventKind.NEW_ARCHIVE else "新作品"
        notify.emit(
            NotifyEvent(
                kind=new_content_kind,
                title=label,
                body=f"同步到 {new_count} 个{noun}",
            )
        )


class MonitorExecutor:
    """Thread pool for monitor_tasks (sync/download/dynamic); priority-0 inline drain."""

    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="monexec",
        )

    def submit(
        self,
        cfg: AppConfig,
        *,
        task_id: str,
        notify: NotifyService,
        watcher: MonitorWatcher | None = None,
    ) -> None:
        def _run() -> None:
            NotifyDaemonGuard.enter()
            conn = open_db(cfg)
            try:
                run_monitor_task(
                    cfg, conn, task_id=task_id, watcher=watcher, notify=notify
                )
            finally:
                conn.close()

        self._executor.submit(_run)

    def drain_pending(
        self,
        cfg: AppConfig,
        conn,
        *,
        notify: NotifyService,
        watcher: MonitorWatcher | None = None,
        limit: int,
        min_priority: int = 1,
        max_priority: int | None = None,
    ) -> None:
        repo = MonitorTaskRepo(conn)
        repo.reset_stale_running(older_than_sec=cfg.monitor.stale_running_sec)
        claimed = repo.claim_pending(
            limit=limit,
            min_priority=min_priority,
            max_priority=max_priority,
        )
        for task in claimed:
            self.submit(
                cfg, task_id=task.id, notify=notify, watcher=watcher
            )

    def claim_and_submit_priority_zero(
        self,
        cfg: AppConfig,
        conn,
        *,
        notify: NotifyService,
        watcher: MonitorWatcher | None = None,
        limit: int = 1,
    ) -> int:
        repo = MonitorTaskRepo(conn)
        repo.reset_stale_running(older_than_sec=cfg.monitor.stale_running_sec)
        claimed = repo.claim_pending(limit=limit, max_priority=0, min_priority=0)
        for task in claimed:
            self.submit(
                cfg, task_id=task.id, notify=notify, watcher=watcher
            )
        return len(claimed)

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
