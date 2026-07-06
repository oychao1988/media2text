import json
import uuid
from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.storage.models import CreatorAgentJobRow
from media2text.core.storage.write_aware import WriteAwareRepo

class CreatorAgentJobRepo(WriteAwareRepo):
    """Job queue for creator distill bootstrap / evolve (Hermes §24.4.6)."""

    _ACTIVE_BOOTSTRAP = ("pending", "running", "deferred")

    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def get(self, job_id: str) -> CreatorAgentJobRow | None:
        row = self._conn.execute(
            "SELECT * FROM creator_agent_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return CreatorAgentJobRow(**dict(row)) if row else None

    def find_active_bootstrap(self, creator_id: str) -> CreatorAgentJobRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE creator_id = ? AND kind = 'bootstrap'
              AND status IN ('pending', 'running', 'deferred')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (creator_id,),
        ).fetchone()
        return CreatorAgentJobRow(**dict(row)) if row else None

    def list_deferred_bootstrap(self, *, limit: int = 50) -> list[CreatorAgentJobRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE kind = 'bootstrap' AND status = 'deferred'
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [CreatorAgentJobRow(**dict(r)) for r in rows]

    def find_evolve_by_source(self, creator_id: str, source_id: str) -> CreatorAgentJobRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE creator_id = ? AND kind = 'evolve' AND source_id = ?
              AND status IN ('pending', 'running', 'done')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (creator_id, source_id),
        ).fetchone()
        return CreatorAgentJobRow(**dict(row)) if row else None

    def enqueue_evolve(
        self,
        *,
        creator_id: str,
        source_id: str,
        trigger: str,
        payload: dict | None = None,
    ) -> str | None:
        def _body() -> str:
            """Enqueue evolve; returns job id or None if idempotent skip."""
            existing = self.find_evolve_by_source(creator_id, source_id)
            if existing:
                return None

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            payload_json = json.dumps(payload) if payload else None
            self._conn.execute(
                """
                    INSERT INTO creator_agent_jobs (
                      id, creator_id, kind, status, trigger, source_id,
                      payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, 'evolve', 'pending', ?, ?, ?, ?, ?)
                    """,
                (job_id, creator_id, trigger, source_id, payload_json, now, now),
            )
            self._conn.commit()
            return job_id

        return self._mutate("creator_agent_job.enqueue_evolve", _body)

    def enqueue_bootstrap(
        self,
        *,
        creator_id: str,
        trigger: str,
        payload: dict | None = None,
        force: bool = False,
    ) -> str | None:
        def _body() -> str:
            """Enqueue bootstrap; returns job id or None if idempotent skip."""
            existing = self.find_active_bootstrap(creator_id)
            if existing:
                if force and existing.status == "deferred":
                    now = datetime.now(timezone.utc).isoformat()
                    self._conn.execute(
                        """
                            UPDATE creator_agent_jobs
                            SET status = 'pending', trigger = ?, updated_at = ?
                            WHERE id = ?
                            """,
                        (trigger, now, existing.id),
                    )
                    self._conn.commit()
                    return existing.id
                if existing.status in ("pending", "running"):
                    return None
                if existing.status == "deferred" and not force:
                    return existing.id

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            payload_json = json.dumps(payload) if payload else None
            self._conn.execute(
                """
                    INSERT INTO creator_agent_jobs (
                      id, creator_id, kind, status, trigger, source_id,
                      payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, 'bootstrap', 'pending', ?, NULL, ?, ?, ?)
                    """,
                (job_id, creator_id, trigger, payload_json, now, now),
            )
            self._conn.commit()
            return job_id

        return self._mutate("creator_agent_job.enqueue_bootstrap", _body)

    def mark_deferred(self, job_id: str, *, payload: dict | None = None) -> None:
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            payload_json = json.dumps(payload) if payload else None
            self._conn.execute(
                """
                    UPDATE creator_agent_jobs
                    SET status = 'deferred', payload_json = COALESCE(?, payload_json), updated_at = ?
                    WHERE id = ?
                    """,
                (payload_json, now, job_id),
            )
            self._conn.commit()

        self._mutate("creator_agent_job.mark_deferred", _body)

    def promote_deferred(self, job_id: str) -> bool:
        def _body() -> bool:
            now = datetime.now(timezone.utc).isoformat()
            cur = self._conn.execute(
                """
                    UPDATE creator_agent_jobs
                    SET status = 'pending', updated_at = ?
                    WHERE id = ? AND status = 'deferred'
                    """,
                (now, job_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

        return self._mutate("creator_agent_job.promote_deferred", _body)

    def claim_pending(self, *, limit: int = 1) -> list[CreatorAgentJobRow]:
        def _body():
            """Claim jobs; evolve (higher priority) before bootstrap."""
            claimed: list[CreatorAgentJobRow] = []
            now = datetime.now(timezone.utc).isoformat()
            for _ in range(limit):
                row = self._conn.execute(
                    """
                        SELECT id FROM creator_agent_jobs
                        WHERE status = 'pending'
                        ORDER BY
                          CASE kind WHEN 'evolve' THEN 0 WHEN 'bootstrap' THEN 1 ELSE 2 END,
                          created_at ASC
                        LIMIT 1
                        """
                ).fetchone()
                if not row:
                    break
                cur = self._conn.execute(
                    """
                        UPDATE creator_agent_jobs
                        SET status = 'running', updated_at = ?
                        WHERE id = ? AND status = 'pending'
                        """,
                    (now, row["id"]),
                )
                if cur.rowcount != 1:
                    continue
                job = self.get(row["id"])
                if job:
                    claimed.append(job)
            self._conn.commit()
            return claimed

        return self._mutate("creator_agent_job.claim_pending", _body)

    def mark_done(self, job_id: str, *, payload: dict | None = None) -> None:
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            payload_json = json.dumps(payload) if payload else None
            self._conn.execute(
                """
                    UPDATE creator_agent_jobs
                    SET status = 'done', payload_json = COALESCE(?, payload_json), updated_at = ?
                    WHERE id = ?
                    """,
                (payload_json, now, job_id),
            )
            self._conn.commit()

        self._mutate("creator_agent_job.mark_done", _body)

    def mark_failed(self, job_id: str, *, error: str, payload: dict | None = None) -> None:
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            merged = payload or {}
            merged["error"] = error
            self._conn.execute(
                """
                    UPDATE creator_agent_jobs
                    SET status = 'failed', payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                (json.dumps(merged), now, job_id),
            )
            self._conn.commit()

        self._mutate("creator_agent_job.mark_failed", _body)

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        def _body() -> int:
            cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
            rows = self._conn.execute(
                "SELECT id, updated_at FROM creator_agent_jobs WHERE status = 'running'"
            ).fetchall()
            count = 0
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                try:
                    updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
                except ValueError:
                    updated = datetime.now(timezone.utc)
                if updated.timestamp() > cutoff:
                    continue
                self._conn.execute(
                    """
                        UPDATE creator_agent_jobs
                        SET status = 'pending', updated_at = ?
                        WHERE id = ?
                        """,
                    (now, row["id"]),
                )
                count += 1
            self._conn.commit()
            return count

        return self._mutate("creator_agent_job.reset_stale_running", _body)

    def distill_status(self, creator_id: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT kind, status, COUNT(*) AS n
            FROM creator_agent_jobs
            WHERE creator_id = ?
            GROUP BY kind, status
            """,
            (creator_id,),
        ).fetchall()
        by_kind: dict[str, dict[str, int]] = {}
        for row in rows:
            kind = str(row["kind"])
            by_kind.setdefault(kind, {})[str(row["status"])] = int(row["n"])
        latest = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE creator_id = ? AND kind = 'bootstrap'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (creator_id,),
        ).fetchone()
        latest_row = CreatorAgentJobRow(**dict(latest)) if latest else None
        return {"by_kind": by_kind, "latest_bootstrap": latest_row}


