import os
from pathlib import Path

import pytest

from media2text.core.process_lock import LockError, workspace_lock


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
