from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog

from media2text.core.storage.db import with_db_lock_retry
from media2text.core.storage.models import SegmentProcessJobRow

log = structlog.get_logger()


@dataclass
class LiveSessionPartRow:
    session_id: str
    part_index: int
    rel_path: str
    state: str
    bytes: int | None = None
    duration_sec: float | None = None
    discontinuity_seq: int = 0
    cloud_path: str | None = None
    uploaded_at: str | None = None
    local_deleted_at: str | None = None
    error: str | None = None
    updated_at: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SegmentManifestRepo:
    """DB-backed manifest for HLS session parts (D14)."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def upsert_part(
        self,
        *,
        session_id: str,
        part_index: int,
        rel_path: str,
        state: str,
        bytes: int | None = None,
        duration_sec: float | None = None,
        discontinuity_seq: int = 0,
    ) -> None:
        now = _now_iso()

        def _write() -> None:
            self._conn.execute(
                """
                INSERT INTO live_session_parts
                  (session_id, part_index, rel_path, state, bytes, duration_sec,
                   discontinuity_seq, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, part_index) DO UPDATE SET
                  rel_path = excluded.rel_path,
                  state = excluded.state,
                  bytes = COALESCE(excluded.bytes, live_session_parts.bytes),
                  duration_sec = COALESCE(excluded.duration_sec, live_session_parts.duration_sec),
                  discontinuity_seq = excluded.discontinuity_seq,
                  updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    part_index,
                    rel_path,
                    state,
                    bytes,
                    duration_sec,
                    discontinuity_seq,
                    now,
                ),
            )
            self._conn.commit()

        with_db_lock_retry(_write)

    def get_part(self, session_id: str, part_index: int) -> LiveSessionPartRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM live_session_parts
            WHERE session_id = ? AND part_index = ?
            """,
            (session_id, part_index),
        ).fetchone()
        if not row:
            return None
        return LiveSessionPartRow(**dict(row))

    def mark_closed(
        self,
        session_id: str,
        part_index: int,
        *,
        bytes: int | None = None,
        duration_sec: float | None = None,
    ) -> None:
        now = _now_iso()

        def _write() -> None:
            self._conn.execute(
                """
                UPDATE live_session_parts
                SET state = 'closed',
                    bytes = COALESCE(?, bytes),
                    duration_sec = COALESCE(?, duration_sec),
                    updated_at = ?
                WHERE session_id = ? AND part_index = ?
                """,
                (bytes, duration_sec, now, session_id, part_index),
            )
            self._conn.commit()

        with_db_lock_retry(_write)

    def mark_uploaded(
        self,
        session_id: str,
        part_index: int,
        *,
        cloud_path: str,
    ) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE live_session_parts
            SET state = 'uploaded',
                cloud_path = ?,
                uploaded_at = ?,
                updated_at = ?
            WHERE session_id = ? AND part_index = ?
            """,
            (cloud_path, now, now, session_id, part_index),
        )
        self._conn.commit()

    def mark_local_deleted(self, session_id: str, part_index: int) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE live_session_parts
            SET state = 'local_deleted',
                local_deleted_at = ?,
                updated_at = ?
            WHERE session_id = ? AND part_index = ?
            """,
            (now, now, session_id, part_index),
        )
        self._conn.commit()

    def list_parts(self, session_id: str) -> list[LiveSessionPartRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM live_session_parts
            WHERE session_id = ?
            ORDER BY part_index ASC
            """,
            (session_id,),
        ).fetchall()
        return [LiveSessionPartRow(**dict(r)) for r in rows]

    def max_part_index(self, session_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT MAX(part_index) AS mx FROM live_session_parts WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if not row or row["mx"] is None:
            return 0
        return int(row["mx"])

    def export_json(self, session_id: str, *, session_dir: Path | None = None) -> dict:
        parts = self.list_parts(session_id)
        discontinuity_at: list[float] = []
        offset = 0.0
        for part in parts:
            if part.discontinuity_seq > 0:
                discontinuity_at.append(offset)
            if part.duration_sec is not None:
                offset += part.duration_sec

        payload = {
            "session_id": session_id,
            "media_format": "hls",
            "parts": [
                {
                    "index": p.part_index,
                    "rel_path": p.rel_path,
                    "state": p.state,
                    "bytes": p.bytes,
                    "duration_sec": p.duration_sec,
                    "discontinuity_seq": p.discontinuity_seq,
                    "cloud_path": p.cloud_path,
                }
                for p in parts
            ],
            "discontinuity_at": discontinuity_at,
        }
        if session_dir is not None:
            manifest_path = session_dir / "session.manifest.json"
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return payload


class SegmentProcessJobRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def enqueue(
        self,
        *,
        session_id: str,
        part_index: int,
        dedupe_key: str | None = None,
    ) -> str | None:
        key = dedupe_key or f"segment_process:{session_id}:{part_index}"
        existing = self._conn.execute(
            """
            SELECT id FROM segment_process_jobs
            WHERE session_id = ? AND part_index = ?
              AND status IN ('pending', 'running')
            """,
            (session_id, part_index),
        ).fetchone()
        if existing:
            return None
        job_id = str(uuid.uuid4())
        now = _now_iso()
        self._conn.execute(
            """
            INSERT INTO segment_process_jobs
              (id, session_id, part_index, status, attempts, created_at, updated_at, dedupe_key)
            VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
            """,
            (job_id, session_id, part_index, now, now, key),
        )
        self._conn.commit()
        return job_id

    def has_pending(self, session_id: str, part_index: int) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM segment_process_jobs
            WHERE session_id = ? AND part_index = ? AND status = 'pending'
            LIMIT 1
            """,
            (session_id, part_index),
        ).fetchone()
        return row is not None

    def get(self, job_id: str) -> SegmentProcessJobRow | None:
        row = self._conn.execute(
            "SELECT * FROM segment_process_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return SegmentProcessJobRow(**dict(row)) if row else None

    def claim_pending(self, *, limit: int = 1) -> list[SegmentProcessJobRow]:
        claimed: list[SegmentProcessJobRow] = []
        now = _now_iso()
        for _ in range(limit):
            row = self._conn.execute(
                """
                SELECT id FROM segment_process_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                break
            cur = self._conn.execute(
                """
                UPDATE segment_process_jobs
                SET status = 'running', claimed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, now, row["id"]),
            )
            if cur.rowcount != 1:
                continue
            job = self.get(row["id"])
            if job:
                claimed.append(job)
        self._conn.commit()
        return claimed

    def mark_running(self, job_id: str) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE segment_process_jobs
            SET status = 'running', updated_at = ?
            WHERE id = ?
            """,
            (now, job_id),
        )
        self._conn.commit()

    def mark_done(self, job_id: str) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE segment_process_jobs
            SET status = 'done', updated_at = ?
            WHERE id = ?
            """,
            (now, job_id),
        )
        self._conn.commit()

    def mark_failed(self, job_id: str, *, error: str) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE segment_process_jobs
            SET status = 'failed',
                last_error = ?,
                attempts = attempts + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (error, now, job_id),
        )
        self._conn.commit()

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
        rows = self._conn.execute(
            "SELECT id, updated_at FROM segment_process_jobs WHERE status = 'running'"
        ).fetchall()
        count = 0
        now = _now_iso()
        for row in rows:
            try:
                updated = datetime.fromisoformat(
                    str(row["updated_at"]).replace("Z", "+00:00")
                )
            except ValueError:
                updated = datetime.now(timezone.utc)
            if updated.timestamp() > cutoff:
                continue
            self._conn.execute(
                """
                UPDATE segment_process_jobs
                SET status = 'pending', updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            count += 1
        if count:
            self._conn.commit()
        return count

    def reset_failed_to_pending(self, *, max_attempts: int) -> int:
        rows = self._conn.execute(
            """
            SELECT id, attempts, last_error FROM segment_process_jobs
            WHERE status = 'failed'
            """
        ).fetchall()
        now = _now_iso()
        reset = 0
        for row in rows:
            attempts = int(row["attempts"] or 0)
            if attempts >= max_attempts:
                cur = self._conn.execute(
                    """
                    UPDATE segment_process_jobs
                    SET status = 'exhausted', updated_at = ?
                    WHERE id = ? AND status = 'failed'
                    """,
                    (now, row["id"]),
                )
                if cur.rowcount:
                    log.warning(
                        "segment_process_retry_exhausted",
                        job_id=row["id"],
                        attempts=attempts,
                        max_attempts=max_attempts,
                        last_error=row["last_error"],
                    )
                continue
            cur = self._conn.execute(
                """
                UPDATE segment_process_jobs
                SET status = 'pending', updated_at = ?
                WHERE id = ? AND status = 'failed'
                """,
                (now, row["id"]),
            )
            if cur.rowcount:
                reset += 1
        if reset:
            self._conn.commit()
        return reset

    def retry_failed(self, job_id: str) -> bool:
        """Manual retry: reset failed/exhausted job to pending regardless of attempts."""
        now = _now_iso()
        cur = self._conn.execute(
            """
            UPDATE segment_process_jobs
            SET status = 'pending', updated_at = ?
            WHERE id = ? AND status IN ('failed', 'exhausted')
            """,
            (now, job_id),
        )
        self._conn.commit()
        return cur.rowcount == 1
