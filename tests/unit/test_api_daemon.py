import os
import signal
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.desktop


def test_daemon_not_running(api_client, workspace) -> None:
    r = api_client.get("/api/daemon")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["running"] is False


def test_daemon_logs_tail(api_client, workspace) -> None:
    log = workspace / "monitor-watch.log"
    log.write_text("line1\nline2\nline3\n", encoding="utf-8")
    r = api_client.get("/api/daemon/logs?tail=2")
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == ["line2", "line3"]


def test_daemon_status_with_lock(api_client, workspace) -> None:
    pid = os.getpid()
    (workspace / ".monitor-watch.lock").write_text(str(pid), encoding="utf-8")
    r = api_client.get("/api/daemon")
    body = r.json()
    assert body["running"] is True
    assert body["pid"] == pid


def test_daemon_stop(api_client, workspace) -> None:
    pid = os.getpid()
    (workspace / ".monitor-watch.lock").write_text(str(pid), encoding="utf-8")
    with patch("media2text.api.services.daemon.os.kill") as mock_kill:
        r = api_client.post("/api/daemon/stop")
    assert r.status_code == 200
    assert r.json()["stopped"] is True
    mock_kill.assert_any_call(pid, signal.SIGTERM)


def test_daemon_start_already_running(api_client, workspace) -> None:
    pid = os.getpid()
    (workspace / ".monitor-watch.lock").write_text(str(pid), encoding="utf-8")
    r = api_client.post("/api/daemon/start")
    assert r.status_code == 409
