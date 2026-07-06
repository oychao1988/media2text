from __future__ import annotations

import time

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.state_writer import StateWriter
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import NotifyService
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.auth import session_path
from media2text.core.platform.bilibili.httpx_client import client_from_storage
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, gateway_write
from media2text.core.workspace import open_db

log = structlog.get_logger()
PLATFORM = "bilibili"


class LiveWatcher:
    def __init__(
        self,
        cfg: AppConfig,
        *,
        runtime: SessionRuntime | None = None,
    ) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._adapter = self._build_adapter()
        self._runtime = runtime or SessionRuntime()
        self._notify = NotifyService(cfg)

    def _make_core(self, conn) -> LiveRecordingCore:
        return LiveRecordingCore(
            self._cfg,
            conn=conn,
            adapter=self._adapter,
            platform=PLATFORM,
            runtime=self._runtime,
            notify=self._notify,
        )

    def core_for_conn(self, conn) -> LiveRecordingCore:
        return self._make_core(conn)

    def _build_adapter(self) -> BilibiliAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return BilibiliAdapterV1(client, session_path=session)
        return BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)

    def run_poll_active(
        self,
        *,
        creator_id: str | None = None,
        deadline: float | None = None,
    ) -> dict:
        def _poll(conn) -> dict:
            core = self.core_for_conn(conn)
            creators = CreatorRepo(conn, cfg=self._cfg)
            sessions = LiveSessionRepo(conn, cfg=self._cfg)
            targets = [c for c in creators.list_monitored() if c.platform == PLATFORM]
            if creator_id:
                row = creators.get(creator_id)
                targets = [row] if row and row.platform == PLATFORM else []
            if deadline is not None and time.monotonic() >= deadline:
                return {
                    "platform": PLATFORM,
                    "skipped": "budget_exhausted",
                    "checked": len(targets),
                    "active": len(sessions.list_active()),
                }
            core.poll_active_recordings()
            return {
                "platform": PLATFORM,
                "checked": len(targets),
                "active": len(sessions.list_active()),
            }

        ensure_write_gateway_started(self._cfg)
        return gateway_write(self._cfg, _poll, label="bilibili.poll_active")

    def run_probe_observe(
        self,
        *,
        creator_id: str | None = None,
        deadline: float | None = None,
        conn=None,
    ) -> dict:
        work_conn = conn or open_db(self._cfg)
        close = conn is None
        try:
            core = self.core_for_conn(work_conn)
            creators = CreatorRepo(work_conn)
            targets = [c for c in creators.list_monitored() if c.platform == PLATFORM]
            if creator_id:
                row = creators.get(creator_id)
                targets = [row] if row and row.platform == PLATFORM else []
            errors, auth_required, platform_changed = core.probe_live(
                creator_id=creator_id,
                deadline=deadline,
            )
            return {
                "platform": PLATFORM,
                "probe": True,
                "checked": len(targets),
                "started": 0,
                "errors": errors,
                "auth_required": auth_required,
                "platform_changed": platform_changed,
            }
        finally:
            if close:
                work_conn.close()

    def run_finalize(self) -> dict:
        def _finalize(conn) -> dict:
            stale = StateWriter(conn, cfg=self._cfg).mark_stale_recordings_failed()
            if stale:
                log.warning("bilibili_live_stale_sessions_cleared", count=stale)
            return {
                "platform": PLATFORM,
                "active": len(LiveSessionRepo(conn, cfg=self._cfg).list_active()),
                "stale_cleared": stale,
            }

        ensure_write_gateway_started(self._cfg)
        return gateway_write(self._cfg, _finalize, label="bilibili.finalize")

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        bcfg = self._cfg.platforms.bilibili
        poll = (
            self._cfg.live.live_poll_interval_sec
            or bcfg.live_poll_interval_sec
            or self._cfg.monitor.live_poll_interval_sec
        )
        lock = self._ws / ".monitor-watch.lock"
        try:
            with workspace_lock(lock):
                log.info("bilibili_live_watch_daemon_started", poll=poll)
                while True:
                    poll_result = self.run_poll_active(creator_id=creator_id)
                    if not poll_result.get("skipped"):
                        self.run_probe_observe(creator_id=creator_id)
                        self.run_finalize()
                    time.sleep(poll)
        except LockError:
            log.error("bilibili_live_watch_lock_held")
            raise

    def _process_alive(self, pid: int) -> bool:
        conn = open_db(self._cfg)
        try:
            return self.core_for_conn(conn)._process_alive(pid)
        finally:
            conn.close()
