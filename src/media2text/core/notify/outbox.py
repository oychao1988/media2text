"""notify_events outbox: enqueue in daemon, drain in API sidecar (R4)."""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from media2text.core.config import AppConfig
from media2text.core.storage.write_aware import WriteAwareRepo
from media2text.core.storage.models import NotifyEventRow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_daemon_ctx = threading.local()


class NotifyDaemonGuard:
    """Thread-local marker for monitor daemon worker threads."""

    @staticmethod
    def enter() -> None:
        _daemon_ctx.active = True

    @staticmethod
    def is_active() -> bool:
        return bool(getattr(_daemon_ctx, "active", False))

    @staticmethod
    def reset() -> None:
        _daemon_ctx.active = False

    @staticmethod
    @contextmanager
    def daemon_thread() -> Iterator[None]:
        NotifyDaemonGuard.enter()
        try:
            yield
        finally:
            _daemon_ctx.active = False


class NotifyEventRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def enqueue(
        self,
        *,
        kind: str,
        title: str,
        body: str,
        creator_id: str | None = None,
        session_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> str:
        def _body() -> str:
            event_id = str(uuid.uuid4())
            now = _now_iso()
            payload_json = json.dumps(
                {"title": title, "body": body},
                ensure_ascii=False,
            )
            self._conn.execute(
                """
                INSERT INTO notify_events
                  (id, kind, dedupe_key, creator_id, session_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    kind,
                    dedupe_key,
                    creator_id,
                    session_id,
                    payload_json,
                    now,
                ),
            )
            self._conn.commit()
            return event_id

        return self._mutate("notify_event.enqueue", _body)

    def claim_pending(self, *, limit: int = 50) -> list[NotifyEventRow]:
        rows = self._conn.execute(
            """
            SELECT id FROM notify_events
            WHERE delivered_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[NotifyEventRow] = []
        for row in rows:
            full = self.get(row["id"])
            if full:
                out.append(full)
        return out

    def mark_done(self, event_id: str) -> None:
        def _body() -> None:
            now = _now_iso()
            self._conn.execute(
                "UPDATE notify_events SET delivered_at = ? WHERE id = ?",
                (now, event_id),
            )
            self._conn.commit()

        self._mutate("notify_event.mark_done", _body)

    def count_pending(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM notify_events WHERE delivered_at IS NULL"
        ).fetchone()
        return int(row["n"]) if row else 0

    def get(self, event_id: str) -> NotifyEventRow | None:
        row = self._conn.execute(
            "SELECT * FROM notify_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        return NotifyEventRow(**dict(row)) if row else None


def enqueue_notify_event_no_commit(
    conn,
    *,
    kind: str,
    title: str,
    body: str,
    creator_id: str | None = None,
    session_id: str | None = None,
    dedupe_key: str | None = None,
) -> str:
    """Insert notify_events row without commit (caller owns transaction)."""
    event_id = str(uuid.uuid4())
    now = _now_iso()
    payload_json = json.dumps({"title": title, "body": body}, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO notify_events
          (id, kind, dedupe_key, creator_id, session_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            kind,
            dedupe_key,
            creator_id,
            session_id,
            payload_json,
            now,
        ),
    )
    return event_id
