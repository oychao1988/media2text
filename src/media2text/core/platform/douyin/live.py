from __future__ import annotations

import time
from pathlib import Path

import httpx
import structlog

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.state_writer import StateWriter
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import NotifyService
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.db import with_db_lock_retry
from media2text.core.storage.repos import LiveSessionRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()
FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def live_poll_interval_sec(cfg: AppConfig) -> int:
    dcfg = cfg.platforms.douyin
    return (
        dcfg.live_poll_interval_sec
        or cfg.live.live_poll_interval_sec
        or cfg.monitor.live_poll_interval_sec
    )


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
            platform="douyin",
            runtime=self._runtime,
            notify=self._notify,
        )

    def core_for_conn(self, conn) -> LiveRecordingCore:
        return self._make_core(conn)

    def _build_adapter(self) -> DouyinAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return DouyinAdapterV1(client, session_path=session)
        return DouyinAdapterV1(httpx.Client(), session_path=None)

    def run_poll_active(
        self,
        *,
        conn,
        creator_id: str | None = None,
        deadline: float | None = None,
    ) -> dict:
        def _poll() -> dict:
            work_conn = conn
            core = self.core_for_conn(work_conn)
            sessions = LiveSessionRepo(work_conn)
            if deadline is not None and time.monotonic() >= deadline:
                return {"skipped": "budget_exhausted", "active": len(sessions.list_active())}
            core.poll_active_recordings()
            return {"active": len(sessions.list_active())}

        return with_db_lock_retry(_poll)

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
            errors, auth_required, platform_changed = core.probe_live(
                creator_id=creator_id,
                deadline=deadline,
            )
            return {
                "probe": True,
                "started": 0,
                "errors": errors,
                "auth_required": auth_required,
                "platform_changed": platform_changed,
            }
        finally:
            if close:
                work_conn.close()

    def run_finalize(self, *, conn) -> dict:
        def _finalize() -> dict:
            stale = StateWriter(conn, cfg=self._cfg).mark_stale_recordings_failed()
            if stale:
                log.warning("live_stale_sessions_cleared", count=stale)
            return {
                "active": len(LiveSessionRepo(conn).list_active()),
                "stale_cleared": stale,
            }

        return with_db_lock_retry(_finalize)

    def run_once(
        self,
        *,
        creator_id: str | None = None,
        conn=None,
        deadline: float | None = None,
    ) -> dict:
        work_conn = conn or open_db(self._cfg)
        close = conn is None
        try:
            poll = self.run_poll_active(
                conn=work_conn, creator_id=creator_id, deadline=deadline
            )
            if poll.get("skipped"):
                return poll
            observe = self.run_probe_observe(
                creator_id=creator_id, deadline=deadline, conn=work_conn
            )
            finalize = self.run_finalize(conn=work_conn)
            return {
                **poll,
                **observe,
                **finalize,
            }
        finally:
            if close:
                work_conn.close()

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        poll = live_poll_interval_sec(self._cfg)
        lock = self._ws / ".monitor-watch.lock"
        try:
            with workspace_lock(lock):
                log.info("live_watch_daemon_started", poll=poll)
                while True:
                    self.run_once(creator_id=creator_id)
                    time.sleep(poll)
        except LockError:
            log.error("live_watch_lock_held")
            raise

    def _poll_active_recordings(self, *, skip_session_ids: set[str] | None = None) -> list[dict]:
        conn = open_db(self._cfg)
        try:
            return self.core_for_conn(conn).poll_active_recordings(
                skip_session_ids=skip_session_ids
            )
        finally:
            conn.close()

    def _finalize_recording(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        conn = open_db(self._cfg)
        try:
            return self.core_for_conn(conn)._finalize_recording(session_id, temp_path, pid)
        finally:
            conn.close()

    def _process_alive(self, pid: int) -> bool:
        conn = open_db(self._cfg)
        try:
            return self.core_for_conn(conn)._process_alive(pid)
        finally:
            conn.close()
