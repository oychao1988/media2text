"""Hermes-aligned AIAgent kernel (M0 echo stub)."""

from __future__ import annotations

from media2text.agent.hermes_state import MessageRow, SessionDB
from media2text.core.config import AppConfig


class AIAgent:
    """M0: persist user turn and echo assistant reply without LLM."""

    def __init__(self, db: SessionDB, cfg: AppConfig | None = None) -> None:
        self._db = db
        self._cfg = cfg or AppConfig.load()

    def run_conversation(self, *, display_thread_id: str, user_text: str) -> str:
        session_id = self._db.get_active_session_for_thread(display_thread_id)
        self._db.append_message(
            session_id,
            MessageRow(role="user", content=user_text),
        )
        reply = f"echo: {user_text}"
        self._db.append_message(
            session_id,
            MessageRow(role="assistant", content=reply),
        )
        return reply
