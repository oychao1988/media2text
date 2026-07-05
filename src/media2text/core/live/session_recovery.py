from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.task_reconciler import reconcile_live
from media2text.core.storage.models import LiveSessionRow
from media2text.core.storage.repos import LiveSessionRepo, MonitorTaskRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, get_write_gateway

log = structlog.get_logger()


def _ffmpeg_dead(row: LiveSessionRow) -> bool:
    if not row.ffmpeg_pid or row.ffmpeg_pid <= 0:
        return True
    try:
        os.kill(row.ffmpeg_pid, 0)
        return False
    except OSError:
        return True


def recover_active_sessions(cfg: AppConfig, conn) -> int:
    """Recovery rules on daemon start (MH-4a / #78 / 7/3 regression)."""
    sessions = LiveSessionRepo(conn, cfg=cfg)
    tasks = MonitorTaskRepo(conn, cfg=cfg)
    now = datetime.now(timezone.utc)
    touched = 0
    for row in sessions.list_active():
        if row.status != "recording":
            continue
        ffmpeg_dead = _ffmpeg_dead(row)
        if ffmpeg_dead:
            conn.execute(
                "UPDATE live_sessions SET obs_ffmpeg_alive = 0 WHERE id = ?",
                (row.id,),
            )
            touched += 1
        if ffmpeg_dead and row.offline_since_at:
            conn.execute(
                """
                UPDATE live_sessions SET
                  obs_still_live = 0,
                  obs_polled_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), row.id),
            )
            payload = json.dumps({"session_id": row.id})
            task_id = tasks.ensure_task(
                creator_id=row.creator_id,
                task_type="finalize",
                dedupe_key=f"finalize:{row.id}",
                priority=0,
                payload_json=payload,
            )
            if task_id:
                touched += 1
                log.info(
                    "session_recovery_offline_finalize_enqueued",
                    session_id=row.id,
                    creator_id=row.creator_id,
                )
            continue
        if ffmpeg_dead and not row.offline_since_at:
            try:
                started = datetime.fromisoformat(row.started_at.replace("Z", "+00:00"))
            except ValueError:
                started = now
            if (now - started).total_seconds() > 7200:
                sessions.update_status(
                    row.id,
                    status="failed",
                    error="stale_recording",
                    ended=True,
                )
                touched += 1
    touched += reconcile_live(cfg, conn)
    return touched


def recover_orphan_sessions(cfg: AppConfig, conn) -> int:
    ensure_write_gateway_started(cfg)
    gateway = get_write_gateway(cfg)
    return gateway.write(
        lambda c: recover_active_sessions(cfg, c),
        label="recover_orphan_sessions",
    )
