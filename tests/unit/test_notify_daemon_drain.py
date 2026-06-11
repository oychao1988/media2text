import threading
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, MonitorConfig, NotifyConfig
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.notify.outbox import NotifyEventRepo
from media2text.core.workspace import open_db


def test_notify_daemon_drain_on_scheduler_tick(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=False),
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

    with patch("media2text.core.notify.drain.NotifyService.deliver") as mock_deliver:
        loop.tick_once(open_db(cfg))
    mock_deliver.assert_called_once()
    conn2 = open_db(cfg)
    assert NotifyEventRepo(conn2).count_pending() == 0
    conn2.close()
