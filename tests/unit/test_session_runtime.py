from unittest.mock import MagicMock

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.session_runtime import SessionRuntime
from media2text.core.notify import NotifyService
from media2text.core.workspace import open_db


def test_session_runtime_shared_across_worker_threads(tmp_path, monkeypatch) -> None:
    """Two cores with separate open_db share ffmpeg process map via SessionRuntime."""
    monkeypatch.chdir(tmp_path)
    runtime = SessionRuntime()
    cfg = AppConfig(workspace=tmp_path / "data")
    conn_a = open_db(cfg)
    conn_b = open_db(cfg)
    adapter = MagicMock()
    notify = NotifyService(cfg)
    core_a = LiveRecordingCore(
        cfg,
        conn=conn_a,
        adapter=adapter,
        platform="douyin",
        runtime=runtime,
        notify=notify,
    )
    core_b = LiveRecordingCore(
        cfg,
        conn=conn_b,
        adapter=adapter,
        platform="douyin",
        runtime=runtime,
        notify=notify,
    )
    fake_proc = MagicMock()
    runtime.processes["s1"] = fake_proc
    assert "s1" in core_b._processes
    assert core_b._processes["s1"] is fake_proc
    assert core_a._runtime is core_b._runtime
