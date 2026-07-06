import pytest

from media2text.core.config import AppConfig, LiveConfig
from media2text.core.live.loop import run_live_inline_decisions
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, LiveSnapshotRepo
from media2text.core.workspace import open_db


@pytest.fixture(autouse=True)
def _reset_db_write_gateway() -> None:
    yield
    import media2text.core.storage.write_gateway as wg_mod
    from media2text.core.storage.write_gateway import shutdown_write_gateway

    shutdown_write_gateway()
    wg_mod._gateway = None


def test_live_loop_inline_prepare_no_duplicate(tmp_path, monkeypatch) -> None:
    """Inline decide must not double-prepare when an active session already exists."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(inline_decisions=True, pipeline_mode="streaming"),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAinline",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSnapshotRepo(conn).upsert(cid, is_live=True, room_id="room1")
    conn.close()

    watcher = MonitorWatcher(cfg)
    registry = watcher.ensure_session_registry()
    prepare_calls: list[str] = []

    def _fake_prepare(creator_id: str, *, live_info=None) -> dict:
        prepare_calls.append(creator_id)
        conn2 = open_db(cfg)
        try:
            LiveSessionRepo(conn2).create(
                creator_id=creator_id,
                room_id="room1",
                temp_path=str(tmp_path / "live.flv"),
                ffmpeg_pid=4242,
            )
        finally:
            conn2.close()
        return {"started": {"session_id": "sess-1"}}

    monkeypatch.setattr(registry, "run_prepare", _fake_prepare)

    run_live_inline_decisions(cfg, watcher)
    run_live_inline_decisions(cfg, watcher)

    assert prepare_calls == [cid]


def test_reconcile_live_no_enqueue_when_inline_decisions(tmp_path, monkeypatch) -> None:
    from media2text.core.live.task_reconciler import reconcile_live
    from media2text.core.storage.repos import MonitorTaskRepo

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(inline_decisions=True),
    )
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAinline2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    LiveSnapshotRepo(conn).upsert(cid, is_live=True, room_id="1")
    ensured = reconcile_live(cfg, conn)
    assert ensured == 0
    assert not MonitorTaskRepo(conn).has_active_dedupe(f"prepare:{cid}")
