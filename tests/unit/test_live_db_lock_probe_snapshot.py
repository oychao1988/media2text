"""DL-1: probe I/O decoupled from DB; serial snapshot persist."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.live.snapshot import persist_live_probe_result
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import CreatorRepo, LiveSnapshotRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_probe_live_parallel_persists_all_snapshots(tmp_path, monkeypatch) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    creators = []
    for i in range(4):
        cid = repo.add(
            sec_uid=f"sec_parallel_{i}",
            profile_url=f"https://www.douyin.com/user/sec_parallel_{i}",
            platform="douyin",
            monitor_enabled=True,
        )
        creators.append(repo.get(cid))
    conn.close()

    live = LiveRoomInfo(room_id="r1", is_live=False)
    adapter = MagicMock()
    adapter.get_live_room.return_value = live

    core = LiveRecordingCore(
        cfg,
        conn=open_db(cfg),
        adapter=adapter,
        platform="douyin",
        notify=MagicMock(),
    )

    errors, auth_required, platform_changed = core.probe_live()

    assert errors == []
    assert auth_required is False
    assert platform_changed is False

    verify = open_db(cfg)
    try:
        for creator in creators:
            assert creator is not None
            snap = LiveSnapshotRepo(verify).get(creator.id)
            assert snap is not None
            assert snap.is_live == 0
    finally:
        verify.close()


def test_observe_for_probe_does_not_open_db_during_fetch(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_fetch",
        profile_url="https://www.douyin.com/user/sec_fetch",
        platform="douyin",
        monitor_enabled=True,
    )
    creator = CreatorRepo(conn).get(cid)
    conn.close()

    live = LiveRoomInfo(room_id="r1", is_live=True, title="t")
    in_fetch = {"value": False}

    def slow_fetch(_creator):
        in_fetch["value"] = True
        time.sleep(0.05)
        in_fetch["value"] = False
        return live, None

    core = LiveRecordingCore(
        cfg,
        conn=open_db(cfg),
        adapter=MagicMock(),
        platform="douyin",
        notify=MagicMock(),
    )

    real_open = open_db

    def tracked_open(app_cfg):
        assert not in_fetch["value"], "open_db must not run during live fetch I/O"
        return real_open(app_cfg)

    with patch("media2text.core.live.snapshot.open_db", side_effect=tracked_open):
        with patch.object(core, "_fetch_live_info", side_effect=slow_fetch):
            info, err = core._observe_for_probe(creator)

    assert err is None
    assert info is not None
    snap = LiveSnapshotRepo(open_db(cfg)).get(cid)
    assert snap is not None
    assert snap.is_live == 1


def test_concurrent_persist_live_probe_result_no_lock_error(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cfg.ensure_workspace()
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    ids = []
    for i in range(8):
        ids.append(
            repo.add(
                sec_uid=f"sec_lock_{i}",
                profile_url=f"https://www.douyin.com/user/sec_lock_{i}",
                platform="douyin",
                monitor_enabled=True,
            )
        )
    conn.close()

    live = LiveRoomInfo(room_id="r", is_live=True, title="live")
    errors: list[str] = []

    def worker(cid: str) -> None:
        try:
            persist_live_probe_result(cfg, cid, live)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(cid,)) for cid in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []

    verify = open_db(cfg)
    try:
        for cid in ids:
            snap = LiveSnapshotRepo(verify).get(cid)
            assert snap is not None
            assert snap.is_live == 1
    finally:
        verify.close()
