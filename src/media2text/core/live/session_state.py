"""Session lifecycle state machines (MH-4a)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.live.session_recovery import recover_active_sessions
from media2text.core.notify import NotifyService
from media2text.core.storage.models import LiveSessionRow
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.storage.write_gateway import DbWriteGateway, ensure_write_gateway_started

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()


@dataclass(frozen=True)
class SessionHandle:
    session_id: str
    creator_id: str
    platform: str


class SessionStateMachine:
    """Per-session poll/offline orchestration; DB via gateway, side effects via runtime."""

    def __init__(
        self,
        cfg: AppConfig,
        handle: SessionHandle,
        *,
        runtime: SessionRuntime,
        gateway: DbWriteGateway,
        watcher: MonitorWatcher,
        notify: NotifyService,
    ) -> None:
        self._cfg = cfg
        self._handle = handle
        self._runtime = runtime
        self._gateway = gateway
        self._watcher = watcher
        self._notify = notify

    @property
    def session_id(self) -> str:
        return self._handle.session_id

    def poll_observation(
        self,
        row: LiveSessionRow,
        creator,
        *,
        _conn: sqlite3.Connection | None = None,
    ) -> None:
        def _poll(conn: sqlite3.Connection) -> None:
            state = StateWriter(conn, cfg=self._cfg, notify=self._notify)
            core = self._watcher.core_for_platform(conn, self._handle.platform)
            core.poll_active_session(row, creator, state=state)

        if _conn is not None:
            _poll(_conn)
        else:
            self._gateway.write(_poll, label=f"session.poll_obs:{row.id[:8]}")

    def mark_offline_pending(self, offline_since: str) -> None:
        def _write(conn) -> None:
            state = StateWriter(conn, cfg=self._cfg, notify=self._notify)
            state.set_offline_since(
                self._handle.session_id,
                offline_since,
                creator_id=self._handle.creator_id,
            )

        self._gateway.write(_write, label="session.mark_offline_pending")

    def clear_offline_pending(self) -> None:
        def _write(conn) -> None:
            state = StateWriter(conn, cfg=self._cfg, notify=self._notify)
            state.clear_offline_since(
                self._handle.session_id,
                creator_id=self._handle.creator_id,
            )

        self._gateway.write(_write, label="session.clear_offline_pending")

    def transition_to_finalizing(self) -> None:
        def _write(conn) -> None:
            LiveSessionRepo(conn, cfg=self._cfg).update_status(
                self._handle.session_id,
                status="remuxing",
            )

        self._gateway.write(_write, label="session.transition_finalizing")

    def run_finalize(self) -> dict:
        def _finalize(conn) -> dict:
            from media2text.core.live.session_finalize import finalize_recording

            session = LiveSessionRepo(conn, cfg=self._cfg).get(self._handle.session_id)
            if not session:
                raise ValueError(f"session_not_found:{self._handle.session_id}")
            core = self._watcher.core_for_platform(conn, self._handle.platform)
            meta = finalize_recording(
                core,
                conn,
                session.id,
                session.temp_path,
                session.ffmpeg_pid or 0,
            )
            return {"finalized": meta} if meta else {}

        return self._gateway.write(_finalize, label="session.finalize")

    def run_reconnect_recording(self) -> dict:
        def _reconnect(conn) -> dict:
            core = self._watcher.core_for_platform(conn, self._handle.platform)
            return core.run_reconnect_recording(self._handle.session_id)

        return self._gateway.write(_reconnect, label="session.reconnect_rec")

    def run_start_streaming_stt(self) -> dict:
        def _start(conn) -> dict:
            core = self._watcher.core_for_platform(conn, self._handle.platform)
            return core.run_start_streaming_stt(self._handle.session_id)

        return self._gateway.write(_start, label="session.start_stt")

    def run_reconnect_streaming_stt(self) -> dict:
        def _reconnect(conn) -> dict:
            core = self._watcher.core_for_platform(conn, self._handle.platform)
            return core.run_reconnect_streaming_stt(self._handle.session_id)

        return self._gateway.write(_reconnect, label="session.reconnect_stt")


class SessionStateMachineRegistry:
    """In-process registry of active session machines."""

    def __init__(
        self,
        cfg: AppConfig,
        *,
        runtime: SessionRuntime,
        gateway: DbWriteGateway,
        watcher: MonitorWatcher,
        notify: NotifyService | None = None,
    ) -> None:
        self._cfg = cfg
        self._runtime = runtime
        self._gateway = gateway
        self._watcher = watcher
        self._notify = notify or NotifyService(cfg)
        self._machines: dict[str, SessionStateMachine] = {}

    def get(self, session_id: str) -> SessionStateMachine | None:
        return self._machines.get(session_id)

    def drop(self, session_id: str) -> None:
        self._machines.pop(session_id, None)

    def get_or_create(
        self,
        row: LiveSessionRow,
        *,
        platform: str,
    ) -> SessionStateMachine:
        existing = self._machines.get(row.id)
        if existing is not None:
            return existing
        handle = SessionHandle(
            session_id=row.id,
            creator_id=row.creator_id,
            platform=platform,
        )
        machine = SessionStateMachine(
            self._cfg,
            handle,
            runtime=self._runtime,
            gateway=self._gateway,
            watcher=self._watcher,
            notify=self._notify,
        )
        self._machines[row.id] = machine
        return machine

    def poll_active_for_platform(
        self,
        platform: str,
        *,
        skip_session_ids: set[str] | None = None,
    ) -> None:
        skip = skip_session_ids or set()

        def _poll(conn) -> None:
            sessions = LiveSessionRepo(conn, cfg=self._cfg)
            creators = CreatorRepo(conn)
            for row in sessions.list_active():
                if row.id in skip:
                    continue
                if row.status != "recording" or row.ffmpeg_pid is None:
                    continue
                creator = creators.get(row.creator_id)
                if not creator or creator.platform != platform:
                    continue
                machine = self.get_or_create(row, platform=platform)
                machine.poll_observation(row, creator, _conn=conn)

        self._gateway.write(_poll, label=f"registry.poll_active:{platform}")

    def recover_all(self) -> int:
        """Daemon-start recovery: offline+dead ffmpeg → finalize; then reconcile."""

        return self._gateway.write(
            lambda conn: recover_active_sessions(self._cfg, conn),
            label="registry.recover_all",
        )

    def run_prepare(self, creator_id: str, *, live_info) -> dict:
        def _prepare(conn) -> dict:
            creator = CreatorRepo(conn).get(creator_id)
            if not creator:
                raise ValueError(f"creator_not_found:{creator_id}")
            core = self._watcher.core_for_platform(conn, creator.platform)
            return core.run_prepare_live_recording(creator_id, live_info=live_info)

        return self._gateway.write(_prepare, label="registry.prepare")

    def _machine_for_session(self, session_id: str) -> SessionStateMachine:
        def _load(conn):
            row = LiveSessionRepo(conn, cfg=self._cfg).get(session_id)
            if not row:
                raise ValueError(f"session_not_found:{session_id}")
            creator = CreatorRepo(conn).get(row.creator_id)
            if not creator:
                raise ValueError(f"creator_not_found:{row.creator_id}")
            return row, creator.platform

        row, platform = self._gateway.read(_load)
        return self.get_or_create(row, platform=platform)

    def run_finalize(self, session_id: str) -> dict:
        return self._machine_for_session(session_id).run_finalize()

    def run_reconnect_recording(self, session_id: str) -> dict:
        return self._machine_for_session(session_id).run_reconnect_recording()

    def run_start_streaming_stt(self, session_id: str) -> dict:
        return self._machine_for_session(session_id).run_start_streaming_stt()

    def run_reconnect_streaming_stt(self, session_id: str) -> dict:
        return self._machine_for_session(session_id).run_reconnect_streaming_stt()

    def bootstrap_streaming_stt(self) -> int:
        """Reconnect STT after daemon restart (empty SessionRuntime)."""
        if not self._cfg.live.streaming_stt.enabled:
            return 0

        def _bootstrap(conn) -> int:
            from media2text.core.live.task_reconciler import _is_streaming_session, _pid_alive

            recovered = 0
            sessions = LiveSessionRepo(conn, cfg=self._cfg)
            creators = CreatorRepo(conn)
            for row in sessions.list_active():
                if row.status != "recording" or not _pid_alive(row.ffmpeg_pid):
                    continue
                if not _is_streaming_session(self._cfg, row):
                    continue
                creator = creators.get(row.creator_id)
                if not creator:
                    continue
                core = self._watcher.core_for_platform(conn, creator.platform)
                stt = core._stt_sessions.get(row.id)
                if stt is not None and stt.is_alive():
                    continue
                try:
                    result = core.run_reconnect_streaming_stt(row.id)
                    if result.get("skipped"):
                        continue
                    recovered += 1
                    log.info(
                        "bootstrap_streaming_stt_recovered",
                        session_id=row.id,
                        creator_id=creator.id,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "bootstrap_streaming_stt_failed",
                        session_id=row.id,
                        error=str(exc),
                    )
            return recovered

        return self._gateway.write(_bootstrap, label="registry.bootstrap_stt")


def build_registry(watcher: MonitorWatcher) -> SessionStateMachineRegistry:
    cfg = watcher._cfg
    ensure_write_gateway_started(cfg)
    from media2text.core.storage.write_gateway import get_write_gateway

    return SessionStateMachineRegistry(
        cfg,
        runtime=watcher._session_runtime,
        gateway=get_write_gateway(cfg),
        watcher=watcher,
        notify=watcher._notify,
    )
