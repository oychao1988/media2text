import threading

from media2text.core.config import AppConfig
from media2text.core.storage import db as db_module
from media2text.core.storage.db import connect
from media2text.core.workspace import open_db


def test_connect_runs_migrations_once_per_db_path(tmp_path, monkeypatch) -> None:
    db = tmp_path / "data" / "media2text.db"
    calls: list[int] = []
    original = db_module._run_migrations

    def spy(conn) -> None:
        calls.append(1)
        original(conn)

    monkeypatch.setattr(db_module, "_run_migrations", spy)
    connect(db)
    connect(db)
    assert len(calls) == 1


def test_open_db_migrations_once_per_process(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    calls: list[int] = []
    original = db_module._run_migrations

    def spy(conn) -> None:
        calls.append(1)
        original(conn)

    monkeypatch.setattr(db_module, "_run_migrations", spy)
    open_db(cfg)
    open_db(cfg)
    assert len(calls) == 1


def test_concurrent_first_connect_runs_migrations_once(tmp_path, monkeypatch) -> None:
    db = tmp_path / "data" / "media2text.db"
    calls: list[int] = []
    original = db_module._run_migrations

    def spy(conn) -> None:
        calls.append(1)
        original(conn)

    monkeypatch.setattr(db_module, "_run_migrations", spy)
    barrier = threading.Barrier(4)

    def worker() -> None:
        barrier.wait()
        connect(db)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert len(calls) == 1
