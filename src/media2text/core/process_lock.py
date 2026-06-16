import os
from contextlib import contextmanager
from pathlib import Path


class LockError(Exception):
    pass


def clear_stale_workspace_lock(lock_path: Path) -> bool:
    if lock_path.name == ".monitor-watch.lock":
        from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock

        return clear_invalid_monitor_lock(lock_path)
    if not lock_path.is_file():
        return False
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
        pid = int(raw) if raw else None
    except (OSError, ValueError):
        lock_path.unlink(missing_ok=True)
        return True

    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    if pid is None or not _pid_alive(pid):
        lock_path.unlink(missing_ok=True)
        return True
    return False


def acquire_workspace_lock(lock_path: Path) -> int:
    """Create exclusive workspace lock; caller must call release_workspace_lock."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    clear_stale_workspace_lock(lock_path)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LockError(f"lock already held: {lock_path}") from exc
    if lock_path.name == ".monitor-watch.lock":
        from media2text.core.runtime.monitor_lock import write_lock_record

        os.close(fd)
        write_lock_record(lock_path, pid=os.getpid(), mode="embedded")
        return -1
    os.write(fd, str(os.getpid()).encode())
    return fd


def release_workspace_lock(lock_path: Path, fd: int | None) -> None:
    if fd is not None and fd >= 0:
        try:
            os.close(fd)
        except OSError:
            pass
    lock_path.unlink(missing_ok=True)


@contextmanager
def workspace_lock(lock_path: Path):
    fd = acquire_workspace_lock(lock_path)
    try:
        yield
    finally:
        release_workspace_lock(lock_path, fd)
