from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, MonitorConfig
from media2text.core.live.probe import run_live_probe_tick
from media2text.core.live.probe_guard import ProbeExecutionGuard, ProbeViolationError
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo


def test_probe_guard_records_enqueue_violation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAguard2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    ProbeExecutionGuard.enter_probe_tick()
    try:
        MonitorTaskRepo(conn).enqueue(
            creator_id=cid,
            task_type="sync_catalog",
            dedupe_key=f"sync_catalog:{cid}",
        )
    finally:
        with pytest.raises(ProbeViolationError) as exc:
            ProbeExecutionGuard.exit_probe_tick(strict=True)
    assert "enqueue" in exc.value.violations


def test_probe_guard_no_violation_outside_tick() -> None:
    ProbeExecutionGuard.record_violation("should_not_append")
    ProbeExecutionGuard.exit_probe_tick(strict=True)


def test_probe_never_enqueues(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(reconciler_enabled=True),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAguard1",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )

    douyin = MagicMock()
    douyin.run_poll_active.return_value = {"active": 0}
    douyin.run_probe_observe.return_value = {"probe": True}
    douyin.run_finalize.return_value = {"active": 0}
    bilibili = MagicMock()
    bilibili.run_poll_active.return_value = {"active": 0}
    bilibili.run_probe_observe.return_value = {"probe": True}
    bilibili.run_finalize.return_value = {"active": 0}

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("enqueue in probe")

    monkeypatch.setattr(MonitorTaskRepo, "enqueue", fail_enqueue)

    run_live_probe_tick(cfg, douyin=douyin, bilibili=bilibili)
    ProbeExecutionGuard.exit_probe_tick(strict=True)


def test_start_recording_violation_in_probe_tick() -> None:
    from media2text.core.live.recording import LiveRecordingCore

    ProbeExecutionGuard.enter_probe_tick()
    try:
        LiveRecordingCore._start_recording(
            MagicMock(),
            "c1",
            "sec",
            "room",
            MagicMock(),
        )
    except Exception:
        pass
    finally:
        with pytest.raises(ProbeViolationError) as exc:
            ProbeExecutionGuard.exit_probe_tick(strict=True)
    assert "_start_recording" in exc.value.violations


def test_guarded_popen_records_violation() -> None:
    from media2text.core.live.probe_guard import guarded_popen

    ProbeExecutionGuard.enter_probe_tick()
    try:
        with patch("subprocess.Popen", return_value=MagicMock()):
            guarded_popen(["echo", "hi"])
    finally:
        with pytest.raises(ProbeViolationError) as exc:
            ProbeExecutionGuard.exit_probe_tick(strict=True)
    assert "Popen" in exc.value.violations
