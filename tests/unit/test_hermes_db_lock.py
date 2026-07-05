import threading

from media2text.agent.hermes_state import SessionDB
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway


def test_hermes_write_uses_shared_db_lock(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    cfg = AppConfig(workspace=ws)
    ensure_write_gateway_started(cfg)
    try:
        db_path = ws / "media2text.db"
        conn_a = connect(db_path)
        conn_b = connect(db_path)
        SessionDB(conn_a, cfg=cfg)
        db_b = SessionDB(conn_b, cfg=cfg)

        held = threading.Event()
        release = threading.Event()
        errors: list[Exception] = []

        def hold_write_lock() -> None:
            try:
                conn_a.execute("BEGIN IMMEDIATE")
                held.set()
                release.wait(timeout=5)
                conn_a.commit()
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=hold_write_lock)
        t.start()
        assert held.wait(timeout=5)

        db_b.create_session(display_thread_id="thread-b", title="B")
        release.set()
        t.join(timeout=5)

        assert not errors
        row = db_b.get_thread_by_display_id("thread-b")
        assert row is not None
        conn_a.close()
        conn_b.close()
    finally:
        shutdown_write_gateway()
