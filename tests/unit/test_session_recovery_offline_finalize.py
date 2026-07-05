"""CRITICAL 7/3 regression: offline + dead ffmpeg must enqueue finalize immediately."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.live.session_recovery import recover_orphan_sessions
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


@pytest.fixture(autouse=True)
def _reset_gateway() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


def test_offline_dead_ffmpeg_with_obs_zero_enqueues_finalize(tmp_path, monkeypatch) -> None:
    """7/3 zombie: obs_ffmpeg_alive=0 must not block finalize recovery."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"offline_confirm_sec": 45})
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAzombie",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    LiveSessionRepo(conn).set_offline_since(sid, past)
    conn.execute(
        """
        UPDATE live_sessions SET
          obs_ffmpeg_alive = 0,
          obs_still_live = 0
        WHERE id = ?
        """,
        (sid,),
    )
    conn.commit()

    ensure_write_gateway_started(cfg)
    count = recover_orphan_sessions(cfg, conn)
    assert count >= 1
    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.obs_still_live == 0
