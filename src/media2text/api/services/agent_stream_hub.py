"""In-process pub/sub for ``WS /api/agent/stream`` (thread-safe)."""

from __future__ import annotations

import queue
from typing import Any


class AgentStreamHub:
    def __init__(self) -> None:
        self._subscribers: list[tuple[queue.Queue[dict[str, Any]], str | None]] = []

    def subscribe(self, *, thread_id: str | None = None) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue()
        self._subscribers.append((q, thread_id))
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        self._subscribers = [(item, tid) for item, tid in self._subscribers if item is not q]

    def publish(self, event: dict[str, Any], *, thread_id: str | None = None) -> None:
        for q, filter_tid in list(self._subscribers):
            if filter_tid is not None and thread_id is not None and filter_tid != thread_id:
                continue
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


agent_stream_hub = AgentStreamHub()
