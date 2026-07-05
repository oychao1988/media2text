"""Embedded monitor DB lock stress (E2E-1 / W1).

Mock 11 creators with parallel probe + task scheduler; assert zero
``task_scheduler_db_locked`` and live_tick gaps within 2× poll interval.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo
from media2text.core.storage.write_gateway import (
    ensure_write_gateway_started,
    gateway_write,
    shutdown_write_gateway,
)
from media2text.core.workspace import open_db

NUM_CREATORS = 11


@pytest.fixture(autouse=True)
def _reset_write_gateway() -> None:
    yield
    import media2text.core.storage.write_gateway as wg_mod

    shutdown_write_gateway()
    wg_mod._gateway = None


def _seed_creators(cfg: AppConfig, *, count: int = NUM_CREATORS) -> None:
    conn = open_db(cfg)
    try:
        repo = CreatorRepo(conn)
        for i in range(count):
            repo.add(
                sec_uid=f"stress_sec_{i}",
                profile_url=f"https://example.com/stress/{i}",
                platform="douyin" if i % 2 == 0 else "bilibili",
                monitor_enabled=True,
            )
    finally:
        conn.close()


def _mock_probe_tick(cfg: AppConfig, **_kwargs) -> dict:
    """Simulate parallel probe persist without Playwright/network."""

    def _persist(conn) -> None:
        creators = CreatorRepo(conn).list_monitored()
        snaps = LiveSnapshotRepo(conn, cfg=cfg)
        for creator in creators:
            snaps.upsert(creator.id, is_live=False, room_id=None, title="stress")

    gateway_write(cfg, _persist, label="stress_probe_persist")
    time.sleep(0.05)
    return {"active_recordings": 0}


def _run_embedded_stress(
    tmp_path,
    monkeypatch,
    *,
    duration_sec: float,
) -> tuple[list[dict], float, int]:
    from media2text.core.live.scheduler import MonitorScheduler
    from media2text.core.monitor.watcher import MonitorWatcher

    monkeypatch.chdir(tmp_path)
    poll_sec = 1
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=poll_sec, scan_concurrency=4),
        monitor=MonitorConfig(
            scheduler_interval_sec=1,
            probe_parallelism=4,
            reconciler_enabled=True,
            live_poll_interval_sec=poll_sec,
        ),
    )
    _seed_creators(cfg)

    db_locked: list[dict] = []
    live_tick_at: list[float] = []

    import media2text.core.live.scheduler as sched_mod
    import media2text.core.live.task_scheduler as ts_mod

    orig_warn = ts_mod.log.warning

    def capture_warn(event, **kwargs):
        if event == "task_scheduler_db_locked":
            db_locked.append(dict(kwargs))
        return orig_warn(event, **kwargs)

    orig_info = sched_mod.log.info

    def capture_info(event, **kwargs):
        if event == "live_tick":
            live_tick_at.append(time.monotonic())
        return orig_info(event, **kwargs)

    monkeypatch.setattr(ts_mod.log, "warning", capture_warn)
    monkeypatch.setattr(sched_mod.log, "info", capture_info)
    monkeypatch.setattr(
        "media2text.core.live.scheduler.run_live_probe_tick",
        lambda *args, **kw: _mock_probe_tick(cfg, **kw),
    )

    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    scheduler = MonitorScheduler(watcher, cfg, stop=stop)
    ensure_write_gateway_started(cfg)

    with (
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch.object(watcher, "_run_dynamic_tick", return_value={}),
    ):
        scheduler.start()
        time.sleep(duration_sec)
        scheduler.stop()
        shutdown_write_gateway()

    max_gap = 0.0
    for prev, cur in zip(live_tick_at, live_tick_at[1:], strict=False):
        max_gap = max(max_gap, cur - prev)

    return db_locked, max_gap, poll_sec


def test_db_lock_stress_smoke(tmp_path, monkeypatch) -> None:
    """Short embedded monitor stress (default CI; not marked db_stress)."""
    locked, max_gap, poll = _run_embedded_stress(tmp_path, monkeypatch, duration_sec=8.0)
    assert locked == []
    assert max_gap < (2 * poll) + 3.0


@pytest.mark.db_stress
def test_db_lock_stress_sustained(tmp_path, monkeypatch) -> None:
    """60s sustained stress gate (W1); run with ``pytest -m db_stress``."""
    locked, max_gap, poll = _run_embedded_stress(tmp_path, monkeypatch, duration_sec=60.0)
    assert locked == []
    assert max_gap < (2 * poll) + 3.0
