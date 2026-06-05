"""Monitor watch log sink: in-memory ring + ``monitor-watch.log`` tee for embedded serve."""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.runtime.status import LOG_NAME

_ring: deque[str] = deque(maxlen=500)
_lock = threading.Lock()
_log_path: Path | None = None
_sink_active = False


def is_sink_active() -> bool:
    return _sink_active


def prepare_sink(workspace: Path) -> Path:
    """Enable file path and session marker; call ``reconfigure_logging_with_sink`` after."""
    global _log_path, _sink_active
    path = workspace / LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = (
        f"\n--- session {datetime.now(timezone.utc).isoformat()} (embedded) ---\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(marker)
    except OSError:
        pass
    _log_path = path
    _sink_active = True
    return path


def structlog_sink_processor(_logger: object, _method: str, event_dict: dict) -> dict:
    if _sink_active:
        record_event_dict(event_dict)
    return event_dict


def record_event_dict(event_dict: dict) -> None:
    line = json.dumps(event_dict, default=str, ensure_ascii=False)
    with _lock:
        _ring.append(line)
        path = _log_path
    if path is not None:
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass


def tail_lines(*, tail: int, log_path: Path | None = None) -> list[str]:
    """Return the last *tail* raw JSON/text log lines (ring preferred when sink active)."""
    n = max(1, min(tail, 500))
    with _lock:
        ring = list(_ring)
    if ring:
        return ring[-n:]
    path = log_path or _log_path
    if path is not None and path.is_file():
        return _read_file_tail(path, n)
    return []


def _read_file_tail(path: Path, n: int) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-n:]
