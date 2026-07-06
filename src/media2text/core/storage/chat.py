import uuid

from media2text.core.storage.models import DesktopChatMessageRow, DesktopChatThreadRow

class DesktopChatRepo:
    """Backward-compatible facade over Hermes SessionDB (M0)."""

    def __init__(self, conn) -> None:
        from media2text.agent.hermes_state import MessageRow, SessionDB, parse_binding

        self._conn = conn
        self._db = SessionDB(conn)
        self._MessageRow = MessageRow
        self._parse_binding = parse_binding

    def _row_to_thread(self, row) -> DesktopChatThreadRow:
        binding = self._parse_binding(row["active_binding_json"])
        return DesktopChatThreadRow(
            id=row["display_thread_id"],
            creator_id=row["creator_id"],
            session_id=binding.get("session_id"),
            title=row["title"],
            provider_name=binding.get("provider_name"),
            model=str(binding.get("model") or "auto"),
            context_mode=str(binding.get("context_mode") or "both"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_thread(
        self,
        *,
        creator_id: str | None,
        session_id: str | None = None,
        title: str | None = None,
        provider_name: str | None = None,
        model: str = "auto",
        context_mode: str = "both",
    ) -> str:
        thread_id = str(uuid.uuid4())
        self._db.create_session(
            display_thread_id=thread_id,
            creator_id=creator_id,
            title=title,
            provider_name=provider_name,
            model=model,
            context_mode=context_mode,
            live_session_id=session_id,
        )
        return thread_id

    def get_thread(self, thread_id: str) -> DesktopChatThreadRow | None:
        row = self._db.get_thread_by_display_id(thread_id)
        if not row:
            return None
        return self._row_to_thread(row)

    def add_message(
        self,
        thread_id: str,
        *,
        role: str,
        content: str,
        thinking_text: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        session_id = self._db.get_active_session_for_thread(thread_id)
        return self._db.append_message(
            session_id,
            self._MessageRow(
                role=role,
                content=content,
                thinking_text=thinking_text,
                duration_ms=duration_ms,
            ),
        )

    def list_messages(self, thread_id: str) -> list[DesktopChatMessageRow]:
        rows = self._db.get_messages(thread_id)
        return [
            DesktopChatMessageRow(
                id=row["id"],
                thread_id=thread_id,
                role=row["role"],
                content=row["content"] or "",
                thinking_text=row["thinking_text"],
                duration_ms=row["duration_ms"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_threads(
        self,
        *,
        creator_id: str | None = None,
        session_id: str | None = None,
    ) -> list[DesktopChatThreadRow]:
        rows = self._db.list_threads(creator_id=creator_id, live_session_id=session_id)
        return [self._row_to_thread(row) for row in rows]

    def update_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        context_mode: str | None = None,
        session_id: str | None = None,
        clear_session: bool = False,
    ) -> bool:
        return self._db.update_session(
            thread_id,
            title=title,
            provider_name=provider_name,
            model=model,
            context_mode=context_mode,
            live_session_id=session_id,
            clear_live_session=clear_session,
        )

    def delete_thread(self, thread_id: str) -> bool:
        return self._db.delete_thread(thread_id)
