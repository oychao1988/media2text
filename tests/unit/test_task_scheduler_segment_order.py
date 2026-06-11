import threading
from unittest.mock import MagicMock

from media2text.core.config import AppConfig
from media2text.core.live.task_scheduler import TaskSchedulerLoop
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.workspace import open_db


def test_scheduler_drains_segment_process_before_post_process(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    order: list[str] = []
    watcher = MonitorWatcher(cfg)
    pool = MagicMock()
    pool.claim_and_submit_priority_zero = MagicMock(return_value=0)
    pool.drain_pending = MagicMock(return_value=0)
    segment_pool = MagicMock()
    segment_pool.drain_pending = MagicMock(
        side_effect=lambda *a, **k: order.append("segment")
    )
    post_pool = MagicMock()
    post_pool.drain_pending = MagicMock(side_effect=lambda *a, **k: order.append("post"))
    stop = threading.Event()
    loop = TaskSchedulerLoop(
        cfg,
        watcher,
        live_pool=pool,
        content_pool=MagicMock(),
        post_pool=post_pool,
        segment_pool=segment_pool,
        stop=stop,
    )

    import media2text.core.live.task_scheduler as task_scheduler_mod

    monkeypatch.setattr(task_scheduler_mod, "reconcile_live", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "reconcile_content", lambda *a, **k: 0)
    monkeypatch.setattr(task_scheduler_mod, "drain_once", lambda *a, **k: None)

    loop.tick_once(conn)
    assert order.index("segment") < order.index("post")
