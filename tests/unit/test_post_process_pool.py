from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig
from media2text.core.live.post_process_pool import PostProcessExecutor


def test_submit_returns_immediately_while_job_runs(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    barrier = threading.Event()

    def slow_job(*_args, **_kwargs) -> dict:
        barrier.wait(timeout=5)
        return {"ok": True}

    monkeypatch.setattr(
        "media2text.core.live.post_process_pool.run_post_process_job",
        slow_job,
    )
    pool = PostProcessExecutor(max_workers=1)
    t0 = time.monotonic()
    pool.submit(cfg, job_id="j1", notify=MagicMock())
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5
    barrier.set()
    pool.shutdown(wait=True)


def test_submit_worker_uses_own_db_connection(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    open_count = 0
    conn_ids: list[int] = []
    caller_conn = MagicMock()
    caller_conn_id = id(caller_conn)

    real_open_db = __import__(
        "media2text.core.workspace", fromlist=["open_db"]
    ).open_db

    def counting_open_db(app_cfg: AppConfig):
        nonlocal open_count
        open_count += 1
        conn = real_open_db(app_cfg)
        conn_ids.append(id(conn))
        return conn

    monkeypatch.setattr(
        "media2text.core.live.post_process_pool.open_db",
        counting_open_db,
    )
    done = threading.Event()

    def finish_job(*_args, **_kwargs) -> dict:
        done.set()
        return {"ok": True}

    monkeypatch.setattr(
        "media2text.core.live.post_process_pool.run_post_process_job",
        finish_job,
    )

    pool = PostProcessExecutor(max_workers=1)
    pool.submit(cfg, job_id="j1", notify=MagicMock())
    assert done.wait(timeout=5)
    pool.shutdown(wait=True)

    assert open_count >= 1
    assert caller_conn_id not in conn_ids


def test_drain_pending_submits_without_blocking(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    submitted: list[str] = []

    pool = PostProcessExecutor(max_workers=1)

    def capture_submit(_cfg, *, job_id: str, notify) -> None:
        submitted.append(job_id)

    monkeypatch.setattr(pool, "submit", capture_submit)

    with patch.object(
        __import__(
            "media2text.core.storage.repos", fromlist=["PostProcessJobRepo"]
        ).PostProcessJobRepo,
        "claim_pending",
        return_value=[MagicMock(id="job-a"), MagicMock(id="job-b")],
    ):
        t0 = time.monotonic()
        pool.drain_pending(cfg, conn, notify=MagicMock(), limit=2)
        elapsed = time.monotonic() - t0

    assert elapsed < 0.5
    assert submitted == ["job-a", "job-b"]
    pool.shutdown(wait=False)
    conn.close()
