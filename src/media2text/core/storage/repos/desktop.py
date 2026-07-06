import json
import uuid
from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.storage.models import DesktopEventRow
from media2text.core.storage.write_aware import WriteAwareRepo

class DesktopEventRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def enqueue_creator_updated(self, creator_id: str, *, payload: dict | None = None) -> str:
        def _body() -> str:
            event_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            payload_json = json.dumps(payload) if payload else None
            self._conn.execute(
                """
                INSERT INTO desktop_events (id, event_type, creator_id, payload_json, created_at)
                VALUES (?, 'creator.updated', ?, ?, ?)
                """,
                (event_id, creator_id, payload_json, now),
            )
            self._conn.commit()
            return event_id

        return self._mutate("desktop_event.enqueue", _body)

    def claim_pending(self, *, limit: int = 50) -> list[DesktopEventRow]:
        rows = self._conn.execute(
            """
            SELECT id FROM desktop_events
            WHERE delivered_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[DesktopEventRow] = []
        for row in rows:
            full = self.get(row["id"])
            if full:
                out.append(full)
        return out

    def mark_delivered(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()

        def _body() -> None:
            self._conn.execute(
                "UPDATE desktop_events SET delivered_at = ? WHERE id = ?",
                (now, event_id),
            )
            self._conn.commit()

        self._mutate("desktop_event.mark_delivered", _body)

    def get(self, event_id: str) -> DesktopEventRow | None:
        row = self._conn.execute(
            "SELECT * FROM desktop_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        return DesktopEventRow(**dict(row)) if row else None

