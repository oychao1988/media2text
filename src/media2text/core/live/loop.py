"""LiveLoop inline prepare/finalize/reconnect decisions (MLS-8 / P3-2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from media2text.core.config import AppConfig
from media2text.core.desktop.auto_record import effective_auto_record
from media2text.core.live.task_reconciler import (
    _ffmpeg_obs_alive,
    _is_streaming_session,
    _load_snapshots,
    _obs_false,
    _obs_true,
    _offline_confirmed,
)
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, get_write_gateway

if TYPE_CHECKING:
    from media2text.core.monitor.watcher import MonitorWatcher

log = structlog.get_logger()


@dataclass
class _InlinePlan:
    prepare_creator_ids: list[str] = field(default_factory=list)
    finalize_session_ids: list[str] = field(default_factory=list)
    cancel_finalize_keys: list[str] = field(default_factory=list)
    reconnect_recording_ids: list[str] = field(default_factory=list)
    reconnect_stt_ids: list[str] = field(default_factory=list)
    start_stt_ids: list[str] = field(default_factory=list)


def _collect_inline_plan(cfg: AppConfig, conn) -> _InlinePlan:
    plan = _InlinePlan()
    creators = CreatorRepo(conn).list_monitored()
    snapshots = _load_snapshots(conn)
    sessions = LiveSessionRepo(conn)
    tasks = MonitorTaskRepo(conn)

    for creator in creators:
        snap = snapshots.get(creator.id)
        active = sessions.get_active_for_creator(creator.id)

        if (
            snap
            and snap.is_live == 1
            and effective_auto_record(creator, cfg)
            and not active
        ):
            plan.prepare_creator_ids.append(creator.id)

        if not active:
            continue
        row = active
        finalize_key = f"finalize:{row.id}"

        if _obs_true(row.obs_still_live) and tasks.has_active_dedupe(finalize_key):
            plan.cancel_finalize_keys.append(finalize_key)
        elif _offline_confirmed(cfg, row):
            plan.finalize_session_ids.append(row.id)

        if row.status != "recording":
            continue

        still_live = _obs_true(row.obs_still_live)
        ffmpeg_alive = _ffmpeg_obs_alive(row)

        if not ffmpeg_alive and still_live:
            plan.reconnect_recording_ids.append(row.id)

        if not _is_streaming_session(cfg, row):
            continue

        stt_streaming = (row.transcribe_status or "").lower() == "streaming"

        if _obs_false(row.obs_stt_alive) and ffmpeg_alive:
            plan.reconnect_stt_ids.append(row.id)
        elif (
            ffmpeg_alive
            and not stt_streaming
            and not tasks.has_active_dedupe(f"start_stt:{row.id}")
            and not _obs_false(row.obs_stt_alive)
        ):
            plan.start_stt_ids.append(row.id)

    return plan


def run_live_inline_decisions(cfg: AppConfig, watcher: MonitorWatcher) -> int:
    """Execute reconcile_live RR-01..05 inline via SessionStateMachineRegistry."""
    if not cfg.live.inline_decisions:
        return 0

    ensure_write_gateway_started(cfg)
    registry = watcher.ensure_session_registry()
    gateway = get_write_gateway(cfg)

    plan: _InlinePlan = gateway.read(lambda conn: _collect_inline_plan(cfg, conn))
    actions = 0

    def _cancel_finalize(conn) -> None:
        tasks = MonitorTaskRepo(conn)
        for key in plan.cancel_finalize_keys:
            tasks.cancel_pending(dedupe_key=key)
        for session_id in plan.reconnect_recording_ids:
            tasks.cancel_pending(dedupe_key=f"reconnect_stt:{session_id}")

    if plan.cancel_finalize_keys or plan.reconnect_recording_ids:
        gateway.write(_cancel_finalize, label="live.inline_cancel_tasks")

    for creator_id in plan.prepare_creator_ids:
        try:
            result = registry.run_prepare(creator_id, live_info=None)
            if result.get("started"):
                actions += 1
                log.info("live_inline_prepare", creator_id=creator_id, result=result)
        except Exception as exc:  # noqa: BLE001
            log.warning("live_inline_prepare_failed", creator_id=creator_id, error=str(exc))

    for session_id in plan.finalize_session_ids:
        try:
            result = registry.run_finalize(session_id)
            if result:
                actions += 1
                log.info("live_inline_finalize", session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("live_inline_finalize_failed", session_id=session_id, error=str(exc))

    for session_id in plan.reconnect_recording_ids:
        try:
            result = registry.run_reconnect_recording(session_id)
            if not result.get("skipped"):
                actions += 1
                log.info("live_inline_reconnect_recording", session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "live_inline_reconnect_recording_failed",
                session_id=session_id,
                error=str(exc),
            )

    for session_id in plan.reconnect_stt_ids:
        try:
            result = registry.run_reconnect_streaming_stt(session_id)
            if not result.get("skipped"):
                actions += 1
                log.info("live_inline_reconnect_stt", session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("live_inline_reconnect_stt_failed", session_id=session_id, error=str(exc))

    for session_id in plan.start_stt_ids:
        try:
            result = registry.run_start_streaming_stt(session_id)
            if not result.get("skipped"):
                actions += 1
                log.info("live_inline_start_stt", session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("live_inline_start_stt_failed", session_id=session_id, error=str(exc))

    return actions
