from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from media2text.core.config import AppConfig
from media2text.core.ffmpeg import record_stream_copy, remux_to_mp4, stop_process
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()
FIXTURE_ROOT = Path(__file__).parent / "fixtures"
# Ignore brief offline glitches right after ffmpeg starts.
MIN_RECORDING_SEC_BEFORE_OFFLINE_END = 45
FFMPEG_STARTUP_GRACE_SEC = 2


class LiveWatcher:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._conn = open_db(cfg)
        self._creators = CreatorRepo(self._conn)
        self._sessions = LiveSessionRepo(self._conn)
        self._adapter = self._build_adapter()
        self._processes: dict[str, object] = {}

    def _build_adapter(self) -> DouyinAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return DouyinAdapterV1(client, session_path=session)
        return DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)

    def run_once(self, *, creator_id: str | None = None) -> dict:
        stale = self._sessions.mark_stale_recordings_failed()
        if stale:
            log.warning("live_stale_sessions_cleared", count=stale)

        targets = self._creators.list_live_watched()
        if creator_id:
            row = self._creators.get(creator_id)
            targets = [row] if row else []
        started = []
        started_session_ids: set[str] = set()
        for creator in targets:
            if self._sessions.get_active_for_creator(creator.id):
                continue
            live_info = self._adapter.get_live_room(sec_uid=creator.sec_uid)
            if not live_info.is_live or not live_info.room_id:
                continue
            room_id = live_info.room_id
            stream_url = live_info.stream_flv_url
            if not stream_url:
                try:
                    stream_url = self._adapter.resolve_stream_url(
                        room_id=room_id,
                        sec_uid=creator.sec_uid,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "live_stream_url_resolve_failed",
                        creator_id=creator.id,
                        room_id=room_id,
                        error=str(exc),
                    )
                    continue
            meta = self._start_recording(creator.id, creator.sec_uid, room_id, stream_url)
            started.append(meta)
            started_session_ids.add(meta["session_id"])
        self._poll_active_recordings(skip_session_ids=started_session_ids)
        return {"started": started, "active": len(self._sessions.list_active())}

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        lock = self._ws / ".live-watch.lock"
        try:
            with workspace_lock(lock):
                stale = self._sessions.mark_stale_recordings_failed()
                if stale:
                    log.warning("live_stale_sessions_cleared", count=stale)
                log.info("live_watch_daemon_started", poll=self._cfg.platforms.douyin.poll_interval_sec)
                while True:
                    self.run_once(creator_id=creator_id)
                    time.sleep(self._cfg.platforms.douyin.poll_interval_sec)
        except LockError:
            log.error("live_watch_lock_held")
            raise

    def _start_recording(
        self,
        creator_id: str,
        sec_uid: str,
        room_id: str | None,
        stream_url: str,
    ) -> dict:
        live_dir = self._ws / "creators" / sec_uid / "live"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        temp_path = live_dir / f"{stamp}.flv"
        proc = record_stream_copy(
            ffmpeg=self._cfg.live.ffmpeg_path,
            stream_url=stream_url,
            output_path=temp_path,
        )
        session_id = self._sessions.create(
            creator_id=creator_id,
            room_id=room_id,
            temp_path=str(temp_path),
            ffmpeg_pid=proc.pid,
        )
        self._processes[session_id] = proc
        time.sleep(FFMPEG_STARTUP_GRACE_SEC)
        exit_code = proc.poll()
        if exit_code is not None:
            err_tail = ""
            if proc.stderr is not None:
                err_tail = proc.stderr.read().decode(errors="replace")[-500:]
            self._sessions.update_status(
                session_id,
                status="failed",
                error=f"ffmpeg_exited_early:{exit_code}:{err_tail}",
                ended=True,
            )
            self._processes.pop(session_id, None)
            log.error(
                "live_recording_ffmpeg_died",
                session_id=session_id,
                exit_code=exit_code,
            )
            return {"session_id": session_id, "temp_path": str(temp_path), "pid": proc.pid}

        log.info("live_recording_started", session_id=session_id, temp_path=str(temp_path))
        return {"session_id": session_id, "temp_path": str(temp_path), "pid": proc.pid}

    def _poll_active_recordings(self, *, skip_session_ids: set[str] | None = None) -> None:
        skip = skip_session_ids or set()
        for row in self._sessions.list_active():
            if row.id in skip:
                continue
            if row.status != "recording" or row.ffmpeg_pid is None:
                continue
            creator = self._creators.get(row.creator_id)
            if not creator:
                continue
            pid = row.ffmpeg_pid
            alive = self._process_alive(pid)
            if not alive:
                self._finalize_recording(row.id, row.temp_path, pid)
                continue

            try:
                still_live = self._adapter.get_live_room(sec_uid=creator.sec_uid).is_live
            except Exception as exc:  # noqa: BLE001
                log.warning("live_status_check_failed", creator_id=creator.id, error=str(exc))
                continue

            if still_live:
                continue

            if self._recording_age_sec(row.started_at) < MIN_RECORDING_SEC_BEFORE_OFFLINE_END:
                continue

            self._finalize_recording(row.id, row.temp_path, pid)

    def _recording_age_sec(self, started_at: str) -> float:
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return MIN_RECORDING_SEC_BEFORE_OFFLINE_END
        return (datetime.now(timezone.utc) - started).total_seconds()

    def _process_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _finalize_recording(self, session_id: str, temp_path: str | None, pid: int) -> None:
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif self._process_alive(pid):
            os.kill(pid, 15)

        if not temp_path:
            self._sessions.update_status(session_id, status="failed", error="missing temp_path", ended=True)
            return

        temp = Path(temp_path)
        if not temp.is_file() or temp.stat().st_size == 0:
            self._sessions.update_status(
                session_id,
                status="failed",
                error="empty_recording",
                ended=True,
            )
            log.warning("live_recording_empty", session_id=session_id, temp_path=str(temp))
            return

        mp4 = temp.with_suffix(".mp4")
        self._sessions.update_status(session_id, status="remuxing")
        try:
            remux_to_mp4(ffmpeg=self._cfg.live.ffmpeg_path, src=temp, dst=mp4)
            temp.unlink(missing_ok=True)
            self._sessions.update_status(
                session_id,
                status="completed",
                local_path=str(mp4),
                ended=True,
            )
            self._sessions.clear_pid(session_id)
            log.info("live_recording_completed", session_id=session_id, path=str(mp4))
        except Exception as exc:  # noqa: BLE001
            self._sessions.update_status(
                session_id,
                status="failed",
                error=str(exc),
                ended=True,
            )
            log.exception("live_recording_failed", session_id=session_id)
