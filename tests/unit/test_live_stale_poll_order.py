"""mark_stale must not skip dead ffmpeg when poll already set obs_ffmpeg_alive=0."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.live.state_writer import StateWriter
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
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


def test_mark_stale_does_not_skip_obs_ffmpeg_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstale",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    conn.execute(
        """
        UPDATE live_sessions SET
          started_at = ?,
          obs_ffmpeg_alive = 0
        WHERE id = ?
        """,
        (old, sid),
    )
    conn.commit()

    writer = StateWriter(conn, cfg=cfg)
    cleared = writer.mark_stale_recordings_failed()
    assert cleared == 1
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "stale_recording"


def test_mark_stale_skips_offline_pending_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAoffline",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    LiveSessionRepo(conn).set_offline_since(sid, past)
    conn.execute(
        "UPDATE live_sessions SET obs_ffmpeg_alive = 0 WHERE id = ?",
        (sid,),
    )
    conn.commit()

    writer = StateWriter(conn, cfg=cfg)
    cleared = writer.mark_stale_recordings_failed()
    assert cleared == 0
    row = LiveSessionRepo(conn).get(sid)
    assert row is not None
    assert row.status == "recording"
