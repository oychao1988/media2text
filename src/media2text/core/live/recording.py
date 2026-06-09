from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import structlog

from media2text.core.live.probe_guard import ProbeExecutionGuard, guarded_popen as Popen

from media2text.core.config import AppConfig
from media2text.core.desktop.auto_record import effective_auto_record
from media2text.core.errors import (
    AlreadyRecording,
    AuthRequired,
    NotLive,
    NotRecording,
    PlatformChanged,
    RecordingError,
)
from media2text.core.live.probe import probe_workers
from media2text.core.archive.hook import index_transcript_safe
from media2text.core.ffmpeg import (
    concat_to_flv,
    concat_to_mp4,
    record_stream_copy,
    remux_to_mp4,
    stop_pid,
    stop_process,
)
from media2text.core.live.hls_recorder import (
    finalize_hls_endlist,
    mark_closed_with_duration,
    part_rel_path,
    rotate_hls_after_reconnect,
    spawn_hls_recorder,
    stop_hls_recorder,
)
from media2text.core.cloud.live_upload import upload_hls_session_sidecars
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.live.segment_watcher import get_segment_watcher
from media2text.core.live.protocol import LivePlatformAdapter
from media2text.core.live.partial_notify import PartialTranscriptNotifier
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.live.streaming_stt import StreamingSttSession
from media2text.core.live.transcript_writer import (
    hls_transcript_anchor_path,
    list_segment_checkpoints,
    merge_transcript_checkpoints,
    partial_segment_end_from_media,
    transcript_sidecar_media_paths,
    seal_partial_transcript,
)
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.live.pipeline_events import stage_event
from media2text.core.live.state_writer import StateWriter
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo, PostProcessJobRepo

log = structlog.get_logger()
FFMPEG_STARTUP_GRACE_SEC = 2
TRANSCRIPT_STALL_RECONNECT_SEC = 90


