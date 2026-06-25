from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from datetime import datetime, timezone

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.monitor_executor import run_monitor_task
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.task_reconciler import bootstrap_streaming_stt
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import EventKind, NotifyService
from media2text.core.platform.bilibili.live import LiveWatcher as BilibiliLiveWatcher
from media2text.core.platform.douyin.live import LiveWatcher as DouyinLiveWatcher
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo
from media2text.core.live.scheduler import MonitorScheduler
from media2text.core.workspace import open_db

log = structlog.get_logger()


def _graceful_stop_event(existing: threading.Event | None) -> threading.Event:
    """Return supervisor stop event, or create one wired to SIGTERM/SIGINT for CLI daemon."""
    if existing is not None:
        return existing
    stop = threading.Event()

    def _handle(signum: int, _frame) -> None:
        log.info("monitor_watch_shutdown_signal", signum=signum)
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    return stop


def _merge_live_results(douyin: dict, bilibili: dict) -> dict:
    auth_required = bool(douyin.get("auth_required") or bilibili.get("auth_required"))
    platform_changed = bool(
        douyin.get("platform_changed") or bilibili.get("platform_changed")
    )
    errors = list(douyin.get("errors") or []) + list(bilibili.get("errors") or [])
    started = list(douyin.get("started") or []) + list(bilibili.get("started") or [])
    finalized = list(douyin.get("finalized") or []) + list(bilibili.get("finalized") or [])
    active = int(douyin.get("active") or 0) + int(bilibili.get("active") or 0)
    payload: dict = {
        "douyin": douyin,
        "bilibili": bilibili,
        "started": started,
        "active": active,
        "errors": errors,
        "auth_required": auth_required,
        "platform_changed": platform_changed,
    }
    if finalized:
        payload["finalized"] = finalized
    return payload


def _bilibili_archive_poll_sec(cfg: AppConfig) -> int:
    return cfg.platforms.bilibili.archive_poll_interval_sec


