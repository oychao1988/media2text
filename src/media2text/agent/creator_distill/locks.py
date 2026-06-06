"""Per-creator distill locks."""

from __future__ import annotations

import threading

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def creator_distill_lock(creator_id: str) -> threading.Lock:
    with _guard:
        if creator_id not in _locks:
            _locks[creator_id] = threading.Lock()
        return _locks[creator_id]
