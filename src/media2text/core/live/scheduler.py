from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.live.post_process_pool import PostProcessExecutor, resolve_post_process_workers

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()


def _bilibili_archive_poll_sec(cfg: AppConfig) -> int:
    return cfg.platforms.bilibili.archive_poll_interval_sec


def _live_poll_interval(cfg: AppConfig) -> int:
    return cfg.live.live_poll_interval_sec or cfg.monitor.live_poll_interval_sec


class LiveTickLoop:
    """Dedicated thread: douyin + bilibili run_once and non-blocking post-process drain."""

    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        post_pool: PostProcessExecutor,
        monitor_pool: MonitorExecutor,
        *,
        creator_id: str | None,
        stop: threading.Event,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._post_pool = post_pool
        self._monitor_pool = monitor_pool
        self._creator_id = creator_id
        self._stop = stop
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="live-tick",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        live_poll = _live_poll_interval(self._cfg)
        last_post = 0.0
        while not self._stop.is_set():
            self._watcher._douyin_live.run_once(creator_id=self._creator_id)
            self._watcher._bilibili_live.run_once(creator_id=self._creator_id)
            finalized = self._monitor_pool.drain_priority_zero(
                self._cfg,
                self._watcher._conn,
                notify=self._watcher._notify,
                watcher=self._watcher,
            )
            if finalized:
                log.info("monitor_finalize_drained", count=len(finalized))
            now = time.time()
            if now - last_post >= self._cfg.live.post_process_poll_interval_sec:
                self._post_pool.drain_pending(
                    self._cfg,
                    self._watcher._conn,
                    notify=self._watcher._notify,
                    limit=self._cfg.live.post_process_max_parallel,
                )
                last_post = now
            self._stop.wait(timeout=live_poll)


class SlowTickLoop:
    """Dedicated thread: VOD, archive, and dynamic ticks on their intervals."""

    def __init__(
        self,
        watcher: MonitorWatcher,
        cfg: AppConfig,
        monitor_pool: MonitorExecutor,
        *,
        creator_id: str | None,
        stop: threading.Event,
    ) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._monitor_pool = monitor_pool
        self._creator_id = creator_id
        self._stop = stop
        self._thread: threading.Thread | None = None

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
        bcfg = self._cfg.platforms.bilibili
        archive_poll = _bilibili_archive_poll_sec(self._cfg)
        dynamic_poll = bcfg.dynamic_poll_interval_sec
        last_vod = 0.0
        last_archive = 0.0
        last_dynamic = 0.0
        while not self._stop.is_set():
            now = time.time()
            if now - last_vod >= self._cfg.monitor.vod_poll_interval_sec:
                self._watcher._run_vod_tick(creator_id=self._creator_id)
                last_vod = now
            if now - last_archive >= archive_poll:
                self._watcher._run_archive_tick(creator_id=self._creator_id)
                last_archive = now
            if now - last_dynamic >= dynamic_poll:
                self._watcher._run_dynamic_tick(creator_id=self._creator_id)
                last_dynamic = now
            self._monitor_pool.drain_pending(
                self._cfg,
                self._watcher._conn,
                notify=self._watcher._notify,
                watcher=self._watcher,
                limit=self._cfg.monitor.executor_max_parallel,
            )
            self._stop.wait(timeout=1.0)


class MonitorScheduler:
    def __init__(self, watcher: MonitorWatcher, cfg: AppConfig) -> None:
        self._watcher = watcher
        self._cfg = cfg
        self._stop = threading.Event()
        max_workers = resolve_post_process_workers(cfg)
        self._post_pool = PostProcessExecutor(max_workers=max_workers)
        self._monitor_pool = MonitorExecutor(max_workers=cfg.monitor.executor_max_parallel)
        self._live_loop: LiveTickLoop | None = None
        self._slow_loop: SlowTickLoop | None = None

    def start(self, *, creator_id: str | None = None) -> None:
        live_poll = _live_poll_interval(self._cfg)
        bcfg = self._cfg.platforms.bilibili
        log.info(
            "monitor_watch_daemon_started",
            live_poll=live_poll,
            vod_poll=self._cfg.monitor.vod_poll_interval_sec,
            archive_poll=_bilibili_archive_poll_sec(self._cfg),
            dynamic_poll=bcfg.dynamic_poll_interval_sec,
            post_process_poll=self._cfg.live.post_process_poll_interval_sec,
            monitor_executor_parallel=self._cfg.monitor.executor_max_parallel,
        )
        self._live_loop = LiveTickLoop(
            self._watcher,
            self._cfg,
            self._post_pool,
            self._monitor_pool,
            creator_id=creator_id,
            stop=self._stop,
        )
        self._slow_loop = SlowTickLoop(
            self._watcher,
            self._cfg,
            self._monitor_pool,
            creator_id=creator_id,
            stop=self._stop,
        )
        self._live_loop.start()
        self._slow_loop.start()

    def stop(self) -> None:
        self._stop.set()
        if self._live_loop is not None:
            self._live_loop.join(timeout=5.0)
        if self._slow_loop is not None:
            self._slow_loop.join(timeout=5.0)
        self._monitor_pool.shutdown(wait=True)
        self._post_pool.shutdown(wait=True)