class MonitorWatcher:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._conn = open_db(cfg)
        self._creators = CreatorRepo(self._conn)
        self._session_runtime = SessionRuntime()
        self._douyin_live = DouyinLiveWatcher(cfg, runtime=self._session_runtime)
        self._bilibili_live = BilibiliLiveWatcher(cfg, runtime=self._session_runtime)
        self._notify = NotifyService(cfg)

    def core_for_platform(self, conn, platform: str) -> LiveRecordingCore:
        if platform == "douyin":
            return self._douyin_live.core_for_conn(conn)
        if platform == "bilibili":
            return self._bilibili_live.core_for_conn(conn)
        raise ValueError(f"unsupported_platform:{platform}")

    def run_once(self, *, creator_id: str | None = None) -> dict:
        douyin_live = self._douyin_live.run_once(creator_id=creator_id)
        bilibili_live = self._bilibili_live.run_once(creator_id=creator_id)
        live_result = _merge_live_results(douyin_live, bilibili_live)

        vod_result = self._run_vod_tick(conn=self._conn, creator_id=creator_id)
        archive_result = self._run_archive_tick(conn=self._conn, creator_id=creator_id)
        dynamic_result = self._run_dynamic_tick(
            conn=self._conn,
            creator_id=creator_id,
        )
        self._drain_monitor_tasks_sync()
        errors = (
            list(live_result.get("errors") or [])
            + list(vod_result.get("errors") or [])
            + list(archive_result.get("errors") or [])
            + list(dynamic_result.get("errors") or [])
        )
        auth_required = bool(
            live_result.get("auth_required")
            or vod_result.get("auth_required")
            or archive_result.get("auth_required")
            or dynamic_result.get("auth_required")
        )
        platform_changed = bool(
            live_result.get("platform_changed") or dynamic_result.get("platform_changed")
        )
        return {
            "live": live_result,
            "vod": vod_result,
            "archive": archive_result,
            "dynamic": dynamic_result,
            "errors": errors,
            "auth_required": auth_required,
            "platform_changed": platform_changed,
        }

    def _run_daemon_locked(
        self,
        *,
        creator_id: str | None = None,
        on_live_tick: Callable[[], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        try:
            recovered = bootstrap_streaming_stt(self._cfg, self)
            if recovered:
                log.info("bootstrap_streaming_stt_on_daemon_start", recovered=recovered)
        except Exception as exc:  # noqa: BLE001
            log.warning("bootstrap_streaming_stt_failed", error=str(exc))
        try:
            from media2text.core.live.session_recovery import recover_orphan_sessions

            orphan_recovered = recover_orphan_sessions(self._cfg, self._conn)
            if orphan_recovered:
                log.info("recover_orphan_sessions_on_daemon_start", recovered=orphan_recovered)
        except Exception as exc:  # noqa: BLE001
            log.warning("recover_orphan_sessions_failed", error=str(exc))
        scheduler = MonitorScheduler(self, self._cfg, on_live_tick=on_live_tick)
        scheduler.start(creator_id=creator_id)
        stop = _graceful_stop_event(stop_event)
        try:
            stop.wait()
        finally:
            try:
                scheduler.stop()
            except Exception as exc:
                log.warning("monitor_scheduler_stop_failed", error=str(exc))

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        lock = self._ws / ".monitor-watch.lock"
        try:
            with workspace_lock(lock):
                self._run_daemon_locked(creator_id=creator_id)
        except LockError:
            log.error("monitor_watch_lock_held")
            raise

    def _run_vod_tick(self, *, conn, creator_id: str | None = None) -> dict:
        return self._run_pipeline_tick(
            conn=conn,
            creator_id=creator_id,
            platform="douyin",
            new_content_kind=EventKind.NEW_AWEME,
        )

    def _run_archive_tick(self, *, conn, creator_id: str | None = None) -> dict:
        return self._run_pipeline_tick(
            conn=conn,
            creator_id=creator_id,
            platform="bilibili",
            new_content_kind=EventKind.NEW_ARCHIVE,
        )

    def _run_dynamic_tick(self, *, conn, creator_id: str | None = None) -> dict:
        creators = CreatorRepo(conn)
        targets = [
            c for c in creators.list_content_sync_enabled() if c.platform == "bilibili"
        ]
        if creator_id:
            row = creators.get(creator_id)
            targets = (
                [row]
                if row and row.content_sync_enabled and row.platform == "bilibili"
                else []
            )
        now = datetime.now(timezone.utc).isoformat()
        marked = 0
        for creator in targets:
            if creator.dynamic_due_at is not None:
                continue
            creators.set_dynamic_due(creator.id, now)
            marked += 1
        return {
            "platform": "bilibili",
            "creators": len(targets),
            "marked": marked,
            "errors": [],
            "auth_required": False,
            "platform_changed": False,
            "interval_sec": self._cfg.platforms.bilibili.dynamic_poll_interval_sec,
        }

    def _drain_monitor_tasks_sync(self, *, max_rounds: int = 100) -> None:
        """Single-shot monitor watch: drain enqueued tasks inline."""
        repo = MonitorTaskRepo(self._conn)
        for _ in range(max_rounds):
            repo.reset_stale_running(older_than_sec=self._cfg.monitor.stale_running_sec)
            claimed = repo.claim_pending(limit=self._cfg.monitor.executor_max_parallel)
            if not claimed:
                break
            for task in claimed:
                if task.priority <= 0:
                    conn = self._conn
                else:
                    conn = open_db(self._cfg)
                try:
                    run_monitor_task(
                        self._cfg,
                        conn,
                        task_id=task.id,
                        watcher=self,
                        notify=self._notify,
                    )
                finally:
                    if conn is not self._conn:
                        conn.close()

    def _run_pipeline_tick(
        self,
        *,
        conn,
        creator_id: str | None,
        platform: str,
        new_content_kind: EventKind,
    ) -> dict:
        _ = new_content_kind
        creators = CreatorRepo(conn)
        targets = [
            c for c in creators.list_content_sync_enabled() if c.platform == platform
        ]
        if creator_id:
            row = creators.get(creator_id)
            targets = (
                [row]
                if row and row.content_sync_enabled and row.platform == platform
                else []
            )
        max_n = self._cfg.monitor.max_creators_per_vod_tick
        if max_n > 0:
            targets = targets[:max_n]

        now = datetime.now(timezone.utc).isoformat()
        marked = 0
        for creator in targets:
            if platform == "douyin":
                if creator.vod_due_at is not None:
                    continue
                creators.set_vod_due(creator.id, now)
            else:
                if creator.archive_due_at is not None:
                    continue
                creators.set_archive_due(creator.id, now)
            marked += 1
            log.info(
                "content_due_marked",
                platform=platform,
                creator_id=creator.id,
            )

        payload: dict = {
            "platform": platform,
            "creators": len(targets),
            "marked": marked,
            "errors": [],
            "auth_required": False,
        }
        if platform == "bilibili":
            payload["interval_sec"] = _bilibili_archive_poll_sec(self._cfg)
        return payload
