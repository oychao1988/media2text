import json
import os
from pathlib import Path

import pytest

from media2text.core.process_lock import LockError, acquire_workspace_lock, release_workspace_lock, workspace_lock


def test_workspace_lock_exclusive(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"
    with workspace_lock(lock_path):
        with pytest.raises(LockError):
            with workspace_lock(lock_path):
                pass
    assert not lock_path.exists()


def test_workspace_lock_clears_stale_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"
    lock_path.write_text("999999999", encoding="utf-8")
    with workspace_lock(lock_path):
        assert lock_path.read_text(encoding="utf-8") == str(os.getpid())
    assert not lock_path.exists()


def test_workspace_lock_clears_pid_reused_by_other_process(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / ".monitor-watch.lock"
    lock_path.write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._pid_alive",
        lambda pid: pid == 581,
    )
    with workspace_lock(lock_path):
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()


def test_acquire_monitor_watch_lock_writes_json(tmp_path: Path) -> None:
    lock_path = tmp_path / ".monitor-watch.lock"
    fd = acquire_workspace_lock(lock_path)
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        assert "monitor" in data["argv"]
    finally:
        release_workspace_lock(lock_path, fd)
