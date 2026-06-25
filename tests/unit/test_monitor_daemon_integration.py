import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, LiveConfig, MonitorConfig
from media2text.core.live.scheduler import MonitorScheduler
from media2text.core.monitor.errors import ReconcilerDisabledError
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import (
    CreatorRepo,
    LiveSessionRepo,
    LiveSnapshotRepo,
    MonitorTaskRepo,
)
from media2text.core.workspace import open_db


def test_scheduler_refuses_start_when_reconciler_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=False),
    )
    watcher = MonitorWatcher(cfg)
    scheduler = MonitorScheduler(watcher, cfg)
    with pytest.raises(ReconcilerDisabledError, match="reconciler_enabled=true"):
        scheduler.start()


def test_reconciler_log_only_still_starts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True, reconciler_log_only=True),
        live=LiveConfig(live_poll_interval_sec=60),
    )
    watcher = MonitorWatcher(cfg)
    scheduler = MonitorScheduler(watcher, cfg)
    scheduler.start()
    scheduler.stop()


def test_daemon_integration_prepare_enqueued_and_live_pool_drains(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(
            scheduler_interval_sec=1,
            reconciler_enabled=True,
            live_worker_max_parallel=1,
        ),
        live=LiveConfig(live_poll_interval_sec=60),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAintA",
        profile_url="https://example.com/a",
        monitor_enabled=True,
    )
    LiveSnapshotRepo(conn).upsert(cid, is_live=True, room_id="room1")
    conn.close()

    watcher = MonitorWatcher(cfg)
    submitted: list[str] = []

    def track_submit(_self, _cfg, *, task_id, notify, watcher=None):
        submitted.append(task_id)
        return True

    stop = threading.Event()

    with (
        patch.object(watcher._douyin_live, "run_once", return_value={"active": 0}),
        patch.object(watcher._bilibili_live, "run_once", return_value={"active": 0}),
        patch(
            "media2text.core.live.monitor_executor.MonitorExecutor.submit",
            track_submit,
        ),
        patch(
            "media2text.core.monitor.watcher._graceful_stop_event",
            side_effect=lambda _: stop,
        ),
    ):
        scheduler = MonitorScheduler(watcher, cfg)
        scheduler.start()
        time.sleep(2.5)
        stop.set()
        scheduler.stop()

    conn2 = open_db(cfg)
    assert MonitorTaskRepo(conn2).has_active_dedupe(f"prepare:{cid}")
    assert submitted, "live pool should submit prepare_live_recording"
    conn2.close()


def test_daemon_integration_content_drains_while_other_creator_recording(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(
            scheduler_interval_sec=1,
            reconciler_enabled=True,
            executor_max_parallel=1,
        ),
        live=LiveConfig(live_poll_interval_sec=60),
    )
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    cid_a = creators.add(
        sec_uid="MS4wLjABAAAAintRecA",
        profile_url="https://example.com/a",
        monitor_enabled=True,
    )
    cid_b = creators.add(
        sec_uid="MS4wLjABAAAAintRecB",
        profile_url="https://example.com/b",
        monitor_enabled=True,
    )
    creators.set_content_sync_enabled(cid_b, enabled=True)
    LiveSessionRepo(conn).create(
        creator_id=cid_a,
        room_id="1",
        temp_path=str(tmp_path / "a.flv"),
        ffmpeg_pid=1,
    )
    repo = MonitorTaskRepo(conn)
    sync_b = repo.enqueue(
        creator_id=cid_b,
        task_type="sync_catalog",
        dedupe_key=f"sync_catalog:{cid_b}",
        priority=10,
        payload_json=json.dumps({"platform": "douyin"}),
    )
    assert sync_b is not None
    conn.close()

    watcher = MonitorWatcher(cfg)
    content_submitted: list[str] = []

    def track_submit(_self, _cfg, *, task_id, notify, watcher=None):
        row = MonitorTaskRepo(open_db(cfg)).get(task_id)
        if row and row.task_type == "sync_catalog":
            content_submitted.append(task_id)
        return True

    stop = threading.Event()

    with (
        patch.object(watcher._douyin_live, "run_once", return_value={"active": 1}),
        patch.object(watcher._bilibili_live, "run_once", return_value={"active": 0}),
        patch(
            "media2text.core.live.monitor_executor.MonitorExecutor.submit",
            track_submit,
        ),
        patch(
            "media2text.core.monitor.watcher._graceful_stop_event",
            side_effect=lambda _: stop,
        ),
    ):
        scheduler = MonitorScheduler(watcher, cfg)
        scheduler.start()
        time.sleep(2.5)
        stop.set()
        scheduler.stop()

    assert content_submitted, "creator B sync_catalog should drain while A is recording"
