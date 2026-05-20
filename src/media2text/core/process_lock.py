import os
from contextlib import contextmanager
from pathlib import Path


class LockError(Exception):
    pass


@contextmanager
def workspace_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LockError(f"lock already held: {lock_path}") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)