class LiveRecordingCore:
    def __init__(
        self,
        cfg: AppConfig,
        *,
        conn,
        adapter: LivePlatformAdapter,
        platform: str,
        notify: NotifyService,
        processes: dict[str, Popen] | None = None,
        runtime: SessionRuntime | None = None,
    ) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._conn = conn
        self._creators = CreatorRepo(conn)
        self._sessions = LiveSessionRepo(conn)
        self._state = StateWriter(conn, cfg=cfg, notify=notify)
        self._jobs = PostProcessJobRepo(conn)
        self._adapter = adapter
        self._platform = platform
        if runtime is None:
            runtime = SessionRuntime()
            if processes is not None:
                runtime.processes = processes
        elif processes is not None and not runtime.processes:
            runtime.processes = processes
        self._runtime = runtime
        self._notify = notify
        self._flv_size_snapshots: dict[str, int] = {}
        self._flv_stall_polls: dict[str, int] = {}
        self._stream_urls: dict[str, str] = {}
        self._streaming_legacy_finalize: set[str] = set()
        self._streaming_transcript_anchor: dict[str, Path] = {}
        self._stt_checkpoint_counter: dict[str, int] = {}
        self._partial_notifiers: dict[str, PartialTranscriptNotifier] = {}
        self._hls_part_index: dict[str, int] = {}
        self._hls_discontinuity_seq: dict[str, int] = {}
        self._stall_recovery_inflight: set[str] = set()

    @property
    def _processes(self) -> dict[str, Popen]:
        return self._runtime.processes

    @property
    def _stt_sessions(self) -> dict[str, StreamingSttSession]:
        return self._runtime.stt_sessions

    def observe_live_state(self, creator) -> tuple[LiveRoomInfo | None, dict | None]:
        """Fetch live status, upsert snapshot, enqueue outbox; no recording."""
        live_info, err = self._fetch_live_info(creator)
        if err is not None:
            _kind, payload = err
            self._state.mark_snapshot_probe_failed(
                creator.id,
                error=str(payload.get("error", _kind)),
            )
            return None, payload
        if live_info is not None:
            self._state.update_snapshot(creator.id, live_info)
        return live_info, None

    def _observe_for_probe(self, creator) -> tuple[LiveRoomInfo | None, dict | None]:
        """Thread-safe live probe: each worker gets its own SQLite connection."""
        from media2text.core.workspace import open_db

        conn = open_db(self._cfg)
        try:
            core = LiveRecordingCore(
                self._cfg,
                conn=conn,
                adapter=self._adapter,
                platform=self._platform,
                notify=self._notify,
            )
            return core.observe_live_state(creator)
        finally:
            conn.close()

    def probe_live(
        self,
        *,
        creator_id: str | None = None,
        deadline: float | None = None,
    ) -> tuple[list[dict], bool, bool]:
        """LP-01: parallel observe_live_state for creators without active sessions."""
        targets = [
            c for c in self._creators.list_monitored() if c.platform == self._platform
        ]
        if creator_id:
            row = self._creators.get(creator_id)
            targets = [row] if row and row.platform == self._platform else []

        errors: list[dict] = []
        auth_required = False
        platform_changed = False

        scan_targets = [
            c for c in targets if not self._sessions.get_active_for_creator(c.id)
        ]
        if not scan_targets:
            return errors, auth_required, platform_changed

        if deadline is not None and time.monotonic() >= deadline:
            return errors, auth_required, platform_changed

        workers = probe_workers(self._cfg, len(scan_targets))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._observe_for_probe, creator): creator
                for creator in scan_targets
            }
            for future in as_completed(futures):
                if deadline is not None and time.monotonic() >= deadline:
                    break
                creator = futures[future]
                try:
                    _live_info, err = future.result()
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "live_status_check_failed",
                        creator_id=creator.id,
                        error=str(exc),
                    )
                    errors.append({"creator_id": creator.id, "error": str(exc)})
                    continue
                if err is None:
                    continue
                errors.append(err)
                if err.get("auth_required"):
                    auth_required = True
                elif err.get("platform_changed"):
                    platform_changed = True

        return errors, auth_required, platform_changed

    def maybe_start_recording(self, creator, live_info: LiveRoomInfo) -> dict:
        return self._start_recording(
            creator.id, creator.sec_uid, live_info.room_id, live_info
        )

    def start_recording_for_creator(self, creator_id: str) -> dict:
        """Start recording when the creator is live and has no active session."""
        if self._sessions.get_active_for_creator(creator_id):
            raise AlreadyRecording("creator already has an active recording")
        creator = self._creators.get(creator_id)
        if not creator:
            raise ValueError(f"creator not found: {creator_id}")
        if creator.platform != self._platform:
            raise ValueError(
                f"creator platform {creator.platform!r} does not match {self._platform!r}"
            )
        live_info, err = self._fetch_live_info(creator)
        if err is not None:
            kind, _payload = err
            if kind == "auth_required":
                raise AuthRequired("auth required for live status")
            if kind == "platform_changed":
                raise PlatformChanged("platform changed")
            raise RecordingError(str(_payload.get("error", "live status check failed")))
        if live_info is not None:
            self._state.update_snapshot(creator_id, live_info)
        if live_info is None or not live_info.is_live or not live_info.room_id:
            raise NotLive("creator is not live")
        return self._start_recording(
            creator.id,
            creator.sec_uid,
            live_info.room_id,
            live_info,
        )

    def stop_recording_for_creator(self, creator_id: str) -> dict | None:
        """Finalize the active recording session for a creator."""
        row = self._sessions.get_active_for_creator(creator_id)
        if not row:
            raise NotRecording("no active recording for creator")
        return self._finalize_recording(
            row.id,
            row.temp_path,
            row.ffmpeg_pid or 0,
        )

    def run_prepare_live_recording(
        self,
        creator_id: str,
        *,
        live_info: LiveRoomInfo | None = None,
    ) -> dict:
        """LW-01: resolve stream if needed, create session, spawn ffmpeg."""
        if self._sessions.get_active_for_creator(creator_id):
            return {"skipped": "already_recording", "creator_id": creator_id}
        creator = self._creators.get(creator_id)
        if not creator:
            raise ValueError(f"creator_not_found:{creator_id}")
        if creator.platform != self._platform:
            raise ValueError(f"platform_mismatch:{creator.platform}")
        if not effective_auto_record(creator, self._cfg):
            return {"skipped": "auto_record_disabled", "creator_id": creator_id}

        if live_info is None:
            live_info, err = self._fetch_live_info(creator)
            if err is not None:
                _kind, payload = err
                return {"ok": False, "kind": _kind, **payload}
        if live_info is not None:
            self._state.update_snapshot(creator_id, live_info)
        if live_info is None or not live_info.is_live or not live_info.room_id:
            return {"skipped": "not_live", "creator_id": creator_id}

        meta = self.maybe_start_recording(creator, live_info)
        return {"started": meta}

    def run_start_streaming_stt(self, session_id: str) -> dict:
        """LW-02: start STT sidecar on an active streaming recording."""
        row = self._sessions.get(session_id)
        if not row:
            raise ValueError(f"session_not_found:{session_id}")
        if row.status != "recording":
            return {"skipped": "not_recording", "session_id": session_id}
        if not self._use_streaming_pipeline(session_id):
            return {"skipped": "not_streaming", "session_id": session_id}
        if session_id in self._stt_sessions:
            return {"skipped": "stt_already_running", "session_id": session_id}

        creator = self._creators.get(row.creator_id)
        if not creator:
            raise ValueError(f"creator_not_found:{row.creator_id}")
        if not row.temp_path:
            raise ValueError(f"missing_temp_path:{session_id}")

        stream_url = self._stream_urls.get(session_id)
        if not stream_url and row.room_id:
            stream_url = self._adapter.resolve_stream_url(
                room_id=row.room_id,
                sec_uid=creator.sec_uid,
            )
        if not stream_url:
            raise ValueError(f"missing_stream_url:{session_id}")

        self._streaming_transcript_anchor.setdefault(
            session_id,
            self._normalize_transcript_anchor(Path(row.temp_path)),
        )
        self._stt_checkpoint_counter.setdefault(session_id, 0)
        anchor = self._transcript_anchor(session_id, row.temp_path)
        stt_session = self._build_streaming_stt_session(
            session_id,
            creator=creator,
            stream_url=stream_url,
            media_path=anchor,
        )
        with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
            stt_session.start()
        self._stt_sessions[session_id] = stt_session
        self._state.update_status(session_id, transcribe_status="streaming")
        self._state.record_pipeline_event(
            session_id=session_id,
            stage="streaming_stt",
            status="started",
            detail={"task": "start_streaming_stt"},
        )
        return {"started": True, "session_id": session_id}

    def run_reconnect_recording(self, session_id: str) -> dict:
        """LW-03: ffmpeg reconnect — wraps _reconnect_segment."""
        row = self._sessions.get(session_id)
        if not row:
            raise ValueError(f"session_not_found:{session_id}")
        if row.status != "recording":
            return {"skipped": "not_recording", "session_id": session_id}
        creator = self._creators.get(row.creator_id)
        if not creator:
            raise ValueError(f"creator_not_found:{row.creator_id}")
        if not row.temp_path or row.ffmpeg_pid is None:
            raise ValueError(f"missing_recording_state:{session_id}")

        self._reconnect_segment(
            session_id,
            creator,
            row.temp_path,
            row.ffmpeg_pid,
        )
        return {"reconnected": True, "session_id": session_id}

    def run_reconnect_streaming_stt(self, session_id: str) -> dict:
        """LW-04: STT reconnect — wraps _handle_stt_disconnect path."""
        row = self._sessions.get(session_id)
        if not row:
            raise ValueError(f"session_not_found:{session_id}")
        if row.status != "recording":
            return {"skipped": "not_recording", "session_id": session_id}
        creator = self._creators.get(row.creator_id)
        if not creator:
            raise ValueError(f"creator_not_found:{row.creator_id}")

        self._handle_stt_disconnect(row, creator)
        return {"session_id": session_id, "stt_reconnect_attempted": True}

    @staticmethod
    def live_info_from_payload(payload: dict) -> LiveRoomInfo | None:
        raw = payload.get("live_info")
        if raw is None:
            return None
        if isinstance(raw, LiveRoomInfo):
            return raw
        if isinstance(raw, dict):
            return LiveRoomInfo(
                room_id=raw.get("room_id"),
                is_live=bool(raw.get("is_live")),
                stream_flv_url=raw.get("stream_flv_url"),
                title=raw.get("title"),
                platform_live_started_at=raw.get("platform_live_started_at"),
            )
        return None

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

    def _normalize_transcript_anchor(self, media_path: Path) -> Path:
        hls_anchor = hls_transcript_anchor_path(media_path)
        return hls_anchor if hls_anchor is not None else media_path

    def _transcript_partial_age_sec(self, row) -> float | None:
        if not row.temp_path:
            return None
        anchor = self._streaming_transcript_anchor.get(row.id)
        candidates: list[Path] = []
        if anchor is not None:
            candidates.append(anchor)
        candidates.extend(transcript_sidecar_media_paths(Path(row.temp_path)))
        freshest: float | None = None
        for base in candidates:
            partial = base.with_suffix(".transcript.partial.json")
            if not partial.is_file():
                continue
            age = time.time() - partial.stat().st_mtime
            if freshest is None or age < freshest:
                freshest = age
        return freshest

    def _partial_timeline_offset_sec(self, row) -> float:
        best = 0.0
        media_paths: list[Path] = []
        if row.segment_paths_json:
            try:
                data = json.loads(row.segment_paths_json)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, list):
                media_paths.extend(Path(str(p)) for p in data if p)
        for raw in (row.temp_path, row.local_path):
            if raw:
                media_paths.append(Path(raw))
        for path in media_paths:
            end = partial_segment_end_from_media(path)
            if end is not None and end > best:
                best = end
        return best

    def _resolve_live_stream_url(self, creator, *, room_id: str | None) -> str | None:
        if room_id:
            try:
                url = self._adapter.resolve_stream_url(
                    room_id=room_id,
                    sec_uid=creator.sec_uid,
                )
                if url:
                    return url
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "resolve_stream_url_failed",
                    creator_id=creator.id,
                    room_id=room_id,
                    error=str(exc),
                )
            return None
        try:
            live_info = self._adapter.get_live_room(sec_uid=creator.sec_uid)
            url = live_info.stream_flv_url
            rid = room_id or live_info.room_id
            if not url and rid:
                url = self._adapter.resolve_stream_url(
                    room_id=rid,
                    sec_uid=creator.sec_uid,
                )
            return url or None
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "resolve_live_stream_url_failed",
                creator_id=creator.id,
                error=str(exc),
            )
            return None

    def _maybe_recover_stalled_stream(
        self,
        row,
        creator,
        *,
        ffmpeg_alive: bool,
        stt_alive: bool | None,
    ) -> None:
        if row.status != "recording":
            return
        if row.id in self._streaming_legacy_finalize:
            return
        if not self._use_streaming_pipeline(row.id):
            return
        if row.id in self._stall_recovery_inflight:
            return
        attempts = row.reconnect_attempts or 0
        if attempts >= self._cfg.live.max_reconnect_attempts:
            return

        stale_sec = self._transcript_partial_age_sec(row)
        if stale_sec is None or stale_sec < TRANSCRIPT_STALL_RECONNECT_SEC:
            return

        if row.temp_path is None:
            return

        tasks = MonitorTaskRepo(self._conn)
        if tasks.has_active_dedupe(f"reconnect_rec:{row.id}") or tasks.has_active_dedupe(
            f"reconnect_stt:{row.id}"
        ):
            return

        self._stall_recovery_inflight.add(row.id)
        try:
            if not ffmpeg_alive:
                if row.ffmpeg_pid is None:
                    return
                log.warning(
                    "live_stream_stall_reconnect",
                    session_id=row.id,
                    transcript_stale_sec=round(stale_sec, 1),
                    stt_alive=stt_alive,
                    mode="ffmpeg",
                )
                self._reconnect_segment(
                    row.id,
                    creator,
                    row.temp_path,
                    row.ffmpeg_pid,
                )
                return

            if row.ffmpeg_pid is None:
                return

            if stt_alive is False:
                log.warning(
                    "live_stt_stall_reconnect",
                    session_id=row.id,
                    transcript_stale_sec=round(stale_sec, 1),
                    mode="stt_only",
                )
                self._handle_stt_disconnect(row, creator)
                return

            log.warning(
                "live_stream_stall_reconnect",
                session_id=row.id,
                transcript_stale_sec=round(stale_sec, 1),
                stt_alive=stt_alive,
                mode="full",
            )
            self._reconnect_segment(
                row.id,
                creator,
                row.temp_path,
                row.ffmpeg_pid,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_stream_stall_reconnect_failed",
                session_id=row.id,
                error=str(exc),
            )
        finally:
            self._stall_recovery_inflight.discard(row.id)

    def poll_active_session(self, row, creator, *, state: StateWriter) -> None:
        """LP-02: obs + offline semantics; inline stall recovery when CDN URL expires."""
        if row.status != "recording" or row.ffmpeg_pid is None:
            return

        pid = row.ffmpeg_pid
        ffmpeg_alive = self._process_alive(pid)

        stt_alive = None
        if self._use_streaming_pipeline(row.id) and row.id not in self._streaming_legacy_finalize:
            stt = self._stt_sessions.get(row.id)
            stt_alive = stt.is_alive() if stt else False

        try:
            still_live = self._recording_still_live(creator, row)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_status_check_failed",
                creator_id=creator.id,
                error=str(exc),
            )
            state.write_obs(
                row.id,
                ffmpeg_alive=ffmpeg_alive,
                stt_alive=stt_alive,
                still_live=None,
            )
            return

        state.write_obs(
            row.id,
            ffmpeg_alive=ffmpeg_alive,
            stt_alive=stt_alive,
            still_live=still_live,
        )

        if still_live:
            self._maybe_recover_stalled_stream(
                row,
                creator,
                ffmpeg_alive=ffmpeg_alive,
                stt_alive=stt_alive,
            )

        try:
            profile = self._adapter.get_live_room(sec_uid=creator.sec_uid)
            state.update_snapshot(creator.id, profile)
        except Exception:  # noqa: BLE001
            pass

        min_offline = self._cfg.live.min_recording_sec_before_offline_end

        if still_live:
            if row.offline_since_at:
                state.clear_offline_since(row.id, creator_id=creator.id)
            return

        if self._recording_age_sec(row.started_at) < min_offline:
            return

        now = datetime.now(timezone.utc)
        if row.offline_since_at is None:
            state.set_offline_since(row.id, now.isoformat(), creator_id=creator.id)

    def poll_active_recordings(
        self, *, skip_session_ids: set[str] | None = None
    ) -> list[dict]:
        """LP-02: obs-only poll for all active sessions (finalize via Reconciler)."""
        skip = skip_session_ids or set()
        state = StateWriter(self._conn, cfg=self._cfg, notify=self._notify)
        for row in self._sessions.list_active():
            if row.id in skip:
                continue
            if row.status != "recording" or row.ffmpeg_pid is None:
                continue
            creator = self._creators.get(row.creator_id)
            if not creator or creator.platform != self._platform:
                continue
            self.poll_active_session(row, creator, state=state)
        return []

    def _transcript_anchor(self, session_id: str, temp_path: str | None) -> Path:
        anchor = self._streaming_transcript_anchor.get(session_id)
        if anchor is not None:
            return self._normalize_transcript_anchor(anchor)
        if temp_path:
            return self._normalize_transcript_anchor(Path(temp_path))
        raise ValueError(f"missing transcript anchor for session {session_id}")

    def _checkpoint_streaming_stt(
        self, session_id: str, stt: StreamingSttSession
    ) -> float:
        idx = self._stt_checkpoint_counter.get(session_id, 0)
        end = stt.writer.checkpoint_segment(idx)
        self._stt_checkpoint_counter[session_id] = idx + 1
        return end

    def _clear_streaming_session_state(self, session_id: str) -> None:
        self._streaming_transcript_anchor.pop(session_id, None)
        self._stt_checkpoint_counter.pop(session_id, None)
        self._partial_notifiers.pop(session_id, None)
        self._hls_part_index.pop(session_id, None)
        self._hls_discontinuity_seq.pop(session_id, None)

    def _build_streaming_stt_session(
        self,
        session_id: str,
        *,
        creator,
        stream_url: str,
        media_path: Path,
        offset_sec: float = 0.0,
    ) -> StreamingSttSession:
        label = creator_label(creator)
        gate = self._partial_notifiers.setdefault(
            session_id,
            PartialTranscriptNotifier(self._cfg, self._notify, title=label),
        )

        def on_first_final(latency_sec: float) -> None:
            self._state.record_pipeline_event(
                session_id=session_id,
                stage="streaming_stt",
                status="first_final",
                duration_ms=int(latency_sec * 1000),
            )

        def on_partial_summary(summary: str, segment_count: int) -> None:
            gate.maybe_emit(summary, segment_count=segment_count)

        return StreamingSttSession(
            self._cfg,
            stream_url=stream_url,
            media_path=media_path,
            offset_sec=offset_sec,
            on_first_final=on_first_final,
            on_partial_summary=on_partial_summary,
        )

    def _use_hls_recording(self, session_id: str | None = None) -> bool:
        if not self._use_streaming_pipeline(session_id):
            return False
        if session_id:
            row = self._sessions.get(session_id)
            if row and row.session_dir:
                return True
        return self._cfg.live.uses_hls_media()

    def _resolve_session_dir(self, session_id: str) -> Path | None:
        row = self._sessions.get(session_id)
        if row and row.session_dir:
            return Path(row.session_dir)
        return None

    def _close_hls_part_if_any(self, session_id: str, session_dir: Path) -> None:
        idx = self._hls_part_index.get(session_id)
        if idx is None:
            return
        repo = SegmentManifestRepo(self._conn)
        part_path = session_dir / part_rel_path(idx)
        size = part_path.stat().st_size if part_path.is_file() else None
        mark_closed_with_duration(
            repo, session_id, idx, session_dir, bytes=size
        )

    def _spawn_hls_recording(
        self,
        *,
        session_id: str,
        stream_url: str,
        session_dir: Path,
        part_index: int,
        discontinuity_seq: int = 0,
    ) -> Popen:
        proc = spawn_hls_recorder(
            ffmpeg=self._cfg.live.ffmpeg_path,
            stream_url=stream_url,
            session_dir=session_dir,
            segment_sec=self._cfg.live.media.segment_duration_sec,
            compress_cfg=self._cfg.live.compress,
            start_segment_number=part_index,
        )
        repo = SegmentManifestRepo(self._conn)
        repo.upsert_part(
            session_id=session_id,
            part_index=part_index,
            rel_path=part_rel_path(part_index),
            state="recording",
            discontinuity_seq=discontinuity_seq,
        )
        self._hls_part_index[session_id] = part_index
        self._hls_discontinuity_seq[session_id] = discontinuity_seq
        return proc

    _STREAMING_PLATFORMS = frozenset({"douyin", "bilibili"})

    def _use_streaming_pipeline(self, session_id: str | None = None) -> bool:
        if session_id:
            row = self._sessions.get(session_id)
            if row and row.pipeline_mode:
                return (
                    row.pipeline_mode == "streaming"
                    and self._cfg.live.streaming_stt.enabled
                    and self._platform in self._STREAMING_PLATFORMS
                )
        return (
            self._cfg.live.is_streaming_pipeline()
            and self._platform in self._STREAMING_PLATFORMS
        )

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
        self._state.record_pipeline_event(
            session_id=session_id,
            stage="streaming_stt",
            status="degraded",
            detail=detail,
        )

    def _handle_stt_disconnect(self, row, creator) -> None:
        session_id = row.id
        stt = self._stt_sessions.pop(session_id, None)
        if stt is not None:
            offset = stt.writer.segment_end_sec()
            try:
                stt.stop(timeout=5, finalize=False)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_stt_stop_on_disconnect_failed",
                    session_id=session_id,
                    error=str(exc),
                )
        else:
            offset = self._partial_timeline_offset_sec(row)

        if not self._cfg.live.streaming_stt.reconnect:
            self._mark_streaming_degraded(session_id, reason="stt_disconnect")
            return

        stream_url = self._resolve_live_stream_url(
            creator,
            room_id=row.room_id,
        )
        if stream_url:
            self._stream_urls[session_id] = stream_url

        if not stream_url or not row.temp_path:
            self._mark_streaming_degraded(
                session_id,
                reason="stt_reconnect_no_url",
            )
            return

        try:
            anchor = self._transcript_anchor(session_id, row.temp_path)
            new_stt = self._build_streaming_stt_session(
                session_id,
                creator=creator,
                stream_url=stream_url,
                media_path=anchor,
                offset_sec=offset,
            )
            with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                new_stt.start()
            self._stt_sessions[session_id] = new_stt
            self._state.record_pipeline_event(
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
        use_hls = self._use_hls_recording(session_id)
        proc_old = self._processes.pop(session_id, None)
        if proc_old is not None:
            if use_hls:
                stop_hls_recorder(
                    proc_old, timeout=self._cfg.live.ffmpeg_stop_timeout_sec
                )
            else:
                stop_process(proc_old, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif self._process_alive(old_pid):
            os.kill(old_pid, 15)

        session_dir = self._resolve_session_dir(session_id)
        if use_hls and session_dir is not None:
            self._close_hls_part_if_any(session_id, session_dir)

        stt = self._stt_sessions.pop(session_id, None)
        next_offset: float | None = None
        streaming_merge = (
            self._use_streaming_pipeline(session_id)
            and session_id not in self._streaming_legacy_finalize
        )
        if stt is not None:
            if streaming_merge:
                next_offset = self._checkpoint_streaming_stt(session_id, stt)
            try:
                stt.stop(timeout=5, finalize=False)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_stt_stop_on_reconnect_failed",
                    session_id=session_id,
                    error=str(exc),
                )
            if not streaming_merge:
                self._mark_streaming_degraded(session_id, reason="ffmpeg_reconnect")

        if not use_hls:
            self._state.append_segment_path(session_id, temp_path)
        attempt = self._state.increment_reconnect_attempts(session_id)

        sess_row = self._sessions.get(session_id)
        room_id = sess_row.room_id if sess_row else None
        stream_url = self._resolve_live_stream_url(creator, room_id=room_id)
        if not stream_url:
            log.warning(
                "live_reconnect_stream_failed",
                session_id=session_id,
                error="empty stream url after resolve",
            )
            self._finalize_recording(session_id, temp_path, old_pid)
            return None

        if use_hls and session_dir is not None:
            repo = SegmentManifestRepo(self._conn)
            next_index = max(repo.max_part_index(session_id), 1) + 1
            discontinuity_seq = self._hls_discontinuity_seq.get(session_id, 0) + 1
            rotate_hls_after_reconnect(
                conn=self._conn,
                session_id=session_id,
                session_dir=session_dir,
                next_index=next_index,
                discontinuity_seq=discontinuity_seq,
            )
            new_proc = self._spawn_hls_recording(
                session_id=session_id,
                stream_url=stream_url,
                session_dir=session_dir,
                part_index=next_index,
                discontinuity_seq=discontinuity_seq,
            )
            master_path = str(session_dir / "master.m3u8")
            self._state.update_recording_state(
                session_id,
                ffmpeg_pid=new_proc.pid,
                temp_path=master_path,
                session_dir=str(session_dir),
            )
            self._processes[session_id] = new_proc
            self._stream_urls[session_id] = stream_url
            time.sleep(FFMPEG_STARTUP_GRACE_SEC)
            if streaming_merge:
                anchor = self._transcript_anchor(session_id, temp_path)
                offset = next_offset
                if offset is None:
                    sess = self._sessions.get(session_id)
                    offset = (
                        self._partial_timeline_offset_sec(sess) if sess else 0.0
                    )
                try:
                    new_stt = self._build_streaming_stt_session(
                        session_id,
                        creator=creator,
                        stream_url=stream_url,
                        media_path=anchor,
                        offset_sec=offset,
                    )
                    with stage_event(
                        self._conn, session_id=session_id, stage="streaming_stt"
                    ):
                        new_stt.start()
                    self._stt_sessions[session_id] = new_stt
                    self._state.record_pipeline_event(
                        session_id=session_id,
                        stage="streaming_stt",
                        status="reconnected",
                        detail={
                            "reason": "hls_reconnect",
                            "offset_sec": offset,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "streaming_stt_reconnect_after_hls_failed",
                        session_id=session_id,
                        error=str(exc),
                    )
                    self._mark_streaming_degraded(
                        session_id,
                        reason="hls_reconnect_stt_failed",
                        error=str(exc),
                    )
            log.info(
                "live_recording_reconnected_hls",
                session_id=session_id,
                attempt=attempt,
                part_index=next_index,
            )
            return None

        live_dir = self._ws / "creators" / creator.sec_uid / "live"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        new_temp = live_dir / f"{stamp}_r{attempt}.flv"
        new_proc = record_stream_copy(
            ffmpeg=self._cfg.live.ffmpeg_path,
            stream_url=stream_url,
            output_path=new_temp,
        )
        self._state.update_recording_state(
            session_id,
            ffmpeg_pid=new_proc.pid,
            temp_path=str(new_temp),
        )
        self._processes[session_id] = new_proc
        self._stream_urls[session_id] = stream_url
        time.sleep(FFMPEG_STARTUP_GRACE_SEC)
        if streaming_merge:
            anchor = self._transcript_anchor(session_id, temp_path)
            offset = next_offset
            if offset is None:
                sess = self._sessions.get(session_id)
                offset = self._partial_timeline_offset_sec(sess) if sess else 0.0
            try:
                new_stt = self._build_streaming_stt_session(
                    session_id,
                    creator=creator,
                    stream_url=stream_url,
                    media_path=anchor,
                    offset_sec=offset,
                )
                with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                    new_stt.start()
                self._stt_sessions[session_id] = new_stt
                self._state.record_pipeline_event(
                    session_id=session_id,
                    stage="streaming_stt",
                    status="reconnected",
                    detail={"reason": "ffmpeg_reconnect", "offset_sec": offset},
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_stt_reconnect_after_ffmpeg_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                self._mark_streaming_degraded(
                    session_id,
                    reason="ffmpeg_reconnect_stt_failed",
                    error=str(exc),
                )
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
        ProbeExecutionGuard.record_violation("_start_recording")
        live_dir = self._ws / "creators" / sec_uid / "live"
        live_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        use_hls = (
            self._cfg.live.is_streaming_pipeline() and self._cfg.live.uses_hls_media()
        )
        if use_hls:
            session_dir = live_dir / stamp
            session_dir.mkdir(parents=True, exist_ok=True)
            temp_path = session_dir / "master.m3u8"
            transcript_anchor = session_dir / f"{stamp}.flv"
        else:
            session_dir = None
            temp_path = live_dir / f"{stamp}.flv"
            transcript_anchor = temp_path

        session_id = self._state.create_session(
            creator_id=creator_id,
            room_id=room_id,
            temp_path=str(temp_path),
            ffmpeg_pid=None,
            platform_live_started_at=live_info.platform_live_started_at,
            pipeline_mode=self._cfg.live.snapshot_pipeline_mode(),
            session_dir=str(session_dir) if session_dir else None,
        )
        try:
            return self._start_recording_after_session(
                session_id,
                creator_id=creator_id,
                sec_uid=sec_uid,
                room_id=room_id,
                live_info=live_info,
                temp_path=temp_path,
                transcript_anchor=transcript_anchor,
                session_dir=session_dir,
            )
        except Exception as exc:
            self._state.update_status(
                session_id,
                status="failed",
                error=str(exc)[:500],
                ended=True,
            )
            self._state.enqueue_creator_updated(creator_id)
            raise

    def _start_recording_after_session(
        self,
        session_id: str,
        *,
        creator_id: str,
        sec_uid: str,
        room_id: str | None,
        live_info: LiveRoomInfo,
        temp_path: Path,
        transcript_anchor: Path | None = None,
        session_dir: Path | None = None,
    ) -> dict:
        self._state.record_pipeline_event(
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

        use_streaming = self._use_streaming_pipeline(session_id)
        use_hls = use_streaming and (
            session_dir is not None or self._cfg.live.uses_hls_media()
        )
        anchor_path = self._normalize_transcript_anchor(
            Path(transcript_anchor or temp_path)
        )
        stt_session: StreamingSttSession | None = None
        if use_streaming:
            self._streaming_transcript_anchor[session_id] = anchor_path
            self._stt_checkpoint_counter[session_id] = 0
            creator_row = self._creators.get(creator_id)
            if creator_row is None:
                raise ValueError(f"creator not found: {creator_id}")
            stt_session = self._build_streaming_stt_session(
                session_id,
                creator=creator_row,
                stream_url=stream_url,
                media_path=anchor_path,
            )

        if use_hls:
            hls_dir = session_dir or temp_path.parent
            proc = self._spawn_hls_recording(
                session_id=session_id,
                stream_url=stream_url,
                session_dir=hls_dir,
                part_index=1,
            )
        else:
            proc = record_stream_copy(
                ffmpeg=self._cfg.live.ffmpeg_path,
                stream_url=stream_url,
                output_path=temp_path,
            )
        self._state.update_recording_state(
            session_id,
            ffmpeg_pid=proc.pid,
            temp_path=str(temp_path),
            session_dir=str(session_dir) if session_dir else None,
        )
        self._processes[session_id] = proc

        time.sleep(FFMPEG_STARTUP_GRACE_SEC)
        exit_code = proc.poll()
        if exit_code is not None:
            err_tail = ""
            if proc.stderr is not None:
                err_tail = proc.stderr.read().decode(errors="replace")[-500:]
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
            self._processes.pop(session_id, None)
            err_parts = [f"ffmpeg_exited_early:{exit_code}:{err_tail}"]
            self._state.update_status(
                session_id,
                status="failed",
                error="; ".join(err_parts),
                ended=True,
            )
            log.error(
                "live_start_failed",
                session_id=session_id,
                exit_code=exit_code,
                stt_failed=False,
            )
            creator = self._creators.get(creator_id)
            if creator:
                label = creator_label(creator)
                body = f"ffmpeg 启动失败（exit {exit_code}）\nroom_id: {room_id or '—'}"
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
        self._state.record_pipeline_event(
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
                    creator_id=creator_id,
                    session_id=session_id,
                )
            )

        stt_failed = False
        stt_error = ""
        if stt_session is not None:
            try:
                with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                    stt_session.start()
                self._stt_sessions[session_id] = stt_session
                self._state.update_status(session_id, transcribe_status="streaming")
                self._state.record_pipeline_event(
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
                self._state.record_pipeline_event(
                    session_id=session_id,
                    stage="streaming_stt",
                    status="failed",
                    detail={"error": stt_error},
                )

        if stt_failed:
            if stt_session is not None and session_id in self._stt_sessions:
                self._stt_sessions.pop(session_id, None)
                try:
                    stt_session.stop(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
            self._mark_streaming_degraded(
                session_id,
                reason="stt_start_failed",
                error=stt_error or None,
            )
            return {
                "session_id": session_id,
                "temp_path": str(temp_path),
                "pid": proc.pid,
            }

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
            self._flv_stall_polls.pop(row.id, None)
            return False
        temp_path = row.temp_path
        if temp_path and self._flv_file_growing(row.id, temp_path):
            self._flv_stall_polls.pop(row.id, None)
            log.debug(
                "live_offline_ignored_flv_growing",
                session_id=row.id,
                creator_id=row.creator_id,
            )
            return True
        stall = self._flv_stall_polls.get(row.id, 0) + 1
        self._flv_stall_polls[row.id] = stall
        stall_limit = max(1, self._cfg.live.offline_flv_stall_polls)
        if stall >= stall_limit:
            log.info(
                "live_offline_flv_stalled",
                session_id=row.id,
                creator_id=row.creator_id,
                stall_polls=stall,
            )
            return False
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
        row = self._sessions.get(session_id)
        if row and row.session_dir:
            return self._hls_media_growing(session_id, Path(row.session_dir))
        path = Path(temp_path)
        if not path.is_file():
            return False
        size = path.stat().st_size
        prev = self._flv_size_snapshots.get(session_id)
        self._flv_size_snapshots[session_id] = size
        if prev is None:
            return size > 4096
        return size > prev

    def _hls_media_growing(self, session_id: str, session_dir: Path) -> bool:
        parts_dir = session_dir / "parts"
        if not parts_dir.is_dir():
            master = session_dir / "master.m3u8"
            if master.is_file():
                size = master.stat().st_size
                prev = self._flv_size_snapshots.get(session_id)
                self._flv_size_snapshots[session_id] = size
                return prev is None or size > prev
            return False
        segments = sorted(parts_dir.glob("seg-*.m4s"))
        if not segments:
            return False
        latest = segments[-1]
        size = latest.stat().st_size
        key = f"{session_id}:{latest.name}"
        prev = self._flv_size_snapshots.get(key)
        self._flv_size_snapshots[key] = size
        if prev is None:
            return size > 0
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
        use_streaming_finalize = (
            self._use_streaming_pipeline(session_id)
            and session_id not in self._streaming_legacy_finalize
        )
        if use_streaming_finalize:
            return self._finalize_recording_streaming(session_id, temp_path, pid)
        return self._finalize_recording_legacy(session_id, temp_path, pid)

    def _finalize_recording_streaming(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        if self._use_hls_recording(session_id):
            return self._finalize_recording_streaming_hls(
                session_id, temp_path, pid
            )
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            stop_process(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif pid and self._process_alive(pid):
            stop_pid(pid, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)

        stt = self._stt_sessions.pop(session_id, None)
        self._stream_urls.pop(session_id, None)
        transcript_ok = False
        if not temp_path:
            self._state.update_status(
                session_id, status="failed", error="missing temp_path", ended=True
            )
            self._clear_streaming_session_state(session_id)
            return None

        anchor = self._transcript_anchor(session_id, temp_path)
        segment_paths = [Path(p) for p in self._sessions.list_segment_paths(session_id)]
        current = Path(temp_path)
        flv_sources = segment_paths + [current]
        valid_flvs = [p for p in flv_sources if p.is_file() and p.stat().st_size > 0]
        if not valid_flvs:
            self._state.update_status(
                session_id,
                status="failed",
                error="empty_recording",
                ended=True,
            )
            self._clear_streaming_session_state(session_id)
            log.warning("live_recording_empty", session_id=session_id)
            return None

        output_flv = anchor
        try:
            if len(valid_flvs) > 1:
                merged_tmp = anchor.with_name(f"{anchor.stem}.merged.flv")
                concat_to_flv(
                    ffmpeg=self._cfg.live.ffmpeg_path,
                    sources=valid_flvs,
                    dst=merged_tmp,
                )
                merged_tmp.replace(anchor)
                for path in valid_flvs:
                    if path.resolve() != anchor.resolve():
                        path.unlink(missing_ok=True)
            elif valid_flvs[0].resolve() != anchor.resolve():
                valid_flvs[0].replace(anchor)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "streaming_flv_merge_failed",
                session_id=session_id,
                error=str(exc),
            )
            output_flv = valid_flvs[-1]

        try:
            with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                trailing = None
                if stt is not None:
                    stt.stop(
                        timeout=self._cfg.live.ffmpeg_stop_timeout_sec,
                        finalize=False,
                    )
                    trailing = stt.writer.current_segments()
                checkpoints = list_segment_checkpoints(anchor)
                if checkpoints or trailing:
                    paths = merge_transcript_checkpoints(
                        anchor,
                        checkpoints,
                        trailing_segments=trailing,
                        engine="deepgram",
                        model=self._cfg.transcribe.deepgram.model,
                    )
                    transcript_ok = paths is not None
                elif anchor.with_suffix(".transcript.json").is_file():
                    transcript_ok = True
                elif seal_partial_transcript(anchor) is not None:
                    transcript_ok = True
            self._state.record_pipeline_event(
                session_id=session_id,
                stage="streaming_stt",
                status="completed" if transcript_ok else "failed",
            )
        except Exception as exc:  # noqa: BLE001
            self._state.record_pipeline_event(
                session_id=session_id,
                stage="streaming_stt",
                status="failed",
                detail={"error": str(exc)},
            )
            log.exception("streaming_stt_finalize_failed", session_id=session_id)

        media_path = output_flv
        if self._cfg.live.should_remux_on_complete():
            mp4 = output_flv.with_suffix(".mp4")
            try:
                with stage_event(self._conn, session_id=session_id, stage="remux"):
                    remux_to_mp4(
                        ffmpeg=self._cfg.live.ffmpeg_path,
                        src=output_flv,
                        dst=mp4,
                    )
                media_path = mp4
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "streaming_remux_failed",
                    session_id=session_id,
                    error=str(exc),
                )
        else:
            self._state.record_pipeline_event(
                session_id=session_id,
                stage="remux",
                status="skipped",
            )

        if transcript_ok:
            index_transcript_safe(self._cfg, anchor.with_suffix(".transcript.json"))

        self._clear_streaming_session_state(session_id)
        self._state.update_status(
            session_id,
            status="completed",
            local_path=str(media_path),
            transcribe_status="completed" if transcript_ok else "failed",
            ended=True,
        )
        self._state.clear_pid(session_id)
        log.info(
            "live_recording_completed_streaming",
            session_id=session_id,
            path=str(media_path),
        )

        session = self._sessions.get(session_id)
        if not session:
            return None
        creator = self._creators.get(session.creator_id)
        if not creator:
            return {"session_id": session_id, "path": str(media_path)}

        job_id = self._jobs.enqueue(
            session_id=session_id,
            creator_id=creator.id,
            mp4_path=str(media_path),
        )
        self._state.refresh_creator_manifest(
            sec_uid=creator.sec_uid,
            workspace=self._ws,
            platform=creator.platform,
        )
        label = creator_label(creator)
        self._notify.emit(
            NotifyEvent(
                kind=EventKind.RECORDING_COMPLETED,
                title=label,
                body=f"直播录制已完成\n{media_path.name}\n{media_path.parent}",
            )
        )
        if transcript_ok:
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.TRANSCRIBE_COMPLETED,
                    title=label,
                    body=f"直播转录完成（deepgram streaming）\n{media_path.name}",
                )
            )
        return {
            "session_id": session_id,
            "path": str(media_path),
            "creator_id": creator.id,
            "job_id": job_id,
        }

    def _finalize_recording_streaming_hls(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        proc = self._processes.pop(session_id, None)
        if proc is not None:
            stop_hls_recorder(proc, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        elif pid and self._process_alive(pid):
            stop_pid(pid, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)

        stt = self._stt_sessions.pop(session_id, None)
        self._stream_urls.pop(session_id, None)

        session_dir = self._resolve_session_dir(session_id)
        if session_dir is None and temp_path:
            session_dir = Path(temp_path).parent

        if session_dir is None:
            self._state.update_status(
                session_id, status="failed", error="missing session_dir", ended=True
            )
            self._clear_streaming_session_state(session_id)
            return None

        seg_watcher = get_segment_watcher()
        if seg_watcher is not None:
            seg_watcher.force_close_session(self._conn, session_id, session_dir)
        else:
            self._close_hls_part_if_any(session_id, session_dir)
        finalize_hls_endlist(session_dir)
        manifest_repo = SegmentManifestRepo(self._conn)
        manifest_repo.export_json(session_id, session_dir=session_dir)

        anchor = self._transcript_anchor(session_id, temp_path)
        transcript_ok = False
        try:
            with stage_event(self._conn, session_id=session_id, stage="streaming_stt"):
                trailing = None
                if stt is not None:
                    stt.stop(
                        timeout=self._cfg.live.ffmpeg_stop_timeout_sec,
                        finalize=False,
                    )
                    trailing = stt.writer.current_segments()
                checkpoints = list_segment_checkpoints(anchor)
                if checkpoints or trailing:
                    paths = merge_transcript_checkpoints(
                        anchor,
                        checkpoints,
                        trailing_segments=trailing,
                        engine="deepgram",
                        model=self._cfg.transcribe.deepgram.model,
                    )
                    transcript_ok = paths is not None
                elif anchor.with_suffix(".transcript.json").is_file():
                    transcript_ok = True
                elif seal_partial_transcript(anchor) is not None:
                    transcript_ok = True
            self._state.record_pipeline_event(
                session_id=session_id,
                stage="streaming_stt",
                status="completed" if transcript_ok else "failed",
            )
        except Exception as exc:  # noqa: BLE001
            self._state.record_pipeline_event(
                session_id=session_id,
                stage="streaming_stt",
                status="failed",
                detail={"error": str(exc)},
            )
            log.exception("streaming_stt_finalize_failed", session_id=session_id)

        self._state.record_pipeline_event(
            session_id=session_id,
            stage="remux",
            status="skipped",
            detail={"reason": "hls_segments"},
        )

        if transcript_ok:
            index_transcript_safe(self._cfg, anchor.with_suffix(".transcript.json"))

        session = self._sessions.get(session_id)
        creator = self._creators.get(session.creator_id) if session else None
        if creator and self._cfg.aliyundrive.enabled:
            upload_hls_session_sidecars(
                self._cfg,
                self._conn,
                session_id=session_id,
                session_dir=session_dir,
                anchor=anchor,
                creator=creator,
                notify=self._notify,
            )

        media_path = session_dir / "master.m3u8"
        self._clear_streaming_session_state(session_id)
        self._state.update_status(
            session_id,
            status="completed",
            local_path=str(session_dir),
            transcribe_status="completed" if transcript_ok else "failed",
            ended=True,
        )
        self._state.clear_pid(session_id)
        log.info(
            "live_recording_completed_streaming_hls",
            session_id=session_id,
            path=str(media_path),
        )

        if not session:
            return None
        if not creator:
            return {"session_id": session_id, "path": str(media_path)}

        job_id = None
        if self._cfg.summarize.enabled and self._cfg.summarize.on_transcribe_complete:
            job_id = self._jobs.enqueue(
                session_id=session_id,
                creator_id=creator.id,
                mp4_path=str(media_path),
            )
        self._state.refresh_creator_manifest(
            sec_uid=creator.sec_uid,
            workspace=self._ws,
            platform=creator.platform,
        )
        label = creator_label(creator)
        self._notify.emit(
            NotifyEvent(
                kind=EventKind.RECORDING_COMPLETED,
                title=label,
                body=f"直播录制已完成（HLS）\n{session_dir.name}\n{session_dir}",
            )
        )
        if transcript_ok:
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.TRANSCRIBE_COMPLETED,
                    title=label,
                    body=f"直播转录完成（deepgram streaming）\n{session_dir.name}",
                )
            )
        return {
            "session_id": session_id,
            "path": str(media_path),
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
            stop_pid(pid, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)

        stt = self._stt_sessions.pop(session_id, None)
        if stt is not None:
            try:
                stt.stop(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        self._streaming_legacy_finalize.discard(session_id)
        self._stream_urls.pop(session_id, None)

        if not temp_path:
            self._state.update_status(
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
            self._state.update_status(
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

        self._state.update_status(session_id, status="remuxing")
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
            self._state.update_status(
                session_id,
                status="completed",
                local_path=str(mp4),
                ended=True,
            )
            self._state.clear_pid(session_id)
            log.info("live_recording_completed", session_id=session_id, path=str(mp4))
        except Exception as exc:  # noqa: BLE001
            seg_list = ", ".join(str(p) for p in valid_sources)
            self._state.update_status(
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
        self._state.refresh_creator_manifest(
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
