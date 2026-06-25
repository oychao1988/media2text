"""Live recording lane priority helpers."""

from __future__ import annotations

from media2text.core.config import AppConfig


def live_lane_priority_count(conn, cfg: AppConfig) -> int:
    """Count live-lane signals that should defer post_process drain."""
    del cfg
    prepare_row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM monitor_tasks
        WHERE task_type = 'prepare_live_recording'
          AND status IN ('pending', 'running')
        """
    ).fetchone()
    prepare_count = int(prepare_row["n"] if prepare_row else 0)

    live_row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM creators c
        INNER JOIN creator_live_snapshots s ON s.creator_id = c.id
        WHERE c.monitor_enabled = 1
          AND s.is_live = 1
          AND NOT EXISTS (
            SELECT 1 FROM live_sessions ls
            WHERE ls.creator_id = c.id
              AND ls.status IN ('recording', 'remuxing')
          )
        """
    ).fetchone()
    live_unrecorded = int(live_row["n"] if live_row else 0)
    return prepare_count + live_unrecorded


def live_lane_needs_priority(conn, cfg: AppConfig) -> bool:
    """True when live detection/prepare work should defer post_process drain."""
    return live_lane_priority_count(conn, cfg) > 0
