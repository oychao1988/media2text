from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from subprocess import Popen

import structlog

from media2text.core.archive.hook import index_transcript_safe
from media2text.core.cloud.live_upload import maybe_upload_live_to_aliyundrive
from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, PlatformChanged
from media2text.core.ffmpeg import record_stream_copy, remux_to_mp4, stop_process
from media2text.core.manifest import refresh_manifest
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.auth import session_path
from media2text.core.platform.bilibili.httpx_client import client_from_storage
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.transcribe.whisper import write_transcript_outputs
from media2text.core.workspace import open_db

log = structlog.get_logger()
PLATFORM = "bilibili"
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
        self._processes: dict[str, Popen] = {}
        self._notify = NotifyService(cfg)

    def _build_adapter(self) -> BilibiliAdapterV1:
        session = session_path(self._ws)
        if session.is_file():
            client = client_from_storage(session)
            return BilibiliAdapterV1(client, session_path=session)
        return BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)

    def _monitored_targets(self, *, creator_id: str | None) -> list:
        targets = [c for c in self._creators.list_monitored() if c.platform == PLATFORM]
        if creator_id:
            row = self._creators.get(creator_id)
            if row and row.platform == PLATFORM:
                return [row]
            return []
        return targets

    def run_once(self, *, creator_id: str | None = None) -> dict:
        stale = self._sessions.mark_stale_recordings_failed()
        if stale:
            log.warning("bilibili_live_stale_sessions_cleared", count=stale)

        targets = self._monitored_targets(creator_id=creator_id)
        started: list[dict] = []
        started_session_ids: set[str] = set()
        auth_required = False
        platform_changed = False
        errors: list[dict] = []

        for creator in targets:
            if self._sessions.get_active_for_creator(creator.id):
                continue
            try:
                live_info = self._adapter.get_live_room(sec_uid=creator.sec_uid)
            except AuthRequired as exc:
                auth_required = True
                errors.append(
                    {"creator_id": creator.id, "error": str(exc), "auth_required": True}
                )
                continue
            except PlatformChanged as exc:
                platform_changed = True
                errors.append(
                    {"creator_id": creator.id, "error": str(exc), "platform_changed": True}
                )
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append({"creator_id": creator.id, "error": str(exc)})
                continue

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
                except AuthRequired as exc:
                    auth_required = True
                    errors.append(
                        {"creator_id": creator.id, "error": str(exc), "auth_required": True}
                    )
                    continue
                except PlatformChanged as exc:
                    platform_changed = True
                    errors.append(
                        {
                            "creator_id": creator.id,
                            "error": str(exc),
                            "platform_changed": True,
                        }
                    )
                    continue
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "bilibili_live_stream_url_resolve_failed",
                        creator_id=creator.id,
                        room_id=room_id,
                        error=str(exc),
                    )
                    errors.append({"creator_id": creator.id, "error": str(exc)})
                    continue
            meta = self._start_recording(creator.id, creator.sec_uid, room_id, stream_url)
            started.append(meta)
            started_session_ids.add(meta["session_id"])

        finalized = self._poll_active_recordings(skip_session_ids=started_session_ids)
        result: dict = {
            "platform": PLATFORM,
            "checked": len(targets),
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
        bcfg = self._cfg.platforms.bilibili
        poll = bcfg.live_poll_interval_sec or self._cfg.monitor.live_poll_interval_sec
        lock = self._ws / ".monitor-watch.lock"
        try:
            with workspace_lock(lock):
                stale = self._sessions.mark_stale_recordings_failed()
                if stale:
                    log.warning("bilibili_live_stale_sessions_cleared", count=stale)
                log.info("bilibili_live_watch_daemon_started", poll=poll)
                while True:
                    self.run_once(creator_id=creator_id)
                    time.sleep(poll)
        except LockError:
            log.error("bilibili_live_watch_lock_held")
            raise

    def _start_recording(
        self,
        creator_id: str,
        sec_uid: str,
        room_id: str | None,
        stream_url: str,
    ) -> dict:
        live_dir = self._ws / "creators" / sec_uid / "live"
        live_dir.mkdir(parents=True, exist_ok=True)
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
                "bilibili_live_recording_ffmpeg_died",
                session_id=session_id,
                exit_code=exit_code,
            )
            return {"session_id": session_id, "temp_path": str(temp_path), "pid": proc.pid}

        log.info(
            "bilibili_live_recording_started",
            session_id=session_id,
            temp_path=str(temp_path),
        )
        creator = self._creators.get(creator_id)
        if creator:
            label = creator_label(creator)
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.LIVE_STARTED,
                    title=label,
                    body=f"检测到 B 站开播，已开始录制\nroom_id: {room_id or '—'}\n文件: {temp_path.name}",
                )
            )
        return {"session_id": session_id, "temp_path": str(temp_path), "pid": proc.pid}

    def _poll_active_recordings(self, *, skip_session_ids: set[str] | None = None) -> list[dict]:
        skip = skip_session_ids or set()
        finalized: list[dict] = []
        for row in self._sessions.list_active():
            if row.id in skip:
                continue
            if row.status != "recording" or row.ffmpeg_pid is None:
                continue
            creator = self._creators.get(row.creator_id)
            if not creator or creator.platform != PLATFORM:
                continue
            pid = row.ffmpeg_pid
            alive = self._process_alive(pid)
            if not alive:
                meta = self._finalize_recording(row.id, row.temp_path, pid)
                if meta:
                    finalized.append(meta)
                continue

            try:
                still_live = self._adapter.get_live_room(sec_uid=creator.sec_uid).is_live
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "bilibili_live_status_check_failed",
                    creator_id=creator.id,
                    error=str(exc),
                )
                continue

            if still_live:
                continue

            if self._recording_age_sec(row.started_at) < MIN_RECORDING_SEC_BEFORE_OFFLINE_END:
                continue

            meta = self._finalize_recording(row.id, row.temp_path, pid)
            if meta:
                finalized.append(meta)
        return finalized

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

    def _finalize_recording(self, session_id: str, temp_path: str | None, pid: int) -> dict | None:
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif self._process_alive(pid):
            os.kill(pid, 15)

        if not temp_path:
            self._sessions.update_status(
                session_id, status="failed", error="missing temp_path", ended=True
            )
            return None

        temp = Path(temp_path)
        if not temp.is_file() or temp.stat().st_size == 0:
            self._sessions.update_status(
                session_id,
                status="failed",
                error="empty_recording",
                ended=True,
            )
            log.warning(
                "bilibili_live_recording_empty",
                session_id=session_id,
                temp_path=str(temp),
            )
            return None

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
            log.info("bilibili_live_recording_completed", session_id=session_id, path=str(mp4))
        except Exception as exc:  # noqa: BLE001
            self._sessions.update_status(
                session_id,
                status="failed",
                error=str(exc),
                ended=True,
            )
            log.exception("bilibili_live_recording_failed", session_id=session_id)
            return None

        session = self._sessions.get(session_id)
        if not session:
            return None
        creator = self._creators.get(session.creator_id)
        if not creator:
            return {"session_id": session_id, "path": str(mp4)}

        refresh_manifest(
            self._conn,
            sec_uid=creator.sec_uid,
            workspace=self._ws,
            platform=creator.platform,
        )
        label = creator_label(creator)
        self._notify.emit(
            NotifyEvent(
                kind=EventKind.RECORDING_COMPLETED,
                title=label,
                body=f"B 站直播录制已完成\n{mp4.name}\n{mp4.parent}",
            )
        )
        transcribe_meta = self._maybe_transcribe_completed(mp4, creator_label=label)
        if transcribe_meta.get("transcribed"):
            refresh_manifest(
                self._conn,
                sec_uid=creator.sec_uid,
                workspace=self._ws,
                platform=creator.platform,
            )

        upload_meta = maybe_upload_live_to_aliyundrive(
            self._cfg,
            self._conn,
            session_id=session_id,
            mp4=mp4,
            creator=creator,
            transcribe_meta=transcribe_meta,
            notify=self._notify,
        )
        if upload_meta:
            refresh_manifest(
                self._conn,
                sec_uid=creator.sec_uid,
                workspace=self._ws,
                platform=creator.platform,
            )

        return {
            "session_id": session_id,
            "path": str(mp4),
            "creator_id": creator.id,
            **transcribe_meta,
            **upload_meta,
        }

    def _maybe_transcribe_completed(self, mp4: Path, *, creator_label: str = "") -> dict:
        if not self._cfg.live.transcribe_on_complete:
            return {}

        from media2text.core.transcribe.errors import TranscribeConfigError
        from media2text.core.transcribe.factory import (
            create_transcribe_backend,
            transcribe_engine_available,
        )

        available, reason = transcribe_engine_available(self._cfg)
        if not available:
            log.warning(
                "bilibili_live_transcribe_skipped",
                path=str(mp4),
                reason=reason or "transcribe_unavailable",
                engine=self._cfg.transcribe.engine,
            )
            return {"transcribe_skipped": True, "transcribe_skip_reason": reason}

        try:
            backend = create_transcribe_backend(self._cfg)
        except TranscribeConfigError as exc:
            log.warning(
                "bilibili_live_transcribe_skipped",
                path=str(mp4),
                reason=str(exc),
                engine=self._cfg.transcribe.engine,
            )
            return {"transcribe_skipped": True, "transcribe_skip_reason": str(exc)}

        try:
            result = backend.transcribe(mp4, language=self._cfg.transcribe.language)
            json_path, _md = write_transcript_outputs(mp4, result)
            index_transcript_safe(self._cfg, json_path)
            log.info("bilibili_live_transcribe_completed", path=str(mp4), engine=result.engine)
            title = creator_label or mp4.parent.parent.name
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.TRANSCRIBE_COMPLETED,
                    title=title,
                    body=f"B 站直播转录完成（{result.engine}）\n{mp4.name}",
                )
            )
            return {"transcribed": True, "transcribe_engine": result.engine}
        except Exception as exc:  # noqa: BLE001
            log.exception("bilibili_live_transcribe_failed", path=str(mp4), error=str(exc))
            return {"transcribe_error": str(exc)}
