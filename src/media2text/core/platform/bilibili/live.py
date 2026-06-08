from __future__ import annotations

import time

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import NotifyService
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.auth import session_path
from media2text.core.platform.bilibili.httpx_client import client_from_storage
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
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
        self._conn = open_db(cfg)
        self._creators = CreatorRepo(self._conn)
        self._sessions = LiveSessionRepo(self._conn)
        self._adapter = self._build_adapter()
        self._runtime = runtime or SessionRuntime()
        self._notify = NotifyService(cfg)
        self._core = self._make_core(self._conn)

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
        if conn is self._conn:
            return self._core
        return self._make_core(conn)

    def _build_adapter(self) -> BilibiliAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return BilibiliAdapterV1(client, session_path=session)
        return BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)

    def run_once(
        self,
        *,
        creator_id: str | None = None,
        conn=None,
        deadline: float | None = None,
    ) -> dict:
        work_conn = conn or self._conn
        core = self.core_for_conn(work_conn)
        creators = CreatorRepo(work_conn)
        sessions = LiveSessionRepo(work_conn)
        targets = [
            c for c in creators.list_monitored() if c.platform == PLATFORM
        ]
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

        errors, auth_required, platform_changed = core.probe_live(
            creator_id=creator_id,
            deadline=deadline,
        )
        stale = sessions.mark_stale_recordings_failed()
        if stale:
            log.warning("bilibili_live_stale_sessions_cleared", count=stale)
        return {
            "platform": PLATFORM,
            "probe": True,
            "checked": len(targets),
            "started": 0,
            "active": len(sessions.list_active()),
            "errors": errors,
            "auth_required": auth_required,
            "platform_changed": platform_changed,
        }

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
                    self.run_once(creator_id=creator_id)
                    time.sleep(poll)
        except LockError:
            log.error("bilibili_live_watch_lock_held")
            raise

    def _process_alive(self, pid: int) -> bool:
        return self._core._process_alive(pid)
