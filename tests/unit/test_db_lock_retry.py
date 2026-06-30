import sqlite3

from media2text.core.storage.db import with_db_lock_retry


def test_with_db_lock_retry_succeeds_after_locked() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    assert with_db_lock_retry(flaky) == "ok"
    assert calls["n"] == 2


def test_with_db_lock_retry_reraises_non_lock_errors() -> None:
    def bad() -> None:
        raise sqlite3.OperationalError("no such table: foo")

    try:
        with_db_lock_retry(bad)
    except sqlite3.OperationalError as exc:
        assert "no such table" in str(exc)
    else:
        raise AssertionError("expected OperationalError")
