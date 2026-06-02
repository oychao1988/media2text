from __future__ import annotations

import time
from pathlib import Path

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.notify import NotifyService
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()
FIXTURE_ROOT = Path(__file__).parent / "fixtures"


class LiveWatcher:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._conn = open_db(cfg)
        self._creators = CreatorRepo(self._conn)
        self._sessions = LiveSessionRepo(self._conn)
        self._adapter = self._build_adapter()
        self._processes: dict = {}
        self._notify = NotifyService(cfg)
        self._core = LiveRecordingCore(
            cfg,
            conn=self._conn,
            adapter=self._adapter,
            platform="douyin",
            processes=self._processes,
            notify=self._notify,
        )

    def _build_adapter(self) -> DouyinAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return DouyinAdapterV1(client, session_path=session)
        return DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)

    def run_once(self, *, creator_id: str | None = None) -> dict:
        finalized = self._core.poll_active_recordings()
        started, started_ids, errors, auth_required, platform_changed = (
            self._core.scan_and_start(creator_id=creator_id)
        )
        if started_ids:
            finalized.extend(
                self._core.poll_active_recordings(skip_session_ids=started_ids)
            )
        stale = self._sessions.mark_stale_recordings_failed()
        if stale:
            log.warning("live_stale_sessions_cleared", count=stale)
        result: dict = {
            "started": started,
            "active": len(self._sessions.list_active()),
            "errors": errors,
            "auth_required": auth_required,
            "platform_changed": platform_changed,
        }
        if finalized:
            result["finalized"] = finalized
        return result

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        poll = (
            self._cfg.live.live_poll_interval_sec
            or self._cfg.monitor.live_poll_interval_sec
        )
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
