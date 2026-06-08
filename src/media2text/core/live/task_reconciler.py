from __future__ import annotations

import json
from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.desktop.auto_record import effective_auto_record
from media2text.core.storage.models import CreatorLiveSnapshotRow, LiveSessionRow
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo


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


def _obs_true(val: int | None) -> bool:
    return val == 1


def _obs_false(val: int | None) -> bool:
    return val == 0


def _load_snapshots(conn) -> dict[str, CreatorLiveSnapshotRow]:
    rows = conn.execute("SELECT * FROM creator_live_snapshots").fetchall()
    return {str(r["creator_id"]): CreatorLiveSnapshotRow(**dict(r)) for r in rows}


def _maybe_ensure(
    tasks: MonitorTaskRepo,
    *,
    log_only: bool,
    creator_id: str,
    task_type: str,
    dedupe_key: str,
    priority: int,
    payload_json: str | None = None,
) -> bool:
    if log_only:
        return True
    return bool(
        tasks.ensure_task(
            creator_id=creator_id,
            task_type=task_type,
            dedupe_key=dedupe_key,
            priority=priority,
            payload_json=payload_json,
        )
    )


def reconcile_live(cfg: AppConfig, conn, *, log_only: bool = False) -> int:
    """RR-01..05: ensure monitor_tasks from snapshots + session obs state."""
    ensured = 0
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
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="prepare_live_recording",
                dedupe_key=f"prepare:{creator.id}",
                priority=1,
            ):
                ensured += 1

        if not active:
            continue
        row = active
        finalize_key = f"finalize:{row.id}"

        if _obs_true(row.obs_still_live) and tasks.has_active_dedupe(finalize_key):
            if not log_only:
                tasks.cancel_pending(dedupe_key=finalize_key)
        elif _offline_confirmed(cfg, row):
            payload = json.dumps({"session_id": row.id})
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="finalize",
                dedupe_key=finalize_key,
                priority=0,
                payload_json=payload,
            ):
                ensured += 1

        if row.status != "recording":
            continue

        session_payload = json.dumps({"session_id": row.id})
        still_live = _obs_true(row.obs_still_live)

        if _obs_false(row.obs_ffmpeg_alive) and still_live:
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="reconnect_recording",
                dedupe_key=f"reconnect_rec:{row.id}",
                priority=6,
                payload_json=session_payload,
            ):
                ensured += 1

        if not _is_streaming_session(cfg, row):
            continue

        ffmpeg_alive = _obs_true(row.obs_ffmpeg_alive)
        stt_streaming = (row.transcribe_status or "").lower() == "streaming"

        if _obs_false(row.obs_stt_alive) and ffmpeg_alive:
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="reconnect_streaming_stt",
                dedupe_key=f"reconnect_stt:{row.id}",
                priority=7,
                payload_json=session_payload,
            ):
                ensured += 1
        elif (
            ffmpeg_alive
            and not stt_streaming
            and not tasks.has_active_dedupe(f"start_stt:{row.id}")
            and not _obs_false(row.obs_stt_alive)
        ):
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="start_streaming_stt",
                dedupe_key=f"start_stt:{row.id}",
                priority=5,
                payload_json=session_payload,
            ):
                ensured += 1

    return ensured


def reconcile_content(cfg: AppConfig, conn, *, log_only: bool = False) -> int:
    """RC-01..03 skeleton: creator due columns land in PR4."""
    _ = cfg, log_only
    ensured = 0
    now = datetime.now(timezone.utc)
    tasks = MonitorTaskRepo(conn)

    for creator in CreatorRepo(conn).list_monitored():
        vod_due = getattr(creator, "vod_due_at", None)
        if vod_due and (due := _parse_iso(vod_due)) and due <= now:
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="sync_catalog",
                dedupe_key=f"sync_catalog:{creator.id}",
                priority=10,
            ):
                ensured += 1

        if creator.platform != "bilibili":
            continue

        archive_due = getattr(creator, "archive_due_at", None)
        if archive_due and (due := _parse_iso(archive_due)) and due <= now:
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="sync_archive",
                dedupe_key=f"sync_archive:{creator.id}",
                priority=10,
            ):
                ensured += 1

        dynamic_due = getattr(creator, "dynamic_due_at", None)
        if dynamic_due and (due := _parse_iso(dynamic_due)) and due <= now:
            if _maybe_ensure(
                tasks,
                log_only=log_only,
                creator_id=creator.id,
                task_type="sync_dynamic",
                dedupe_key=f"sync_dynamic:{creator.id}",
                priority=10,
            ):
                ensured += 1

    return ensured
