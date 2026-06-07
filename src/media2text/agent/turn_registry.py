"""In-process active turn tracking for cancel + supervisor handoff."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class ActiveTurnHandle:
    turn_id: str
    thread_id: str
    cancel: threading.Event
    supervisor: Any | None = None


class TurnRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turns: dict[str, ActiveTurnHandle] = {}

    def register(
        self,
        *,
        turn_id: str,
        thread_id: str,
        supervisor: Any | None = None,
    ) -> ActiveTurnHandle:
        handle = ActiveTurnHandle(
            turn_id=turn_id,
            thread_id=thread_id,
            cancel=threading.Event(),
            supervisor=supervisor,
        )
        with self._lock:
            self._turns[turn_id] = handle
        return handle

    def get(self, turn_id: str) -> ActiveTurnHandle | None:
        with self._lock:
            return self._turns.get(turn_id)

    def cancel(self, turn_id: str) -> bool:
        handle = self.get(turn_id)
        if handle is None:
            return False
        handle.cancel.set()
        return True

    def unregister(self, turn_id: str) -> None:
        with self._lock:
            self._turns.pop(turn_id, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._turns)


turn_registry = TurnRegistry()
