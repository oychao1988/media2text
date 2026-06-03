from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from subprocess import Popen

from concurrent.futures import ThreadPoolExecutor, as_completed

import structlog

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, PlatformChanged
from media2text.core.archive.hook import index_transcript_safe
from media2text.core.ffmpeg import concat_to_mp4, record_stream_copy, remux_to_mp4, stop_process
from media2text.core.live.protocol import LivePlatformAdapter
from media2text.core.live.streaming_stt import StreamingSttSession
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.live.pipeline_events import record_event, stage_event
from media2text.core.manifest import refresh_manifest
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, PostProcessJobRepo

log = structlog.get_logger()
FFMPEG_STARTUP_GRACE_SEC = 2


class LiveRecordingCore:
    def __init__(
        self,
        cfg: AppConfig,
        *,
        conn,
        adapter: LivePlatformAdapter,
        platform: str,
        processes: dict[str, Popen],
        notify: NotifyService,
    ) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._conn = conn
        self._creators = CreatorRepo(conn)
        self._sessions = LiveSessionRepo(conn)
        self._jobs = PostProcessJobRepo(conn)
        self._adapter = adapter
        self._platform = platform
        self._processes = processes
        self._notify = notify
        self._flv_size_snapshots: dict[str, int] = {}
        self._stt_sessions: dict[str, StreamingSttSession] = {}
        self._stream_urls: dict[str, str] = {}
        self._streaming_legacy_finalize: set[str] = set()

    def scan_and_start(
        self, *, creator_id: str | None = None
    ) -> tuple[list[dict], set[str], list[dict], bool, bool]:
        targets = [
            c for c in self._creators.list_monitored() if c.platform == self._platform
        ]
        if creator_id:
            row = self._creators.get(creator_id)
            targets = [row] if row and row.platform == self._platform else []

        started: list[dict] = []
        started_session_ids: set[str] = set()
        errors: list[dict] = []
        auth_required = False
        platform_changed = False

        scan_targets: list = []
        for creator in targets:
            if self._sessions.get_active_for_creator(creator.id):
                continue
            scan_targets.append(creator)

        live_by_creator: dict[str, tuple] = {}
        workers = max(1, self._cfg.live.scan_concurrency)
        if scan_targets:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self._fetch_live_info, creator): creator
                    for creator in scan_targets
                }
                for fut in as_completed(futures):
                    creator = futures[fut]
                    live_by_creator[creator.id] = fut.result()

        for creator in scan_targets:
            outcome = live_by_creator.get(creator.id)
            if outcome is None:
                continue
            live_info, err = outcome
            if err is not None:
                kind, payload = err
                if kind == "auth_required":
                    auth_required = True
                elif kind == "platform_changed":
                    platform_changed = True
                errors.append(payload)
                continue
            if live_info is None or not live_info.is_live or not live_info.room_id:
                continue
            room_id = live_info.room_id
            try:
                meta = self._start_recording(
                    creator.id, creator.sec_uid, room_id, live_info
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
                    "live_stream_url_resolve_failed",
                    creator_id=creator.id,
                    room_id=room_id,
                    error=str(exc),
                )
                errors.append({"creator_id": creator.id, "error": str(exc)})
                continue

            started.append(meta)
            started_session_ids.add(meta["session_id"])

        return started, started_session_ids, errors, auth_required, platform_changed

    def _fetch_live_info(self, creator):
        try:
            return self._adapter.get_live_room(sec_uid=creator.sec_uid), None
        except AuthRequired as exc:
            return None, (
                "auth_required",
                {
                    "creator_id": creator.id,
                    "error": str(exc),
                    "auth_required": True,
                },
            )
        except PlatformChanged as exc:
            return None, (
                "platform_changed",
                {
                    "creator_id": creator.id,
                    "error": str(exc),
                    "platform_changed": True,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_status_check_failed",
                creator_id=creator.id,
                error=str(exc),
            )
            return None, (
                "error",
                {"creator_id": creator.id, "error": str(exc)},
            )

    def poll_active_recordings(
        self, *, skip_session_ids: set[str] | None = None
    ) -> list[dict]:
        skip = skip_session_ids or set()
        finalized: list[dict] = []
        min_offline = self._cfg.live.min_recording_sec_before_offline_end
        confirm_sec = self._cfg.live.offline_confirm_sec

        for row in self._sessions.list_active():
            if row.id in skip:
                continue
            if row.status != "recording" or row.ffmpeg_pid is None:
                continue
            creator = self._creators.get(row.creator_id)
            if not creator or creator.platform != self._platform:
                continue

            pid = row.ffmpeg_pid
            if not self._process_alive(pid):
                meta = self._handle_ffmpeg_exit(row, creator)
                if meta:
                    finalized.append(meta)
                continue

            if self._use_streaming_pipeline() and row.id not in self._streaming_legacy_finalize:
                stt = self._stt_sessions.get(row.id)
                if stt is not None and not stt.is_alive():
                    self._handle_stt_disconnect(row, creator)

            try:
                still_live = self._recording_still_live(creator, row)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "live_status_check_failed",
                    creator_id=creator.id,
                    error=str(exc),
                )
                continue

            if still_live:
                if row.offline_since_at:
                    self._sessions.clear_offline_since(row.id)
                    record_event(
                        self._conn,
                        session_id=row.id,
                        stage="recording",
                        status="offline_cancelled",
                    )
                    log.debug(
                        "live_offline_cancelled",
                        session_id=row.id,
                        creator_id=creator.id,
                    )
                continue

            if self._recording_age_sec(row.started_at) < min_offline:
                continue

            now = datetime.now(timezone.utc)
            if row.offline_since_at is None:
                iso = now.isoformat()
                self._sessions.set_offline_since(row.id, iso)
                record_event(
                    self._conn,
                    session_id=row.id,
                    stage="recording",
                    status="offline_pending",
                )
                self._emit_live_ended(creator, row)
                continue

            offline_since = self._parse_iso(row.offline_since_at)
            if offline_since is None:
                continue
            elapsed = (now - offline_since).total_seconds()
            if elapsed < confirm_sec:
                continue

            meta = self._finalize_recording(row.id, row.temp_path, pid)
            if meta:
                finalized.append(meta)

        return finalized

    def _handle_ffmpeg_exit(self, row, creator) -> dict | None:
        session_id = row.id
        temp_path = row.temp_path
        pid = row.ffmpeg_pid
        if pid is None:
            return self._finalize_recording(session_id, temp_path, 0)

        if self._cfg.live.ffmpeg_exit_recheck:
            try:
                still_live = self._recording_still_live(creator, row)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "live_ffmpeg_exit_recheck_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                still_live = False
        else:
            still_live = False

        attempts = row.reconnect_attempts or 0
        if (
            still_live
            and attempts < self._cfg.live.max_reconnect_attempts
            and temp_path
        ):
            return self._reconnect_segment(session_id, creator, temp_path, pid)

        return self._finalize_recording(session_id, temp_path, pid)

    def _use_streaming_pipeline(self) -> bool:
        return self._cfg.live.is_streaming_pipeline() and self._platform == "douyin"

    def _mark_streaming_degraded(
        self,
        session_id: str,
        *,
        reason: str,
        error: str | None = None,
    ) -> None:
        self._streaming_legacy_finalize.add(session_id)
        detail: dict[str, str] = {"reason": reason}
        if error:
            detail["error"] = error
        record_event(
            self._conn,
            session_id=session_id,
            stage="streaming_stt",
            status="degraded",
            detail=detail,
        )

    def _handle_stt_disconnect(self, row, creator) -> None:
        session_id = row.id
        stt = self._stt_sessions.pop(session_id, None)
        if stt is not None:
            try:
                stt.stop(timeout=5)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_stt_stop_on_disconnect_failed",
                    session_id=session_id,
                    error=str(exc),
                )

        if not self._cfg.live.streaming_stt.reconnect:
            self._mark_streaming_degraded(session_id, reason="stt_disconnect")
            return

        stream_url = self._stream_urls.get(session_id)
        if not stream_url and row.room_id:
            try:
                stream_url = self._adapter.resolve_stream_url(
                    room_id=row.room_id,
                    sec_uid=creator.sec_uid,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_stt_reconnect_resolve_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                stream_url = None

        if not stream_url or not row.temp_path:
            self._mark_streaming_degraded(
                session_id,
                reason="stt_reconnect_no_url",
            )
            return

        try:
            new_stt = StreamingSttSession(
                self._cfg,
                stream_url=stream_url,
                media_path=Path(row.temp_path),
            )
            with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                new_stt.start()
            self._stt_sessions[session_id] = new_stt
            record_event(
                self._conn,
                session_id=session_id,
                stage="streaming_stt",
                status="reconnected",
                detail={"reason": "stt_disconnect"},
            )
            log.info("streaming_stt_reconnected", session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "streaming_stt_reconnect_failed",
                session_id=session_id,
                error=str(exc),
            )
            self._mark_streaming_degraded(
                session_id,
                reason="stt_reconnect_failed",
                error=str(exc),
            )

    def _reconnect_segment(
        self,
        session_id: str,
        creator,
        temp_path: str,
        old_pid: int,
    ) -> None:
        proc_old = self._processes.pop(session_id, None)
        if proc_old is not None:
            stop_process(proc_old, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif self._process_alive(old_pid):
            os.kill(old_pid, 15)

        stt = self._stt_sessions.pop(session_id, None)
        if stt is not None:
            try:
                stt.stop(timeout=5)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_stt_stop_on_reconnect_failed",
                    session_id=session_id,
                    error=str(exc),
                )
            self._mark_streaming_degraded(session_id, reason="ffmpeg_reconnect")

        self._sessions.append_segment_path(session_id, temp_path)
        attempt = self._sessions.increment_reconnect_attempts(session_id)

        try:
            live_info = self._adapter.get_live_room(sec_uid=creator.sec_uid)
            room_id = live_info.room_id
            stream_url = live_info.stream_flv_url
            if not stream_url and room_id:
                stream_url = self._adapter.resolve_stream_url(
                    room_id=room_id,
                    sec_uid=creator.sec_uid,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_reconnect_stream_failed",
                session_id=session_id,
                error=str(exc),
            )
            self._finalize_recording(session_id, temp_path, old_pid)
            return None

        if not stream_url:
            self._finalize_recording(session_id, temp_path, old_pid)
            return None

        live_dir = self._ws / "creators" / creator.sec_uid / "live"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        new_temp = live_dir / f"{stamp}_r{attempt}.flv"
        new_proc = record_stream_copy(
            ffmpeg=self._cfg.live.ffmpeg_path,
            stream_url=stream_url,
            output_path=new_temp,
        )
        self._sessions.update_recording_state(
            session_id,
            ffmpeg_pid=new_proc.pid,
            temp_path=str(new_temp),
        )
        self._processes[session_id] = new_proc
        self._stream_urls[session_id] = stream_url
        time.sleep(FFMPEG_STARTUP_GRACE_SEC)
        log.info(
            "live_recording_reconnected",
            session_id=session_id,
            attempt=attempt,
            temp_path=str(new_temp),
        )
        return None

    def _start_recording(
        self,
        creator_id: str,
        sec_uid: str,
        room_id: str | None,
        live_info: LiveRoomInfo,
    ) -> dict:
        live_dir = self._ws / "creators" / sec_uid / "live"
        live_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        temp_path = live_dir / f"{stamp}.flv"

        session_id = self._sessions.create(
            creator_id=creator_id,
            room_id=room_id,
            temp_path=str(temp_path),
            ffmpeg_pid=None,
            platform_live_started_at=live_info.platform_live_started_at,
        )
        record_event(
            self._conn,
            session_id=session_id,
            stage="detected_live",
            status="completed",
            detail={"room_id": room_id},
        )

        with stage_event(self._conn, session_id=session_id, stage="stream_resolve"):
            stream_url = live_info.stream_flv_url
            if not stream_url:
                if not room_id:
                    raise ValueError("room_id required for stream resolve")
                stream_url = self._adapter.resolve_stream_url(
                    room_id=room_id,
                    sec_uid=sec_uid,
                )
            if not stream_url:
                raise ValueError("empty stream url after resolve")

        self._stream_urls[session_id] = stream_url

        use_streaming = self._use_streaming_pipeline()
        stt_session: StreamingSttSession | None = None
        if use_streaming:
            stt_session = StreamingSttSession(
                self._cfg,
                stream_url=stream_url,
                media_path=temp_path,
            )

        proc = record_stream_copy(
            ffmpeg=self._cfg.live.ffmpeg_path,
            stream_url=stream_url,
            output_path=temp_path,
        )
        self._sessions.update_recording_state(
            session_id,
            ffmpeg_pid=proc.pid,
            temp_path=str(temp_path),
        )
        self._processes[session_id] = proc

        stt_failed = False
        stt_error = ""
        if stt_session is not None:
            try:
                with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                    stt_session.start()
                self._stt_sessions[session_id] = stt_session
                record_event(
                    self._conn,
                    session_id=session_id,
                    stage="streaming_stt",
                    status="started",
                )
            except Exception as exc:  # noqa: BLE001
                stt_failed = True
                stt_error = str(exc)
                log.error(
                    "streaming_stt_start_failed",
                    session_id=session_id,
                    error=stt_error,
                )
                record_event(
                    self._conn,
                    session_id=session_id,
                    stage="streaming_stt",
                    status="failed",
                    detail={"error": stt_error},
                )

        time.sleep(FFMPEG_STARTUP_GRACE_SEC)
        exit_code = proc.poll()
        if exit_code is not None or stt_failed:
            err_tail = ""
            if proc.stderr is not None:
                err_tail = proc.stderr.read().decode(errors="replace")[-500:]
            if stt_session is not None and session_id in self._stt_sessions:
                self._stt_sessions.pop(session_id, None)
                try:
                    stt_session.stop(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
            self._processes.pop(session_id, None)
            err_parts = []
            if exit_code is not None:
                err_parts.append(f"ffmpeg_exited_early:{exit_code}:{err_tail}")
            if stt_failed:
                err_parts.append(f"streaming_stt_failed:{stt_error}")
            self._sessions.update_status(
                session_id,
                status="failed",
                error="; ".join(err_parts) or "live_start_failed",
                ended=True,
            )
            log.error(
                "live_start_failed",
                session_id=session_id,
                exit_code=exit_code,
                stt_failed=stt_failed,
            )
            creator = self._creators.get(creator_id)
            if creator:
                label = creator_label(creator)
                body = f"room_id: {room_id or '—'}\n"
                if exit_code is not None:
                    body = f"ffmpeg 启动失败（exit {exit_code}）\n" + body
                if stt_failed:
                    body = f"流式转写启动失败：{stt_error}\n" + body
                self._notify.emit(
                    NotifyEvent(
                        kind=EventKind.LIVE_START_FAILED,
                        title=label,
                        body=body.strip(),
                    )
                )
            return {
                "session_id": session_id,
                "temp_path": str(temp_path),
                "pid": proc.pid,
            }

        log.info(
            "live_recording_started", session_id=session_id, temp_path=str(temp_path)
        )
        record_event(
            self._conn,
            session_id=session_id,
            stage="recording",
            status="started",
            detail={"temp_path": str(temp_path), "pid": proc.pid},
        )
        creator = self._creators.get(creator_id)
        if creator:
            label = creator_label(creator)
            mode = "streaming" if use_streaming else "legacy"
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.LIVE_STARTED,
                    title=label,
                    body=(
                        f"检测到开播，已开始录制（{mode}）\n"
                        f"room_id: {room_id or '—'}\n"
                        f"文件: {temp_path.name}"
                    ),
                )
            )
        return {"session_id": session_id, "temp_path": str(temp_path), "pid": proc.pid}

    def _recording_still_live(self, creator, row) -> bool:
        try:
            profile = self._adapter.get_live_room(sec_uid=creator.sec_uid)
        except Exception:
            if self._cfg.live.offline_trust_recording_signals:
                return self._infer_live_from_recording(row, creator)
            raise

        if profile.is_live:
            return True
        if not self._cfg.live.offline_trust_recording_signals:
            return False
        return self._infer_live_from_recording(row, creator)

    def _infer_live_from_recording(self, row, creator) -> bool:
        pid = row.ffmpeg_pid
        if pid is None or not self._process_alive(pid):
            return False
        temp_path = row.temp_path
        if temp_path and self._flv_file_growing(row.id, temp_path):
            log.debug(
                "live_offline_ignored_flv_growing",
                session_id=row.id,
                creator_id=row.creator_id,
            )
            return True
        reflow_getter = getattr(self._adapter, "get_room_reflow", None)
        room_id = row.room_id
        if room_id and callable(reflow_getter):
            try:
                reflow = reflow_getter(room_id=room_id, sec_uid=creator.sec_uid)
                if isinstance(reflow, LiveRoomInfo) and reflow.is_live:
                    log.debug(
                        "live_offline_ignored_reflow_live",
                        session_id=row.id,
                        room_id=room_id,
                    )
                    return True
            except Exception as exc:  # noqa: BLE001
                log.debug(
                    "live_reflow_check_failed",
                    session_id=row.id,
                    room_id=room_id,
                    error=str(exc),
                )
        return False

    def _flv_file_growing(self, session_id: str, temp_path: str) -> bool:
        path = Path(temp_path)
        if not path.is_file():
            return False
        size = path.stat().st_size
        prev = self._flv_size_snapshots.get(session_id)
        self._flv_size_snapshots[session_id] = size
        if prev is None:
            return size > 4096
        return size > prev

    def _emit_live_ended(self, creator, row) -> None:
        label = creator_label(creator)
        self._notify.emit(
            NotifyEvent(
                kind=EventKind.LIVE_ENDED,
                title=label,
                body=(
                    f"检测到下播，等待 {self._cfg.live.offline_confirm_sec}s 确认后停录\n"
                    f"session: {row.id[:8]}…"
                ),
            )
        )

    def _parse_iso(self, value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _recording_age_sec(self, started_at: str) -> float:
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return self._cfg.live.min_recording_sec_before_offline_end
        return (datetime.now(timezone.utc) - started).total_seconds()

    def _process_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _finalize_recording(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        segments = self._sessions.list_segment_paths(session_id)
        use_streaming_finalize = (
            self._use_streaming_pipeline()
            and session_id not in self._streaming_legacy_finalize
            and not segments
        )
        if use_streaming_finalize:
            return self._finalize_recording_streaming(session_id, temp_path, pid)
        return self._finalize_recording_legacy(session_id, temp_path, pid)

    def _finalize_recording_streaming(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif pid and self._process_alive(pid):
            os.kill(pid, 15)

        stt = self._stt_sessions.pop(session_id, None)
        self._stream_urls.pop(session_id, None)
        transcript_ok = False
        if not temp_path:
            self._sessions.update_status(
                session_id, status="failed", error="missing temp_path", ended=True
            )
            return None

        current = Path(temp_path)
        if not current.is_file() or current.stat().st_size == 0:
            self._sessions.update_status(
                session_id,
                status="failed",
                error="empty_recording",
                ended=True,
            )
            log.warning("live_recording_empty", session_id=session_id)
            return None

        try:
            with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                if stt is not None:
                    paths = stt.stop(timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
                    transcript_ok = paths is not None
                elif current.with_suffix(".transcript.json").is_file():
                    transcript_ok = True
            record_event(
                self._conn,
                session_id=session_id,
                stage="streaming_stt",
                status="completed" if transcript_ok else "failed",
            )
            record_event(
                self._conn,
                session_id=session_id,
                stage="remux",
                status="skipped",
            )
            if transcript_ok:
                index_transcript_safe(self._cfg, current.with_suffix(".transcript.json"))
        except Exception as exc:  # noqa: BLE001
            record_event(
                self._conn,
                session_id=session_id,
                stage="streaming_stt",
                status="failed",
                detail={"error": str(exc)},
            )
            log.exception("streaming_stt_finalize_failed", session_id=session_id)

        self._sessions.update_status(
            session_id,
            status="completed",
            local_path=str(current),
            transcribe_status="completed" if transcript_ok else "failed",
            ended=True,
        )
        self._sessions.clear_pid(session_id)
        log.info(
            "live_recording_completed_streaming",
            session_id=session_id,
            path=str(current),
        )

        session = self._sessions.get(session_id)
        if not session:
            return None
        creator = self._creators.get(session.creator_id)
        if not creator:
            return {"session_id": session_id, "path": str(current)}

        job_id = self._jobs.enqueue(
            session_id=session_id,
            creator_id=creator.id,
            mp4_path=str(current),
        )
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
                body=f"直播录制已完成\n{current.name}\n{current.parent}",
            )
        )
        if transcript_ok:
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.TRANSCRIBE_COMPLETED,
                    title=label,
                    body=f"直播转录完成（deepgram streaming）\n{current.name}",
                )
            )
        return {
            "session_id": session_id,
            "path": str(current),
            "creator_id": creator.id,
            "job_id": job_id,
        }

    def _finalize_recording_legacy(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif pid and self._process_alive(pid):
            os.kill(pid, 15)

        stt = self._stt_sessions.pop(session_id, None)
        if stt is not None:
            try:
                stt.stop(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        self._streaming_legacy_finalize.discard(session_id)
        self._stream_urls.pop(session_id, None)

        if not temp_path:
            self._sessions.update_status(
                session_id, status="failed", error="missing temp_path", ended=True
            )
            return None

        segments = [
            Path(p) for p in self._sessions.list_segment_paths(session_id)
        ]
        current = Path(temp_path)
        sources = segments + [current]
        valid_sources = [p for p in sources if p.is_file() and p.stat().st_size > 0]
        if not valid_sources:
            self._sessions.update_status(
                session_id,
                status="failed",
                error="empty_recording",
                ended=True,
            )
            log.warning("live_recording_empty", session_id=session_id)
            return None

        mp4 = current.with_suffix(".mp4")
        if len(valid_sources) == 1 and valid_sources[0] == current:
            mp4 = current.with_suffix(".mp4")

        self._sessions.update_status(session_id, status="remuxing")
        try:
            with stage_event(self._conn, session_id=session_id, stage="remux"):
                if len(valid_sources) == 1:
                    remux_to_mp4(
                        ffmpeg=self._cfg.live.ffmpeg_path,
                        src=valid_sources[0],
                        dst=mp4,
                    )
                    if valid_sources[0] != mp4:
                        valid_sources[0].unlink(missing_ok=True)
                else:
                    concat_to_mp4(
                        ffmpeg=self._cfg.live.ffmpeg_path,
                        sources=valid_sources,
                        dst=mp4,
                    )
                    for seg in valid_sources:
                        if seg.suffix.lower() in (".flv", ".ts", ".mkv"):
                            seg.unlink(missing_ok=True)
            self._sessions.update_status(
                session_id,
                status="completed",
                local_path=str(mp4),
                ended=True,
            )
            self._sessions.clear_pid(session_id)
            log.info("live_recording_completed", session_id=session_id, path=str(mp4))
        except Exception as exc:  # noqa: BLE001
            seg_list = ", ".join(str(p) for p in valid_sources)
            self._sessions.update_status(
                session_id,
                status="failed",
                error=f"{exc}; segments={seg_list}",
                ended=True,
            )
            log.exception("live_recording_failed", session_id=session_id)
            return None

        session = self._sessions.get(session_id)
        if not session:
            return None
        creator = self._creators.get(session.creator_id)
        if not creator:
            return {"session_id": session_id, "path": str(mp4)}

        job_id = self._jobs.enqueue(
            session_id=session_id,
            creator_id=creator.id,
            mp4_path=str(mp4),
        )
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
                body=f"直播录制已完成\n{mp4.name}\n{mp4.parent}",
            )
        )
        return {
            "session_id": session_id,
            "path": str(mp4),
            "creator_id": creator.id,
            "job_id": job_id,
        }
