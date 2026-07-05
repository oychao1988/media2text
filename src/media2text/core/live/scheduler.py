from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from media2text.core.runtime.heartbeat import write_heartbeat
from media2text.core.storage.repos import LiveSessionRepo

from media2text.core.config import AppConfig
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.notify.outbox import NotifyDaemonGuard
from media2text.core.live.post_process_pool import PostProcessExecutor, resolve_post_process_workers
from media2text.core.live.segment_process_pool import (
    SegmentProcessExecutor,
    resolve_segment_process_workers,
)
from media2text.core.live.segment_watcher import SegmentWatcher, set_segment_watcher
from media2text.core.live.probe import run_live_probe_tick
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.errors import ReconcilerDisabledError
from media2text.core.monitor.intervals import (
    DISTILL_DRAIN_INTERVAL_SEC,
    bilibili_archive_poll_sec,
    bilibili_dynamic_poll_sec,
    compute_slow_tick_sleep_sec,
    live_poll_interval,
    vod_poll_interval_sec,
)
from media2text.core.workspace import open_db

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()


class LiveTickLoop:
    """Dedicated thread: live probe only (LP-01/02/03); no inline finalize drain."""

    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        *,
        creator_id: str | None,
        stop: threading.Event,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._creator_id = creator_id
        self._stop = stop
        self._on_tick = on_tick
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="live-probe",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        NotifyDaemonGuard.enter()
        live_poll = live_poll_interval(self._cfg)
        while not self._stop.is_set():
            if self._on_tick is not None:
                self._on_tick()
            else:
                write_heartbeat(
                    self._cfg.ensure_workspace(),
                    last_tick_at=datetime.now(timezone.utc).isoformat(),
                )
            result = run_live_probe_tick(
                self._cfg,
                douyin=self._watcher._douyin_live,
                bilibili=self._watcher._bilibili_live,
                creator_id=self._creator_id,
                session_registry=self._watcher.session_registry,
            )
            active = int(result.get("active_recordings") or 0)
            log.info("live_tick", active_recordings=active, live_poll_sec=live_poll)
            if self._on_tick is not None:
                self._on_tick()
            else:
                write_heartbeat(
                    self._cfg.ensure_workspace(),
                    last_tick_at=datetime.now(timezone.utc).isoformat(),
                )
            self._stop.wait(timeout=live_poll)


class SlowTickLoop:
    """Dedicated thread: VOD, archive, and dynamic ticks on their intervals."""

    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        distill_pool,
        *,
        creator_id: str | None,
        stop: threading.Event,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._distill_pool = distill_pool
        self._creator_id = creator_id
        self._stop = stop
        self._thread: threading.Thread | None = None
        self._last_distill = 0.0

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="slow-tick",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        NotifyDaemonGuard.enter()
        while not self._stop.is_set():
            conn = open_db(self._cfg)
            try:
                self._watcher._run_vod_tick(conn=conn, creator_id=self._creator_id)
                self._watcher._run_archive_tick(conn=conn, creator_id=self._creator_id)
                self._watcher._run_dynamic_tick(conn=conn, creator_id=self._creator_id)
            finally:
                conn.close()
            now_distill = time.time()
            if now_distill - self._last_distill >= DISTILL_DRAIN_INTERVAL_SEC:
                from media2text.agent.creator_distill.pool import resolve_distill_workers

                conn = open_db(self._cfg)
                try:
                    self._distill_pool.drain_pending(
                        self._cfg,
                        conn,
                        limit=resolve_distill_workers(self._cfg),
                    )
                finally:
                    conn.close()
                self._last_distill = now_distill
            sleep_conn = open_db(self._cfg)
            try:
                sleep_sec = compute_slow_tick_sleep_sec(
                    self._cfg,
                    sleep_conn,
                    creator_id=self._creator_id,
                )
            finally:
                sleep_conn.close()
            self._stop.wait(timeout=sleep_sec)


