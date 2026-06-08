"""Derive creator live pipeline_phase from session + in-flight tasks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.desktop.status_lights import _ffmpeg_alive
from media2text.core.storage.models import LiveSessionRow, MonitorTaskRow, PostProcessJobRow

_IN_FLIGHT_POST = frozenset({"pending", "running"})
_IN_FLIGHT_TASK = frozenset({"pending", "running"})
_STT_TASK_TYPES = frozenset({"start_streaming_stt", "reconnect_streaming_stt"})


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _offline_confirmed(cfg: AppConfig, row: LiveSessionRow) -> bool:
    if not row.offline_since_at:
        return False
    offline_since = _parse_iso(row.offline_since_at)
    if offline_since is None:
        return False
    elapsed = (datetime.now(timezone.utc) - offline_since).total_seconds()
    return elapsed >= cfg.live.offline_confirm_sec


def _is_streaming_session(cfg: AppConfig, row: LiveSessionRow) -> bool:
    mode = (row.pipeline_mode or cfg.live.effective_pipeline_mode()).strip().lower()
    return mode == "streaming" and cfg.live.streaming_stt.enabled


def _task_targets_session(task: MonitorTaskRow, session_id: str) -> bool:
    if not task.payload_json:
        return task.task_type == "finalize"
    return session_id in task.payload_json


def _has_finalize_task(tasks: Sequence[MonitorTaskRow], session_id: str) -> bool:
    key = f"finalize:{session_id}"
    for task in tasks:
        if task.status not in _IN_FLIGHT_TASK:
            continue
        if task.dedupe_key == key or (
            task.task_type == "finalize" and _task_targets_session(task, session_id)
        ):
            return True
    return False


def _has_stt_task(tasks: Sequence[MonitorTaskRow], session_id: str) -> bool:
    for task in tasks:
        if task.status not in _IN_FLIGHT_TASK:
            continue
        if task.task_type in _STT_TASK_TYPES and _task_targets_session(task, session_id):
            return True
    return False


def _recording_stt_pending(
    cfg: AppConfig,
    row: LiveSessionRow,
    tasks: Sequence[MonitorTaskRow],
) -> bool:
    if not _is_streaming_session(cfg, row):
        return False
    transcribe = (row.transcribe_status or "").strip().lower()
    if transcribe in ("streaming", "completed"):
        return False
    if _has_stt_task(tasks, row.id):
        return True
    return transcribe in ("", "pending")


def derive_pipeline_phase(
    session: LiveSessionRow | None,
    *,
    is_live: bool = False,
    post_jobs: Sequence[PostProcessJobRow] | None = None,
    monitor_tasks: Sequence[MonitorTaskRow] | None = None,
    cfg: AppConfig | None = None,
) -> str:
    """Project pipeline_phase from live_sessions + in-flight monitor/post jobs."""
    jobs = list(post_jobs or [])
    tasks = list(monitor_tasks or [])

    if any(j.status == "failed" for j in jobs):
        if not any(j.status in _IN_FLIGHT_POST for j in jobs):
            return "failed"

    if any(j.status in _IN_FLIGHT_POST for j in jobs):
        return "post_processing"

    if session is None:
        if is_live:
            return "live_unrecorded"
        return "offline"

    if session.status == "failed":
        return "failed"

    if session.status == "completed":
        return "completed"

    if session.status == "remuxing":
        return "finalizing"

    if _has_finalize_task(tasks, session.id):
        return "finalizing"

    if session.offline_since_at:
        if cfg is not None and _offline_confirmed(cfg, session):
            return "finalizing"
        return "offline_pending"

    if session.status == "recording":
        if cfg is not None and _recording_stt_pending(cfg, session, tasks):
            return "recording_stt_pending"
        if _ffmpeg_alive(session) or (session.reconnect_attempts or 0) > 0:
            return "recording"
        return "recording"

    return "offline"


def pipeline_phase_for_creator(
    conn,
    cfg: AppConfig,
    creator_id: str,
    *,
    active: LiveSessionRow | None,
    is_live: bool,
) -> str:
    """Load in-flight jobs/tasks for a creator and derive pipeline_phase."""
    from media2text.core.storage.repos import MonitorTaskRepo, PostProcessJobRepo

    post_jobs = [
        j
        for j in PostProcessJobRepo(conn).list_in_flight(limit=200)
        if j.creator_id == creator_id
    ]
    monitor_tasks = [
        t
        for t in MonitorTaskRepo(conn).list_in_flight(limit=200)
        if t.creator_id == creator_id
    ]
    return derive_pipeline_phase(
        active,
        is_live=is_live,
        post_jobs=post_jobs,
        monitor_tasks=monitor_tasks,
        cfg=cfg,
    )
