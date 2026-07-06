from __future__ import annotations

import signal
import threading
from collections.abc import Callable

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.task_reconciler import bootstrap_streaming_stt
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import EventKind, NotifyService
from media2text.core.platform.bilibili.live import LiveWatcher as BilibiliLiveWatcher
from media2text.core.platform.douyin.live import LiveWatcher as DouyinLiveWatcher
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.live.scheduler import MonitorScheduler
from media2text.core.monitor.intervals import bilibili_archive_poll_sec
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway

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


class MonitorWatcher:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._session_runtime = SessionRuntime()
        self._douyin_live = DouyinLiveWatcher(cfg, runtime=self._session_runtime)
        self._bilibili_live = BilibiliLiveWatcher(cfg, runtime=self._session_runtime)
        self._notify = NotifyService(cfg)
        self._session_registry = None

    @property
    def session_registry(self):
        return self._session_registry

    def ensure_session_registry(self):
        from media2text.core.live.session_state import build_registry

        if self._session_registry is None:
            ensure_write_gateway_started(self._cfg)
            self._session_registry = build_registry(self)
        return self._session_registry

    def core_for_platform(self, conn, platform: str) -> LiveRecordingCore:
        if platform == "douyin":
            return self._douyin_live.core_for_conn(conn)
        if platform == "bilibili":
            return self._bilibili_live.core_for_conn(conn)
        raise ValueError(f"unsupported_platform:{platform}")

    def run_once(self, *, creator_id: str | None = None) -> dict:
        """Single debug round: one LiveTick + one SchedulerTick (matches daemon paths)."""
        scheduler = MonitorScheduler(self, self._cfg)
        try:
            return scheduler.run_single_round(creator_id=creator_id)
        finally:
            scheduler.stop()

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
            from media2text.core.live.session_state import build_registry

            self._session_registry = build_registry(self)
            orphan_recovered = self._session_registry.recover_all()
            if orphan_recovered:
                log.info("recover_orphan_sessions_on_daemon_start", recovered=orphan_recovered)
        except Exception as exc:  # noqa: BLE001
            log.warning("recover_orphan_sessions_failed", error=str(exc))
        stop = _graceful_stop_event(stop_event)
        scheduler = MonitorScheduler(
            self,
            self._cfg,
            on_live_tick=on_live_tick,
            stop=stop,
        )
        scheduler.start(creator_id=creator_id)
        try:
            stop.wait()
        finally:
            try:
                scheduler.stop()
            except Exception as exc:
                log.warning("monitor_scheduler_stop_failed", error=str(exc))

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        from media2text.core.runtime.monitor_startup import assert_monitor_slot_available

        blocked = assert_monitor_slot_available(self._cfg)
        if blocked is not None:
            log.error(
                "monitor_watch_already_running",
                managed_by=blocked.get("managed_by"),
                pid=blocked.get("pid"),
            )
            raise LockError(blocked["error"])
        lock = self._ws / ".monitor-watch.lock"

        try:
            with workspace_lock(lock):
                ensure_write_gateway_started(self._cfg)
                try:
                    self._run_daemon_locked(creator_id=creator_id)
                finally:
                    shutdown_write_gateway()
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
        from datetime import datetime, timezone

        from media2text.core.storage.repos import CreatorRepo

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

    def _run_pipeline_tick(
        self,
        *,
        conn,
        creator_id: str | None,
        platform: str,
        new_content_kind: EventKind,
    ) -> dict:
        _ = new_content_kind
        from datetime import datetime, timezone

        from media2text.core.storage.repos import CreatorRepo

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
            payload["interval_sec"] = bilibili_archive_poll_sec(self._cfg)
        return payload
