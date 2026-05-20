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
