"""Live session prepare/poll/offline orchestration (MLS-7 / P3-1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from media2text.core.desktop.auto_record import effective_auto_record
from media2text.core.live.state_writer import StateWriter
from media2text.core.platform.douyin.models import LiveRoomInfo

if TYPE_CHECKING:
    from media2text.core.live.recording import LiveRecordingCore

log = structlog.get_logger()


def prepare_live_recording(
    core: LiveRecordingCore,
    creator_id: str,
    *,
    live_info: LiveRoomInfo | None = None,
) -> dict:
    """LW-01: resolve stream if needed, create session, spawn ffmpeg."""
    if core._sessions.get_active_for_creator(creator_id):
        return {"skipped": "already_recording", "creator_id": creator_id}
    creator = core._creators.get(creator_id)
    if not creator:
        raise ValueError(f"creator_not_found:{creator_id}")
    if creator.platform != core._platform:
        raise ValueError(f"platform_mismatch:{creator.platform}")
    if not effective_auto_record(creator, core._cfg):
        return {"skipped": "auto_record_disabled", "creator_id": creator_id}

    if live_info is None:
        live_info, err = core._fetch_live_info(creator)
        if err is not None:
            _kind, payload = err
            return {"ok": False, "kind": _kind, **payload}
    if live_info is not None:
        core._state.update_snapshot(creator_id, live_info)
    if live_info is None or not live_info.is_live or not live_info.room_id:
        return {"skipped": "not_live", "creator_id": creator_id}

    meta = core.maybe_start_recording(creator, live_info)
    return {"started": meta}


def poll_active_session(
    core: LiveRecordingCore,
    row,
    creator,
    *,
    state: StateWriter,
) -> None:
    """LP-02: obs + offline semantics; inline stall recovery when CDN URL expires."""
    if row.status != "recording" or row.ffmpeg_pid is None:
        return

    pid = row.ffmpeg_pid
    ffmpeg_alive = core._process_alive(pid)

    stt_alive = None
    if core._use_streaming_pipeline(row.id) and row.id not in core._streaming_legacy_finalize:
        stt = core._stt_sessions.get(row.id)
        stt_alive = stt.is_alive() if stt else False

    try:
        still_live = recording_still_live(core, creator, row)
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
        stream_reconnected = core._maybe_recover_stalled_stream(
            row,
            creator,
            ffmpeg_alive=ffmpeg_alive,
            stt_alive=stt_alive,
        )
        if not stream_reconnected:
            core._maybe_recover_stalled_hls(
                row,
                creator,
                ffmpeg_alive=ffmpeg_alive,
                stt_alive=stt_alive,
            )

    try:
        profile = core._adapter.get_live_room(sec_uid=creator.sec_uid)
        state.update_snapshot(creator.id, profile)
    except Exception:  # noqa: BLE001
        pass

    min_offline = core._cfg.live.min_recording_sec_before_offline_end

    if still_live:
        if row.offline_since_at:
            state.clear_offline_since(row.id, creator_id=creator.id)
        return

    if recording_age_sec(core, row.started_at) < min_offline:
        return

    now = datetime.now(timezone.utc)
    if row.offline_since_at is None:
        state.set_offline_since(row.id, now.isoformat(), creator_id=creator.id)


def poll_active_recordings(
    core: LiveRecordingCore,
    *,
    skip_session_ids: set[str] | None = None,
) -> list[dict]:
    """LP-02 delegate: obs-only per active session (finalize via registry/Reconciler)."""
    skip = skip_session_ids or set()
    state = core._state
    for row in core._sessions.list_active():
        if row.id in skip:
            continue
        if row.status != "recording" or row.ffmpeg_pid is None:
            continue
        creator = core._creators.get(row.creator_id)
        if not creator or creator.platform != core._platform:
            continue
        poll_active_session(core, row, creator, state=state)
    return []


def recording_still_live(core: LiveRecordingCore, creator, row) -> bool:
    try:
        profile = core._adapter.get_live_room(sec_uid=creator.sec_uid)
    except Exception:
        if core._cfg.live.offline_trust_recording_signals:
            return infer_live_from_recording(
                core, row, creator, platform_offline=False
            )
        raise

    if profile.is_live:
        return True
    if not core._cfg.live.offline_trust_recording_signals:
        return False
    return infer_live_from_recording(core, row, creator, platform_offline=True)


def is_hls_session(row) -> bool:
    temp_path = row.temp_path or ""
    if temp_path.endswith(".m3u8"):
        return True
    session_dir = getattr(row, "session_dir", None)
    if not session_dir:
        return False
    base = Path(session_dir)
    return (base / "master.m3u8").is_file() or (base / "parts").is_dir()


def infer_live_from_recording(
    core: LiveRecordingCore,
    row,
    creator,
    *,
    platform_offline: bool = False,
) -> bool:
    pid = row.ffmpeg_pid
    if pid is None or not core._process_alive(pid):
        core._flv_stall_polls.pop(row.id, None)
        return False
    temp_path = row.temp_path
    if temp_path and flv_file_growing(core, row.id, temp_path):
        if platform_offline and is_hls_session(row):
            log.debug(
                "live_offline_hls_tail_ignored_for_growth",
                session_id=row.id,
                creator_id=row.creator_id,
            )
        else:
            core._flv_stall_polls.pop(row.id, None)
            log.debug(
                "live_offline_ignored_flv_growing",
                session_id=row.id,
                creator_id=row.creator_id,
            )
            return True
    stall = core._flv_stall_polls.get(row.id, 0) + 1
    core._flv_stall_polls[row.id] = stall
    stall_limit = max(1, core._cfg.live.offline_flv_stall_polls)
    if stall >= stall_limit:
        log.info(
            "live_offline_flv_stalled",
            session_id=row.id,
            creator_id=row.creator_id,
            stall_polls=stall,
        )
        return False
    reflow_getter = getattr(core._adapter, "get_room_reflow", None)
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


def flv_file_growing(core: LiveRecordingCore, session_id: str, temp_path: str) -> bool:
    row = core._sessions.get(session_id)
    if row and row.session_dir:
        return hls_media_growing(core, session_id, Path(row.session_dir))
    path = Path(temp_path)
    if not path.is_file():
        return False
    size = path.stat().st_size
    prev = core._flv_size_snapshots.get(session_id)
    core._flv_size_snapshots[session_id] = size
    if prev is None:
        return size > 4096
    return size > prev


def hls_media_growing(core: LiveRecordingCore, session_id: str, session_dir: Path) -> bool:
    parts_dir = session_dir / "parts"
    if not parts_dir.is_dir():
        master = session_dir / "master.m3u8"
        if master.is_file():
            size = master.stat().st_size
            prev = core._flv_size_snapshots.get(session_id)
            core._flv_size_snapshots[session_id] = size
            return prev is None or size > prev
        return False
    segments = sorted(parts_dir.glob("seg-*.m4s"))
    if not segments:
        return False
    latest = segments[-1]
    size = latest.stat().st_size
    key = f"{session_id}:{latest.name}"
    prev = core._flv_size_snapshots.get(key)
    core._flv_size_snapshots[key] = size
    if prev is None:
        return size > 0
    return size > prev


def recording_age_sec(core: LiveRecordingCore, started_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return core._cfg.live.min_recording_sec_before_offline_end
    return (datetime.now(timezone.utc) - started).total_seconds()
