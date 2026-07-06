from unittest.mock import MagicMock

from media2text.core.config import AppConfig
from media2text.core.live.heavy_pool import HeavyPool
from media2text.core.live.monitor_executor import MonitorExecutor
from media2text.core.live.segment_process_pool import SegmentProcessExecutor
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo
from media2text.core.workspace import open_db


def test_heavy_pool_drains_finalize_p0_and_segment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAheavy",
        profile_url="https://example.com/heavy",
        monitor_enabled=True,
    )
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="finalize",
        dedupe_key="finalize:s-heavy",
        priority=0,
        payload_json='{"session_id":"s-heavy"}',
    )

    finalize_pool = MonitorExecutor(max_workers=1)
    segment_pool = SegmentProcessExecutor(max_workers=1)
    heavy = HeavyPool(finalize_pool=finalize_pool, segment_pool=segment_pool)
    watcher = MonitorWatcher(cfg)

    submitted: list[str] = []

    def track_submit(_cfg, *, task_id, notify, watcher=None):
        submitted.append(task_id)
        return True

    finalize_pool.submit = track_submit  # type: ignore[method-assign]
    segment_drained: list[bool] = []
    segment_pool.drain_pending = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda *a, **k: segment_drained.append(True)
    )

    heavy.drain(cfg, conn, notify=watcher._notify, watcher=watcher)

    assert len(submitted) == 1
    assert segment_drained == [True]
    heavy.shutdown(wait=False)
