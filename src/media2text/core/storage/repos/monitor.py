import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig
from media2text.core.live.probe_guard import ProbeExecutionGuard
from media2text.core.storage.models import MonitorTaskRow, PipelineEventRow
from media2text.core.storage.write_aware import WriteAwareRepo

class MonitorTaskRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def enqueue(
        self,
        *,
        creator_id: str,
        task_type: str,
        dedupe_key: str | None = None,
        priority: int = 10,
        payload_json: str | None = None,
    ) -> str | None:
        def _body() -> str | None:
            ProbeExecutionGuard.record_violation("enqueue")
            task_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            try:
                self._conn.execute(
                    """
                    INSERT INTO monitor_tasks
                      (id, creator_id, task_type, payload_json, priority, status,
                       dedupe_key, created_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        task_id,
                        creator_id,
                        task_type,
                        payload_json,
                        priority,
                        dedupe_key,
                        now,
                    ),
                )
                self._conn.commit()
                return task_id
            except sqlite3.IntegrityError:
                return None

        return self._mutate("monitor_task.enqueue", _body)

    def ensure_task(
        self,
        *,
        creator_id: str,
        task_type: str,
        dedupe_key: str,
        priority: int,
        payload_json: str | None = None,
    ) -> str | None:
        ProbeExecutionGuard.record_violation("ensure_task")
        return self.enqueue(
            creator_id=creator_id,
            task_type=task_type,
            dedupe_key=dedupe_key,
            priority=priority,
            payload_json=payload_json,
        )

    def cancel_pending(self, *, dedupe_key: str) -> int:
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            cur = self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'cancelled', finished_at = ?
                WHERE dedupe_key = ? AND status = 'pending'
                """,
                (now, dedupe_key),
            )
            self._conn.commit()
            return cur.rowcount

        return self._mutate("monitor_task.cancel_pending", _body)

    def has_active_dedupe(self, dedupe_key: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM monitor_tasks
            WHERE dedupe_key = ? AND status IN ('pending', 'running')
            LIMIT 1
            """,
            (dedupe_key,),
        ).fetchone()
        return row is not None

    def mark_running(self, task_id: str) -> None:
        def _body() -> None:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'running', started_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, task_id),
            )
            self._conn.commit()

        self._mutate("monitor_task.mark_running", _body)

    def get(self, task_id: str) -> MonitorTaskRow | None:
        row = self._conn.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return MonitorTaskRow(**dict(row)) if row else None

    def _select_fair_pending_id(
        self,
        *,
        min_priority: int,
        max_priority: int | None,
        exclude_creator_ids: frozenset[str] | None = None,
    ) -> str | None:
        """Pick oldest pending task per creator, then lowest priority globally."""
        exclude_inner = ""
        exclude_outer = ""
        exclude_params: tuple = ()
        if exclude_creator_ids:
            placeholders = ",".join("?" * len(exclude_creator_ids))
            exclude_inner = f" AND creator_id NOT IN ({placeholders})"
            exclude_outer = f" AND t.creator_id NOT IN ({placeholders})"
            exclude_params = tuple(exclude_creator_ids)
        if max_priority is not None:
            row = self._conn.execute(
                f"""
                SELECT t.id FROM monitor_tasks t
                INNER JOIN (
                  SELECT creator_id, MIN(created_at) AS min_created
                  FROM monitor_tasks
                  WHERE status = 'pending'
                    AND priority >= ? AND priority <= ?{exclude_inner}
                  GROUP BY creator_id
                ) heads
                  ON t.creator_id = heads.creator_id
                 AND t.created_at = heads.min_created
                WHERE t.status = 'pending'
                  AND t.priority >= ? AND t.priority <= ?{exclude_outer}
                ORDER BY t.priority ASC, t.created_at ASC
                LIMIT 1
                """,
                (
                    min_priority,
                    max_priority,
                    *exclude_params,
                    min_priority,
                    max_priority,
                    *exclude_params,
                ),
            ).fetchone()
        else:
            row = self._conn.execute(
                f"""
                SELECT t.id FROM monitor_tasks t
                INNER JOIN (
                  SELECT creator_id, MIN(created_at) AS min_created
                  FROM monitor_tasks
                  WHERE status = 'pending' AND priority >= ?{exclude_inner}
                  GROUP BY creator_id
                ) heads
                  ON t.creator_id = heads.creator_id
                 AND t.created_at = heads.min_created
                WHERE t.status = 'pending' AND t.priority >= ?{exclude_outer}
                ORDER BY t.priority ASC, t.created_at ASC
                LIMIT 1
                """,
                (min_priority, *exclude_params, min_priority, *exclude_params),
            ).fetchone()
        return str(row["id"]) if row else None

    def claim_pending(
        self,
        *,
        limit: int = 1,
        max_priority: int | None = None,
        min_priority: int = 0,
        exclude_creator_ids: frozenset[str] | None = None,
    ) -> list[MonitorTaskRow]:
        def _body():
            claimed: list[MonitorTaskRow] = []
            now = datetime.now(timezone.utc).isoformat()
            for _ in range(limit):
                task_id = self._select_fair_pending_id(
                    min_priority=min_priority,
                    max_priority=max_priority,
                    exclude_creator_ids=exclude_creator_ids,
                )
                if not task_id:
                    break
                row = {"id": task_id}
                cur = self._conn.execute(
                    """
                    UPDATE monitor_tasks
                    SET status = 'running', started_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (now, row["id"]),
                )
                if cur.rowcount != 1:
                    continue
                task = self.get(row["id"])
                if task:
                    claimed.append(task)
            self._conn.commit()
            return claimed

        return self._mutate("monitor_task.claim_pending", _body)

    def mark_done(self, task_id: str) -> None:
        def _body() -> None:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'done', finished_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
            self._conn.commit()

        self._mutate("monitor_task.mark_done", _body)

    def mark_failed(self, task_id: str, *, error: str) -> None:
        def _body() -> None:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'failed', error = ?, finished_at = ?
                WHERE id = ?
                """,
                (error, now, task_id),
            )
            self._conn.commit()

        self._mutate("monitor_task.mark_failed", _body)

    def fail_or_retry(self, task_id: str, *, error: str, max_retries: int) -> str:
        def _body():
            """On worker failure: retry (pending) or DLQ (failed). Returns outcome."""
            row = self.get(task_id)
            if not row:
                return "missing"
            next_attempt = int(row.attempt_count) + 1
            if next_attempt < max_retries:
                self._conn.execute(
                    """
                    UPDATE monitor_tasks
                    SET status = 'pending', attempt_count = ?, error = ?,
                        started_at = NULL, finished_at = NULL
                    WHERE id = ?
                    """,
                    (next_attempt, error, task_id),
                )
                self._conn.commit()
                return "retry"
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'failed', attempt_count = ?, error = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (next_attempt, error, now, task_id),
            )
            self._conn.commit()
            return "failed"

        return self._mutate("monitor_task.fail_or_retry", _body)

    def retry_failed(self, task_id: str) -> bool:
        def _body():
            """Reset a failed task to pending. Returns True if updated."""
            now = datetime.now(timezone.utc).isoformat()
            cur = self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'pending', attempt_count = 0, error = NULL,
                    started_at = NULL, finished_at = NULL, created_at = ?
                WHERE id = ? AND status = 'failed'
                """,
                (now, task_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

        return self._mutate("monitor_task.retry_failed", _body)

    def list_in_flight(self, *, limit: int = 50) -> list[MonitorTaskRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM monitor_tasks
            WHERE status IN ('pending', 'running')
            ORDER BY
              CASE status WHEN 'running' THEN 0 ELSE 1 END,
              priority ASC,
              created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [MonitorTaskRow(**dict(r)) for r in rows]

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        def _body():
            cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
            rows = self._conn.execute(
                "SELECT id, started_at FROM monitor_tasks WHERE status = 'running'"
            ).fetchall()
            count = 0
            for row in rows:
                started = row["started_at"]
                if started:
                    try:
                        started_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                    except ValueError:
                        started_dt = datetime.now(timezone.utc)
                    if started_dt.timestamp() > cutoff:
                        continue
                elif older_than_sec > 0:
                    continue
                self._conn.execute(
                    """
                    UPDATE monitor_tasks
                    SET status = 'pending', started_at = NULL, error = NULL
                    WHERE id = ?
                    """,
                    (row["id"],),
                )
                count += 1
            self._conn.commit()
            return count

        return self._mutate("monitor_task.reset_stale_running", _body)

    def release_running_content_tasks_for_creators(self, creator_ids: list[str]) -> int:
        def _body():
            """Yield Playwright for live lane: reset running content tasks for given creators."""
            if not creator_ids:
                return 0
            placeholders = ",".join("?" * len(creator_ids))
            cur = self._conn.execute(
                f"""
                UPDATE monitor_tasks
                SET status = 'pending', started_at = NULL, error = NULL
                WHERE status = 'running'
                  AND task_type IN ('sync_catalog', 'download', 'sync_dynamic')
                  AND creator_id IN ({placeholders})
                """,
                tuple(creator_ids),
            )
            self._conn.commit()
            return cur.rowcount

        return self._mutate("monitor_task.release_running_content_tasks_for_creators", _body)

    def release_running_content_tasks(self) -> int:
        def _body():
            """Release all running content tasks (legacy; prefer per-creator)."""
            cur = self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'pending', started_at = NULL, error = NULL
                WHERE status = 'running'
                  AND task_type IN ('sync_catalog', 'download', 'sync_dynamic')
                """
            )
            self._conn.commit()
            return cur.rowcount

        return self._mutate("monitor_task.release_running_content_tasks", _body)

    def count_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM monitor_tasks
            GROUP BY status
            """
        ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    def count_failed_recent_24h(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM monitor_tasks
            WHERE status = 'failed'
              AND finished_at IS NOT NULL
              AND finished_at >= ?
            """,
            (cutoff,),
        ).fetchone()
        return int(row["n"]) if row else 0


class PipelineEventRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def insert(
        self,
        *,
        session_id: str,
        stage: str,
        status: str,
        job_id: str | None = None,
        detail: dict | None = None,
        started_at: str,
        ended_at: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        def _body() -> str:
            import uuid

            event_id = str(uuid.uuid4())
            self._conn.execute(
                """
                    INSERT INTO live_pipeline_events
                      (id, session_id, job_id, stage, status, detail_json,
                       started_at, ended_at, duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    event_id,
                    session_id,
                    job_id,
                    stage,
                    status,
                    json.dumps(detail, ensure_ascii=False) if detail else None,
                    started_at,
                    ended_at,
                    duration_ms,
                ),
            )
            self._conn.commit()
            return event_id

        return self._mutate("pipeline_event.insert", _body)

    def complete(
        self,
        event_id: str,
        *,
        status: str,
        ended_at: str,
        duration_ms: int | None = None,
        detail: dict | None = None,
    ) -> None:
        def _body():
            if detail is not None:
                self._conn.execute(
                    """
                        UPDATE live_pipeline_events
                        SET status = ?, ended_at = ?, duration_ms = ?, detail_json = ?
                        WHERE id = ?
                        """,
                    (
                        status,
                        ended_at,
                        duration_ms,
                        json.dumps(detail, ensure_ascii=False),
                        event_id,
                    ),
                )
            else:
                self._conn.execute(
                    """
                        UPDATE live_pipeline_events
                        SET status = ?, ended_at = ?, duration_ms = ?
                        WHERE id = ?
                        """,
                    (status, ended_at, duration_ms, event_id),
                )
            self._conn.commit()

        self._mutate("pipeline_event.complete", _body)

    def list_for_session(self, session_id: str) -> list[PipelineEventRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM live_pipeline_events
            WHERE session_id = ?
            ORDER BY started_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [PipelineEventRow(**dict(r)) for r in rows]

    def stats_since(self, since_iso: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT stage, duration_ms
            FROM live_pipeline_events
            WHERE started_at >= ?
              AND duration_ms IS NOT NULL
              AND status = 'completed'
            """,
            (since_iso,),
        ).fetchall()
        by_stage: dict[str, list[int]] = {}
        for row in rows:
            stage = str(row["stage"])
            ms = int(row["duration_ms"])
            by_stage.setdefault(stage, []).append(ms)
        out: list[dict] = []
        for stage, values in sorted(by_stage.items()):
            values.sort()
            out.append(
                {
                    "stage": stage,
                    "count": len(values),
                    "p50_ms": _percentile(values, 50),
                    "p95_ms": _percentile(values, 95),
                }
            )
        return out

    def streaming_metrics_since(self, since_iso: str) -> dict:
        s1 = self._percentile_stats_for_events(since_iso, stage="streaming_stt", status="completed")
        first_final = self._percentile_stats_for_events(
            since_iso, stage="streaming_stt", status="first_final"
        )
        s2 = self._offline_to_complete_stats(since_iso)
        s3 = self._offline_to_summarize_stats(since_iso)
        return {
            "s1_finalize_stt_ms": s1,
            "s2_offline_to_complete_ms": s2,
            "s3_offline_to_summarize_ms": s3,
            "first_final_latency_ms": first_final,
        }

    def _percentile_stats_for_events(self, since_iso: str, *, stage: str, status: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT duration_ms
            FROM live_pipeline_events
            WHERE started_at >= ?
              AND stage = ?
              AND status = ?
              AND duration_ms IS NOT NULL
            """,
            (since_iso, stage, status),
        ).fetchall()
        values = [int(row["duration_ms"]) for row in rows]
        return _aggregate_ms(values)

    def _offline_to_complete_stats(self, since_iso: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT ls.ended_at AS completed_at,
                   (
                     SELECT started_at FROM live_pipeline_events e
                     WHERE e.session_id = ls.id
                       AND e.stage = 'recording'
                       AND e.status = 'offline_pending'
                     ORDER BY started_at ASC LIMIT 1
                   ) AS offline_at
            FROM live_sessions ls
            WHERE ls.started_at >= ?
              AND ls.pipeline_mode = 'streaming'
              AND ls.status = 'completed'
              AND ls.ended_at IS NOT NULL
            """,
            (since_iso,),
        ).fetchall()
        deltas: list[int] = []
        for row in rows:
            offline_at = row["offline_at"]
            completed_at = row["completed_at"]
            if not offline_at or not completed_at:
                continue
            try:
                t0 = datetime.fromisoformat(str(offline_at).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            deltas.append(max(0, int((t1 - t0).total_seconds() * 1000)))
        return _aggregate_ms(deltas)

    def _offline_to_summarize_stats(self, since_iso: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT (
                     SELECT started_at FROM live_pipeline_events e
                     WHERE e.session_id = ls.id
                       AND e.stage = 'recording'
                       AND e.status = 'offline_pending'
                     ORDER BY started_at ASC LIMIT 1
                   ) AS offline_at,
                   (
                     SELECT ended_at FROM live_pipeline_events e
                     WHERE e.session_id = ls.id
                       AND e.stage = 'summarize'
                       AND e.status = 'completed'
                     ORDER BY ended_at DESC LIMIT 1
                   ) AS summarize_at
            FROM live_sessions ls
            WHERE ls.started_at >= ?
              AND ls.pipeline_mode = 'streaming'
            """,
            (since_iso,),
        ).fetchall()
        deltas: list[int] = []
        for row in rows:
            offline_at = row["offline_at"]
            summarize_at = row["summarize_at"]
            if not offline_at or not summarize_at:
                continue
            try:
                t0 = datetime.fromisoformat(str(offline_at).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(summarize_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            deltas.append(max(0, int((t1 - t0).total_seconds() * 1000)))
        return _aggregate_ms(deltas)


def _aggregate_ms(values: list[int]) -> dict:
    if not values:
        return {"count": 0, "p50_ms": 0, "p95_ms": 0}
    values.sort()
    return {
        "count": len(values),
        "p50_ms": _percentile(values, 50),
        "p95_ms": _percentile(values, 95),
    }


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return int(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))

