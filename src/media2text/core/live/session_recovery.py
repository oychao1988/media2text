from __future__ import annotations

import os
from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.live.task_reconciler import reconcile_live
from media2text.core.storage.repos import LiveSessionRepo

_ORPHAN_MAX_AGE_SEC = 7200


def recover_orphan_sessions(cfg: AppConfig, conn) -> int:
    sessions = LiveSessionRepo(conn)
    touched = 0
    stale_marked = 0
    now = datetime.now(timezone.utc)
    for row in sessions.list_active():
        if row.status != "recording":
            continue
        ffmpeg_dead = False
        if row.ffmpeg_pid:
            try:
                os.kill(row.ffmpeg_pid, 0)
            except OSError:
                ffmpeg_dead = True
                conn.execute(
                    "UPDATE live_sessions SET obs_ffmpeg_alive = 0 WHERE id = ?",
                    (row.id,),
                )
                touched += 1
        if ffmpeg_dead and not row.offline_since_at:
            try:
                started = datetime.fromisoformat(row.started_at.replace("Z", "+00:00"))
            except ValueError:
                started = now
            if (now - started).total_seconds() > _ORPHAN_MAX_AGE_SEC:
                sessions.update_status(
                    row.id,
                    status="failed",
                    error="stale_recording",
                    ended=True,
                )
                stale_marked += 1
    conn.commit()
    ensured = reconcile_live(cfg, conn)
    return touched + stale_marked + ensured
