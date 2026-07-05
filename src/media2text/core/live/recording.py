from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import structlog

from media2text.core.live.probe_guard import ProbeExecutionGuard

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
from media2text.core.ffmpeg import (
    record_stream_copy,
    stop_pid,
    stop_process,
)
# Re-export finalize deps for unit test patch paths (logic in session_finalize.py)
from media2text.core.archive.hook import index_transcript_safe  # noqa: F401
from media2text.core.cloud.live_upload import upload_hls_session_sidecars  # noqa: F401
from media2text.core.ffmpeg import concat_to_flv, concat_to_mp4, remux_to_mp4  # noqa: F401
from media2text.core.live.hls_recorder import (
    HLS_FFMPEG_LOG,
    append_discontinuity_to_playlist,
    part_rel_path,
    read_hls_ffmpeg_log_tail,
    rotate_hls_after_reconnect,
    restore_hls_init_if_empty,
    spawn_hls_recorder,
    stop_hls_recorder,
)
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.live.segment_watcher import (
    enqueue_closed_hls_part,
)
from media2text.core.live.protocol import LivePlatformAdapter
from media2text.core.live.partial_notify import PartialTranscriptNotifier
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.live.streaming_stt import StreamingSttSession
from media2text.core.live.transcript_writer import (
    hls_transcript_anchor_path,
    list_segment_checkpoints,
    partial_segment_end_from_media,
    transcript_sidecar_media_paths,
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
STT_RECONNECT_MIN_SEC = 15.0
HLS_STALL_GRACE_SEC = 45
HLS_STALL_POLL_THRESHOLD = 3
RECONNECT_COOLDOWN_SEC = 120.0


class _RecordingDb:
    """Per-gateway-write DB repos; not stored on watcher (MH-4d)."""

    __slots__ = ("conn", "creators", "sessions", "state", "jobs")

    def __init__(self, conn, cfg: AppConfig, notify: NotifyService) -> None:
        self.conn = conn
        self.creators = CreatorRepo(conn)
        self.sessions = LiveSessionRepo(conn)
        self.state = StateWriter(conn, cfg=cfg, notify=notify)
        self.jobs = PostProcessJobRepo(conn)


class LiveRecordingCore:
    """Live recording facade: runtime side effects + DB via bind(conn) per gateway write."""

    def __init__(
        self,
        cfg: AppConfig,
        *,
        conn=None,
        adapter: LivePlatformAdapter,
        platform: str,
        notify: NotifyService,
        processes: dict[str, subprocess.Popen] | None = None,
        runtime: SessionRuntime | None = None,
    ) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._db: _RecordingDb | None = None
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
        self._hls_stall_polls: dict[str, int] = {}
        self._stall_recovery_inflight: set[str] = set()
        self._stall_reconnect_cooldown_until: dict[str, float] = {}
        self._stt_last_reconnect_mono: dict[str, float] = {}
        if conn is not None:
            self.bind(conn)

    def bind(self, conn) -> LiveRecordingCore:
        """Attach short-lived DB repos for a gateway.write callback."""
        self._db = _RecordingDb(conn, self._cfg, self._notify)
        return self

    def _require_db(self) -> _RecordingDb:
        if self._db is None:
            raise RuntimeError("LiveRecordingCore.bind(conn) required before DB access")
        return self._db

    @property
    def _conn(self):
        return self._require_db().conn

    @property
    def _creators(self):
        return self._require_db().creators

    @property
    def _sessions(self):
        return self._require_db().sessions

    @property
    def _state(self):
        return self._require_db().state

    @property
    def _jobs(self):
        return self._require_db().jobs

    @property
    def _processes(self) -> dict[str, subprocess.Popen]:
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
        """Thread-safe live probe: fetch without DB; persist via serial short conn."""
        from media2text.core.live.snapshot import persist_live_probe_result

        live_info, err = self._fetch_live_info(creator)
        if err is not None:
            _kind, payload = err
            persist_live_probe_result(
                self._cfg,
                creator.id,
                None,
                error=str(payload.get("error", _kind)),
            )
            return None, payload
        persist_live_probe_result(self._cfg, creator.id, live_info)
        return live_info, None

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
        """LW-01: resolve stream if needed, create session, spawn ffmpeg.

        Not wrapped by MonitorExecutor playwright_exclusive; see MH-3 notes on
        _run_prepare_live_recording for nested Playwright in stream resolve.
        """
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
        self._write_stt_obs_if_alive(session_id)
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
        self._write_stt_obs_if_alive(session_id)
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
        """Age of the newest transcript output (partial + checkpoints).

        After ``checkpoint_segment()`` deletes ``partial.json``, stall detection
        falls back to segment checkpoint mtimes so it is not permanently blocked.
        """
        if not row.temp_path:
            return None
        anchor = self._streaming_transcript_anchor.get(row.id)
        candidates: list[Path] = []
        if anchor is not None:
            candidates.append(anchor)
        candidates.extend(transcript_sidecar_media_paths(Path(row.temp_path)))
        freshest: float | None = None

        def _consider(path: Path) -> None:
            nonlocal freshest
            if not path.is_file():
                return
            age = time.time() - path.stat().st_mtime
            if freshest is None or age < freshest:
                freshest = age

        for base in candidates:
            _consider(base.with_suffix(".transcript.partial.json"))
            for seg in list_segment_checkpoints(base):
                _consider(seg)
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

    def _resolve_live_stream_url(
        self,
        creator,
        *,
        room_id: str | None,
        web_rid: str | None = None,
    ) -> str | None:
        if room_id:
            try:
                live_info = self._adapter.get_live_room(sec_uid=creator.sec_uid)
                if live_info.room_id == room_id:
                    if live_info.stream_flv_url:
                        return live_info.stream_flv_url
                    if not web_rid:
                        web_rid = live_info.web_rid
            except Exception as exc:  # noqa: BLE001
                log.debug(
                    "resolve_live_stream_prefetch_failed",
                    creator_id=creator.id,
                    room_id=room_id,
                    error=str(exc),
                )
            try:
                url = self._adapter.resolve_stream_url(
                    room_id=room_id,
                    sec_uid=creator.sec_uid,
                    web_rid=web_rid,
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
                    web_rid=live_info.web_rid,
                )
            return url or None
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "resolve_live_stream_url_failed",
                creator_id=creator.id,
                error=str(exc),
            )
            return None

    def _in_reconnect_cooldown(self, session_id: str) -> bool:
        until = self._stall_reconnect_cooldown_until.get(session_id, 0.0)
        return time.monotonic() < until

    def _mark_reconnect_cooldown(self, session_id: str) -> None:
        self._stall_reconnect_cooldown_until[session_id] = (
            time.monotonic() + RECONNECT_COOLDOWN_SEC
        )

    def _hls_stall_grace_sec(self) -> float:
        seg = float(self._cfg.live.media.segment_duration_sec)
        return min(max(seg * 0.15, HLS_STALL_GRACE_SEC), 180.0)

    def _hls_stall_poll_threshold(self) -> int:
        seg = self._cfg.live.media.segment_duration_sec
        if seg >= 300:
            return max(HLS_STALL_POLL_THRESHOLD, int(seg / 60))
        return HLS_STALL_POLL_THRESHOLD

    def _hls_within_segment_quiet_period(self, session_dir: Path) -> bool:
        """Latest fmp4 part may stop growing between long HLS segment rollovers."""
        seg = float(self._cfg.live.media.segment_duration_sec)
        parts_dir = session_dir / "parts"
        if not parts_dir.is_dir():
            return False
        segments = sorted(parts_dir.glob("seg-*.m4s"))
        if not segments:
            return False
        latest = segments[-1]
        age = time.time() - latest.stat().st_mtime
        return age < seg * 1.05

    def _maybe_recover_stalled_stream(
        self,
        row,
        creator,
        *,
        ffmpeg_alive: bool,
        stt_alive: bool | None,
    ) -> bool:
        """Return True when a stall reconnect was triggered."""
        if row.status != "recording":
            return False
        if row.id in self._streaming_legacy_finalize:
            return False
        if not self._use_streaming_pipeline(row.id):
            return False
        if row.id in self._stall_recovery_inflight:
            return False
        if self._in_reconnect_cooldown(row.id):
            return False
        attempts = row.reconnect_attempts or 0
        if attempts >= self._cfg.live.max_reconnect_attempts:
            return False

        stale_sec = self._transcript_partial_age_sec(row)
        if stale_sec is None or stale_sec < TRANSCRIPT_STALL_RECONNECT_SEC:
            return False

        if row.temp_path is None:
            return False

        tasks = MonitorTaskRepo(self._conn)
        if tasks.has_active_dedupe(f"reconnect_rec:{row.id}") or tasks.has_active_dedupe(
            f"reconnect_stt:{row.id}"
        ):
            return False

        self._stall_recovery_inflight.add(row.id)
        triggered = False
        try:
            if not ffmpeg_alive:
                if row.ffmpeg_pid is None:
                    return False
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
                self._mark_reconnect_cooldown(row.id)
                return True

            if row.ffmpeg_pid is None:
                return False

            if stt_alive is False:
                log.warning(
                    "live_stt_stall_reconnect",
                    session_id=row.id,
                    transcript_stale_sec=round(stale_sec, 1),
                    mode="stt_only",
                )
                self._handle_stt_disconnect(row, creator)
                self._mark_reconnect_cooldown(row.id)
                return True

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
            self._mark_reconnect_cooldown(row.id)
            triggered = True
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_stream_stall_reconnect_failed",
                session_id=row.id,
                error=str(exc),
            )
        finally:
            self._stall_recovery_inflight.discard(row.id)
        return triggered

    def _hls_recording_healthy(self, session_id: str, session_dir: Path) -> bool:
        if self._hls_within_segment_quiet_period(session_dir):
            return True
        master = session_dir / "master.m3u8"
        if master.is_file():
            msize = master.stat().st_size
            mkey = f"{session_id}:master"
            mprev = self._flv_size_snapshots.get(mkey)
            self._flv_size_snapshots[mkey] = msize
            if mprev is not None and msize > mprev:
                return True
        if self._hls_media_growing(session_id, session_dir):
            return True
        log_path = session_dir / HLS_FFMPEG_LOG
        if log_path.is_file():
            size = log_path.stat().st_size
            key = f"{session_id}:hlslog"
            prev = self._flv_size_snapshots.get(key)
            self._flv_size_snapshots[key] = size
            if prev is not None and size > prev:
                return True
        return False

    def _maybe_recover_stalled_hls(
        self,
        row,
        creator,
        *,
        ffmpeg_alive: bool,
        stt_alive: bool | None,
    ) -> None:
        if not self._use_hls_recording(row.id):
            return
        if row.status != "recording" or not ffmpeg_alive:
            return
        if stt_alive is not True:
            return
        if row.id in self._streaming_legacy_finalize:
            return
        if row.id in self._stall_recovery_inflight:
            return
        if self._in_reconnect_cooldown(row.id):
            return
        attempts = row.reconnect_attempts or 0
        if attempts >= self._cfg.live.max_reconnect_attempts:
            return
        session_dir = self._resolve_session_dir(row.id)
        if session_dir is None:
            return
        if self._recording_age_sec(row.started_at) < self._hls_stall_grace_sec():
            return
        if self._hls_recording_healthy(row.id, session_dir):
            self._hls_stall_polls.pop(row.id, None)
            return
        stall = self._hls_stall_polls.get(row.id, 0) + 1
        self._hls_stall_polls[row.id] = stall
        if stall < self._hls_stall_poll_threshold():
            return
        tasks = MonitorTaskRepo(self._conn)
        if tasks.has_active_dedupe(f"reconnect_rec:{row.id}"):
            return
        self._stall_recovery_inflight.add(row.id)
        try:
            log.warning(
                "live_hls_stall_reconnect",
                session_id=row.id,
                stall_polls=stall,
                mode="hls_only",
            )
            self._reconnect_hls_ffmpeg_only(row.id, creator)
            self._mark_reconnect_cooldown(row.id)
            self._hls_stall_polls.pop(row.id, None)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_hls_stall_reconnect_failed",
                session_id=row.id,
                error=str(exc),
            )
        finally:
            self._stall_recovery_inflight.discard(row.id)

    def _reconnect_hls_ffmpeg_only(self, session_id: str, creator) -> None:
        row = self._sessions.get(session_id)
        if row is None or row.ffmpeg_pid is None:
            return
        old_pid = row.ffmpeg_pid
        proc_old = self._processes.pop(session_id, None)
        if proc_old is not None:
            stop_hls_recorder(
                proc_old, timeout=self._cfg.live.ffmpeg_stop_timeout_sec
            )
        elif self._process_alive(old_pid):
            stop_pid(old_pid, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)

        session_dir = self._resolve_session_dir(session_id)
        if session_dir is None:
            return

        part_index = self._resolve_hls_part_index(session_id, session_dir) or 1
        seg_path = session_dir / part_rel_path(part_index)
        has_seg = seg_path.is_file() and seg_path.stat().st_size > 0
        discontinuity_seq = self._hls_discontinuity_seq.get(session_id, 0)
        next_index = part_index
        if has_seg:
            self._close_hls_part_if_any(session_id, session_dir)
            next_index = part_index + 1
            discontinuity_seq += 1
            rotate_hls_after_reconnect(
                conn=self._conn,
                session_id=session_id,
                session_dir=session_dir,
                next_index=next_index,
                discontinuity_seq=discontinuity_seq,
            )
        elif (session_dir / "master.m3u8").is_file():
            append_discontinuity_to_playlist(session_dir)

        stream_url = self._resolve_live_stream_url(creator, room_id=row.room_id)
        if not stream_url:
            raise RecordingError("hls_reconnect_no_stream_url")

        attempt = self._state.increment_reconnect_attempts(session_id)

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
        self._hls_discontinuity_seq[session_id] = discontinuity_seq
        time.sleep(FFMPEG_STARTUP_GRACE_SEC)
        restore_hls_init_if_empty(session_dir)
        log.info(
            "live_recording_reconnected_hls",
            session_id=session_id,
            attempt=attempt,
            part_index=next_index,
            mode="hls_only",
        )

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
            stream_reconnected = self._maybe_recover_stalled_stream(
                row,
                creator,
                ffmpeg_alive=ffmpeg_alive,
                stt_alive=stt_alive,
            )
            if not stream_reconnected:
                self._maybe_recover_stalled_hls(
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
        """LP-02 delegate: obs-only per active session (finalize via registry/Reconciler)."""
        skip = skip_session_ids or set()
        state = self._state
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
        self._stt_last_reconnect_mono.pop(session_id, None)
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
        idx = self._resolve_hls_part_index(session_id, session_dir)
        if idx is None:
            return
        enqueue_closed_hls_part(
            self._conn,
            session_id=session_id,
            session_dir=session_dir,
            part_index=idx,
            cfg=self._cfg,
        )

    def _resolve_hls_part_index(self, session_id: str, session_dir: Path) -> int | None:
        idx = self._hls_part_index.get(session_id)
        if idx is not None:
            return idx
        repo = SegmentManifestRepo(self._conn)
        recording = [
            p.part_index
            for p in repo.list_parts(session_id)
            if p.state == "recording"
        ]
        if recording:
            return max(recording)
        parts_dir = session_dir / "parts"
        if parts_dir.is_dir():
            max_idx = 0
            for path in parts_dir.glob("seg-*.m4s"):
                if path.is_file() and path.stat().st_size > 0:
                    stem = path.stem  # seg-00001
                    try:
                        max_idx = max(max_idx, int(stem.split("-")[-1]))
                    except ValueError:
                        continue
            if max_idx:
                return max_idx
        mx = repo.max_part_index(session_id)
        return mx if mx > 0 else None

    def _spawn_hls_recording(
        self,
        *,
        session_id: str,
        stream_url: str,
        session_dir: Path,
        part_index: int,
        discontinuity_seq: int = 0,
    ) -> subprocess.Popen:
        existing = self._processes.pop(session_id, None)
        if existing is not None:
            stop_hls_recorder(existing, timeout=self._cfg.live.ffmpeg_stop_timeout_sec)
        proc = spawn_hls_recorder(
            ffmpeg=self._cfg.live.ffmpeg_path,
            stream_url=stream_url,
            session_dir=session_dir,
            segment_sec=self._cfg.live.media.segment_duration_sec,
            encode_cfg=self._cfg.live.encode,
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

    def _write_stt_obs_if_alive(self, session_id: str) -> None:
        stt = self._stt_sessions.get(session_id)
        if stt is None or not stt.is_alive():
            return
        self._state.write_obs(
            session_id,
            ffmpeg_alive=None,
            stt_alive=True,
            still_live=None,
        )

    def _handle_stt_disconnect(self, row, creator) -> None:
        session_id = row.id
        now = time.monotonic()
        last = self._stt_last_reconnect_mono.get(session_id)
        if last is not None and (now - last) < STT_RECONNECT_MIN_SEC:
            return

        stt = self._stt_sessions.pop(session_id, None)
        streaming_merge = (
            self._use_streaming_pipeline(session_id)
            and session_id not in self._streaming_legacy_finalize
        )
        if stt is not None:
            if streaming_merge and stt.writer.segment_count() > 0:
                offset = self._checkpoint_streaming_stt(session_id, stt)
            else:
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
            self._stt_last_reconnect_mono[session_id] = now
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
                    web_rid=live_info.web_rid,
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
            if use_hls and session_dir is not None:
                err_tail = read_hls_ffmpeg_log_tail(session_dir)
            elif proc.stderr is not None:
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
                return self._infer_live_from_recording(row, creator, platform_offline=False)
            raise

        if profile.is_live:
            return True
        if not self._cfg.live.offline_trust_recording_signals:
            return False
        return self._infer_live_from_recording(row, creator, platform_offline=True)

    @staticmethod
    def _is_hls_session(row) -> bool:
        temp_path = row.temp_path or ""
        if temp_path.endswith(".m3u8"):
            return True
        session_dir = getattr(row, "session_dir", None)
        if not session_dir:
            return False
        base = Path(session_dir)
        return (base / "master.m3u8").is_file() or (base / "parts").is_dir()

    def _infer_live_from_recording(
        self, row, creator, *, platform_offline: bool = False
    ) -> bool:
        pid = row.ffmpeg_pid
        if pid is None or not self._process_alive(pid):
            self._flv_stall_polls.pop(row.id, None)
            return False
        temp_path = row.temp_path
        if temp_path and self._flv_file_growing(row.id, temp_path):
            if platform_offline and self._is_hls_session(row):
                log.debug(
                    "live_offline_hls_tail_ignored_for_growth",
                    session_id=row.id,
                    creator_id=row.creator_id,
                )
            else:
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
        from media2text.core.live.session_finalize import finalize_recording

        return finalize_recording(
            self, self._conn, session_id, temp_path, pid
        )

    def _finalize_recording_streaming_hls(
        self, session_id: str, temp_path: str | None, pid: int
    ) -> dict | None:
        from media2text.core.live.session_finalize import finalize_recording_streaming_hls

        return finalize_recording_streaming_hls(
            self, self._conn, session_id, temp_path, pid
        )
