import threading
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, MonitorConfig, NotifyConfig
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.notify.outbox import NotifyEventRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway
from media2text.core.workspace import open_db


@pytest.fixture(autouse=True)
def _reset_db_write_gateway() -> None:
    yield
    import media2text.core.storage.write_gateway as wg_mod
    from media2text.core.storage.write_gateway import shutdown_write_gateway

    shutdown_write_gateway()
    wg_mod._gateway = None


def test_notify_daemon_drain_after_scheduler_gateway_tick(tmp_path, monkeypatch) -> None:
    """Regression: drain_once must not run inside write_batch (writer-thread reentrancy)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
        notify=NotifyConfig(enabled=True, sound=False, outbox_only=True),
    )
    conn = open_db(cfg)
    NotifyEventRepo(conn).enqueue(
        kind="recording_completed",
        title="博主",
        body="录制完成",
    )
    conn.close()

    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    pool.drain_pending = MagicMock(return_value=0)
    post_pool = MagicMock()
    post_pool.drain_pending = MagicMock(return_value=0)
    stop = threading.Event()
    loop = TaskSchedulerLoop(cfg, watcher, live_pool=pool, content_pool=MagicMock(), post_pool=post_pool, stop=stop)

    ensure_write_gateway_started(cfg)
    try:
        with (
            patch("media2text.core.live.task_reconciler.reconcile_live"),
            patch("media2text.core.live.task_reconciler.reconcile_content"),
            patch("media2text.core.notify.drain.NotifyService.deliver") as mock_deliver,
        ):
            gw = ensure_write_gateway_started(cfg)
            gw.write_batch(lambda conn: loop.tick_once(conn), label="scheduler_tick")
            from media2text.core.notify.drain import drain_once

            drain_once(cfg, limit=20)
        mock_deliver.assert_called_once()
    finally:
        shutdown_write_gateway()
    conn2 = open_db(cfg)
    assert NotifyEventRepo(conn2).count_pending() == 0
    conn2.close()


def test_notify_daemon_drain_on_scheduler_tick(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
        notify=NotifyConfig(enabled=True, sound=False, outbox_only=True),
    )
    conn = open_db(cfg)
    NotifyEventRepo(conn).enqueue(
        kind="recording_completed",
        title="博主",
        body="录制完成",
    )
    conn.close()

    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    pool.drain_pending = MagicMock(return_value=0)
    post_pool = MagicMock()
    post_pool.drain_pending = MagicMock(return_value=0)
    stop = threading.Event()
    loop = TaskSchedulerLoop(cfg, watcher, live_pool=pool, content_pool=MagicMock(), post_pool=post_pool, stop=stop)

    with (
        patch("media2text.core.live.task_reconciler.reconcile_live"),
        patch("media2text.core.live.task_reconciler.reconcile_content"),
        patch("media2text.core.notify.drain.NotifyService.deliver") as mock_deliver,
    ):
        loop.tick_once(open_db(cfg))
        from media2text.core.notify.drain import drain_once

        drain_once(cfg, limit=20)
    mock_deliver.assert_called_once()
    conn2 = open_db(cfg)
    assert NotifyEventRepo(conn2).count_pending() == 0
    conn2.close()
