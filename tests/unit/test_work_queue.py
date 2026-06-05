import pytest

from media2text.api.services.work_queue import get_work_queue, recover_stale_work
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo, PostProcessJobRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_creator(conn) -> str:
    return CreatorRepo(conn).add(
        sec_uid="sec_wq_test",
        profile_url="https://www.douyin.com/user/sec_wq_test",
        platform="douyin",
        monitor_enabled=True,
        display_name="测试博主",
    )


def test_work_queue_lists_in_flight(workspace) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    try:
        creator_id = _seed_creator(conn)
        MonitorTaskRepo(conn).enqueue(
            creator_id=creator_id,
            task_type="sync_catalog",
            dedupe_key=f"test-sync:{creator_id}",
            priority=10,
        )
        PostProcessJobRepo(conn).enqueue(
            session_id="sess-test",
            creator_id=creator_id,
            mp4_path=str(workspace / "live" / "test.mp4"),
        )
    finally:
        conn.close()

    body = get_work_queue(cfg, limit=10)
    assert body["ok"] is True
    assert any(t["task_type"] == "sync_catalog" for t in body["monitor_tasks"])
    assert any(j["creator_id"] == creator_id for j in body["post_process"])


def test_recover_stale_resets_running_tasks(workspace) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    try:
        creator_id = _seed_creator(conn)
        task_id = MonitorTaskRepo(conn).enqueue(
            creator_id=creator_id,
            task_type="download",
            dedupe_key=f"test-dl:{creator_id}",
        )
        assert task_id
        conn.execute(
            "UPDATE monitor_tasks SET status = 'running', started_at = datetime('now') WHERE id = ?",
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    result = recover_stale_work(cfg, older_than_sec=0)
    assert result["monitor_tasks_reset"] >= 1

    body = get_work_queue(cfg)
    assert not any(t["status"] == "running" for t in body["monitor_tasks"])
