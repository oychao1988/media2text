import json
import sys

import pytest
import structlog

from media2text.core.logging import enable_monitor_log_sink
from media2text.core.runtime import monitor_log

pytestmark = pytest.mark.desktop


class _BrokenStdout:
    def write(self, _data: str) -> None:
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        return None


def test_enable_monitor_log_sink_ignores_broken_stdout(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(monitor_log, "_ring", monitor_log.deque(maxlen=500))
    monkeypatch.setattr(monitor_log, "_sink_active", False)
    monkeypatch.setattr(monitor_log, "_log_path", None)
    monkeypatch.setattr(sys, "stdout", _BrokenStdout())

    path = enable_monitor_log_sink(tmp_path)
    log = structlog.get_logger()
    log.info("monitor_watch_daemon_started", live_poll=20)

    text = path.read_text(encoding="utf-8")
    assert "monitor_watch_daemon_started" in text
    lines = [line for line in text.splitlines() if line.strip().startswith("{")]
    assert json.loads(lines[-1])["event"] == "monitor_watch_daemon_started"
