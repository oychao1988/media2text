import os
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.desktop


def test_runtime_not_running(api_client) -> None:
    r = api_client.get("/api/runtime")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["health"] == "stopped"
    assert body["managed_by"] == "none"
    assert "daemon" in body
    assert "queues" in body
    assert "observability" in body
    assert "log_path" in body


def test_runtime_logs_tail(api_client, workspace) -> None:
    log = workspace / "monitor-watch.log"
    log.write_text("a\nb\nc\n", encoding="utf-8")
    r = api_client.get("/api/runtime/logs?tail=2")
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == ["信息 · 系统 · — · b", "信息 · 系统 · — · c"]
    assert len(body["entries"]) == 2


def test_runtime_logs_formats_json(api_client, workspace) -> None:
    import json

    log = workspace / "monitor-watch.log"
    log.write_text(
        json.dumps(
            {
                "event": "monitor_finalize_drained",
                "count": 2,
                "timestamp": "2026-06-05T10:42:31Z",
                "level": "info",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    r = api_client.get("/api/runtime/logs?tail=1")
    assert r.status_code == 200
    body = r.json()
    line = body["lines"][0]
    assert line.startswith("[")
    assert "直播收尾" in line
    assert "2 场" in line
    assert body["entries"][0]["task"] == "直播收尾"


def test_runtime_start_stop(api_client, workspace) -> None:
    from media2text.core.runtime.supervisor import MonitorSupervisor

    with patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None):
        start = api_client.post("/api/runtime/start")
    assert start.status_code == 200
    assert start.json()["ok"] is True
    stop = api_client.post("/api/runtime/stop")
    assert stop.status_code == 200


def test_runtime_stop_external(api_client, workspace) -> None:
    external_pid = 919191
    (workspace / ".monitor-watch.lock").write_text(str(external_pid), encoding="utf-8")
    alive = {external_pid}

    def fake_alive(pid: int) -> bool:
        return pid in alive

    def fake_kill(pid: int, sig: int) -> None:
        alive.discard(pid)

    with (
        patch("media2text.core.runtime.supervisor._pid_alive", fake_alive),
        patch("media2text.core.runtime.supervisor.os.kill", fake_kill),
    ):
        r = api_client.post("/api/runtime/stop")
    assert r.status_code == 200
    assert r.json()["stopped"] is True


def test_runtime_with_lock_external(api_client, workspace) -> None:
    pid = os.getpid()
    (workspace / ".monitor-watch.lock").write_text(str(pid), encoding="utf-8")
    r = api_client.get("/api/runtime")
    body = r.json()
    assert body["daemon"]["running"] is True
    assert body["managed_by"] in ("external", "none")


def test_runtime_handoff_to_external(api_client, workspace) -> None:
    from media2text.core.runtime.supervisor import MonitorSupervisor

    with patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None):
        start = api_client.post("/api/runtime/start")
    assert start.status_code == 200

    spawn_result = {"ok": True, "managed_by": "external", "pid": 939393}
    with patch(
        "media2text.core.runtime.supervisor.spawn_cli_monitor_daemon",
        return_value=spawn_result,
        create=True,
    ):
        with patch(
            "media2text.core.runtime.external_spawn.spawn_cli_monitor_daemon",
            return_value=spawn_result,
        ):
            r = api_client.post("/api/runtime/handoff")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["start"]["managed_by"] == "external"


def test_runtime_takeover_from_external(api_client, workspace) -> None:
    from media2text.core.runtime.supervisor import MonitorSupervisor

    external_pid = 828282
    (workspace / ".monitor-watch.lock").write_text(str(external_pid), encoding="utf-8")
    alive = {external_pid}

    def fake_alive(pid: int) -> bool:
        return pid in alive

    def fake_kill(pid: int, sig: int) -> None:
        alive.discard(pid)

    with (
        patch("media2text.core.runtime.supervisor._pid_alive", fake_alive),
        patch("media2text.core.runtime.supervisor.os.kill", fake_kill),
        patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None),
    ):
        r = api_client.post("/api/runtime/takeover")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["start"]["managed_by"] == "embedded"


def test_daemon_deprecated_gone(api_client) -> None:
    r = api_client.get("/api/daemon")
    assert r.status_code == 410
    assert r.json()["detail"]["use"] == "/api/runtime"
