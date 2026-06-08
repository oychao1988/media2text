from __future__ import annotations

import time
from pathlib import Path

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
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
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
            platform="douyin",
            runtime=self._runtime,
            notify=self._notify,
        )

    def core_for_conn(self, conn) -> LiveRecordingCore:
        if conn is self._conn:
            return self._core
        return self._make_core(conn)

    def _build_adapter(self) -> DouyinAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return DouyinAdapterV1(client, session_path=session)
        return DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)

    def run_once(
        self,
        *,
        creator_id: str | None = None,
        conn=None,
        deadline: float | None = None,
    ) -> dict:
        work_conn = conn or self._conn
        core = self.core_for_conn(work_conn)
        sessions = LiveSessionRepo(work_conn)
        if deadline is not None and time.monotonic() >= deadline:
            return {"skipped": "budget_exhausted", "active": len(sessions.list_active())}

        core.poll_active_recordings()

        if deadline is not None and time.monotonic() >= deadline:
            return {
                "probe": True,
                "active": len(sessions.list_active()),
                "errors": [],
                "auth_required": False,
                "platform_changed": False,
            }

        errors, auth_required, platform_changed = core.probe_live(
            creator_id=creator_id,
            deadline=deadline,
        )
        stale = StateWriter(work_conn, cfg=self._cfg).mark_stale_recordings_failed()
        if stale:
            log.warning("live_stale_sessions_cleared", count=stale)
        return {
            "probe": True,
            "started": 0,
            "active": len(sessions.list_active()),
            "errors": errors,
            "auth_required": auth_required,
            "platform_changed": platform_changed,
        }

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
        return self._core.poll_active_recordings(skip_session_ids=skip_session_ids)

    def _finalize_recording(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        return self._core._finalize_recording(session_id, temp_path, pid)

    def _process_alive(self, pid: int) -> bool:
        return self._core._process_alive(pid)
