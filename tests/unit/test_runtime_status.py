from datetime import datetime, timedelta, timezone
import os

import pytest

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.runtime.status import (
    build_runtime_status,
    compute_health,
    count_stale_snapshots,
)
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo, MonitorTaskRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_compute_health_stopped() -> None:
    health, reasons = compute_health(
        running=False,
        tick_age_sec=None,
        live_poll_sec=10,
        snapshots_stale=0,
        failed_recent_24h=0,
    )
    assert health == "stopped"
    assert "monitor not running" in reasons


def test_compute_health_degraded_stale_tick() -> None:
    health, reasons = compute_health(
        running=True,
        tick_age_sec=100,
        live_poll_sec=10,
        snapshots_stale=0,
        failed_recent_24h=0,
    )
    assert health == "degraded"
    assert "live tick stale" in reasons


def test_compute_health_healthy() -> None:
    health, reasons = compute_health(
        running=True,
        tick_age_sec=5,
        live_poll_sec=10,
        snapshots_stale=0,
        failed_recent_24h=0,
    )
    assert health == "healthy"
    assert reasons == []


def test_failed_recent_24h_count(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAfail24",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    repo = MonitorTaskRepo(conn)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=30)).isoformat()
    recent = (now - timedelta(hours=1)).isoformat()
    for finished_at in (old, recent, recent):
        task_id = repo.enqueue(
            creator_id=cid,
            task_type="sync_catalog",
            dedupe_key=None,
        )
        assert task_id
        conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'failed', finished_at = ?
            WHERE id = ?
            """,
            (finished_at, task_id),
        )
    conn.commit()
    assert repo.count_failed_recent_24h() == 2


def test_build_runtime_status_includes_queues(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    conn = open_db(cfg)
    payload = build_runtime_status(cfg, conn=conn)
    assert payload["ok"] is True
    assert payload["health"] == "stopped"
    assert "queues" in payload
    assert "post_process" in payload["queues"]
    assert "failed_recent_24h" in payload["queues"]["monitor_tasks"]
    assert "observability" in payload
    assert payload["managed_by"] == "none"


def test_count_stale_snapshots_no_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    conn = open_db(cfg)
    CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstale",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    assert count_stale_snapshots(conn, cfg) == 1
    cid = CreatorRepo(conn).list_monitored()[0].id
    LiveSnapshotRepo(conn).upsert(cid, is_live=False)
    assert count_stale_snapshots(conn, cfg) == 0


def test_build_runtime_status_rejects_fake_lock_pid(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    conn = open_db(cfg)
    payload = build_runtime_status(cfg, conn=conn)
    assert payload["daemon"]["running"] is False
    assert payload["daemon"]["lock_valid"] is False
    assert payload["daemon"]["lock_reason"] == "lock_pid_mismatch"
    assert payload["health"] == "stopped"


def test_build_runtime_status_embedded_heartbeat_stale_health_degraded(tmp_path, monkeypatch) -> None:
    from media2text.core.runtime.heartbeat import write_heartbeat

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    sup = {"managed_by": "embedded", "thread_alive": True, "running": True}
    payload = build_runtime_status(cfg, conn=open_db(cfg), supervisor_status=sup)
    assert payload["daemon"]["running"] is True
    assert payload["health"] == "stopped"
    assert payload["daemon"]["lock_reason"] == "heartbeat_stale"


def test_build_runtime_status_embedded_heartbeat_stale_not_running(tmp_path, monkeypatch) -> None:
    from media2text.core.runtime.heartbeat import write_heartbeat

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    sup = {"managed_by": "embedded", "thread_alive": True, "running": True}
    payload = build_runtime_status(cfg, conn=open_db(cfg), supervisor_status=sup)
    assert payload["daemon"]["running"] is True
    assert payload["daemon"]["lock_reason"] == "heartbeat_stale"