class MonitorScheduler:
    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        *,
        on_live_tick: Callable[[], None] | None = None,
        stop: threading.Event | None = None,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._on_live_tick = on_live_tick
        self._stop = stop if stop is not None else threading.Event()
        max_workers = resolve_post_process_workers(cfg)
        self._post_pool = PostProcessExecutor(max_workers=max_workers)
        seg_workers = resolve_segment_process_workers(cfg)
        self._segment_pool = SegmentProcessExecutor(max_workers=seg_workers)
        self._segment_watcher = SegmentWatcher(cfg, stop=self._stop)
        set_segment_watcher(self._segment_watcher)
        from media2text.agent.creator_distill.pool import (
            CreatorAgentJobPool,
            resolve_distill_workers,
        )

        self._distill_pool = CreatorAgentJobPool(max_workers=resolve_distill_workers(cfg))
        self._live_monitor_pool = MonitorExecutor(
            max_workers=max(cfg.monitor.live_worker_max_parallel, 1),
        )
        self._content_monitor_pool = MonitorExecutor(
            max_workers=max(cfg.monitor.executor_max_parallel, 1),
        )
        self._live_loop: LiveTickLoop | None = None
        self._slow_loop: SlowTickLoop | None = None
        self._scheduler_loop: TaskSchedulerLoop | None = None

    def start(self, *, creator_id: str | None = None) -> None:
        if not self._cfg.monitor.reconciler_enabled:
            raise ReconcilerDisabledError()
        live_poll = live_poll_interval(self._cfg)
        log.info(
            "monitor_watch_daemon_started",
            live_poll=live_poll,
            vod_poll=vod_poll_interval_sec(self._cfg),
            archive_poll=bilibili_archive_poll_sec(self._cfg),
            dynamic_poll=bilibili_dynamic_poll_sec(self._cfg),
            post_process_poll=self._cfg.live.post_process_poll_interval_sec,
            monitor_executor_parallel=self._cfg.monitor.live_worker_max_parallel,
            content_executor_parallel=self._cfg.monitor.executor_max_parallel,
            scheduler_interval_sec=self._cfg.monitor.scheduler_interval_sec,
        )
        self._live_loop = LiveTickLoop(
            self._watcher,
            self._cfg,
            creator_id=creator_id,
            stop=self._stop,
            on_tick=self._on_live_tick,
        )
        self._scheduler_loop = TaskSchedulerLoop(
            self._cfg,
            self._watcher,
            live_pool=self._live_monitor_pool,
            content_pool=self._content_monitor_pool,
            post_pool=self._post_pool,
            segment_pool=self._segment_pool,
            stop=self._stop,
        )
        self._segment_watcher.start()
        self._slow_loop = SlowTickLoop(
            self._watcher,
            self._cfg,
            self._distill_pool,
            creator_id=creator_id,
            stop=self._stop,
        )
        self._live_loop.start()
        self._scheduler_loop.start()
        self._slow_loop.start()

    def stop(self) -> None:
        self._stop.set()
        if self._live_loop is not None:
            self._live_loop.join(timeout=5.0)
        if self._scheduler_loop is not None:
            self._scheduler_loop.join(timeout=5.0)
        if self._slow_loop is not None:
            self._slow_loop.join(timeout=5.0)
        self._segment_watcher.join(timeout=5.0)
        self._live_monitor_pool.shutdown(wait=False, cancel_futures=True)
        self._content_monitor_pool.shutdown(wait=False, cancel_futures=True)
        self._post_pool.shutdown(wait=False, cancel_futures=True)
        self._segment_pool.shutdown(wait=False, cancel_futures=True)
        set_segment_watcher(None)
        self._distill_pool.shutdown(wait=False, cancel_futures=True)

    def join(self, timeout: float | None = None) -> None:
        if self._live_loop is not None:
            self._live_loop.join(timeout=timeout)
        if self._scheduler_loop is not None:
            self._scheduler_loop.join(timeout=timeout)
        if self._slow_loop is not None:
            self._slow_loop.join(timeout=timeout)
