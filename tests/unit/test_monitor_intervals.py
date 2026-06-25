from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig, BilibiliPlatformConfig, MonitorConfig, PlatformsConfig
from media2text.core.monitor.intervals import (
    bilibili_archive_poll_sec,
    bilibili_dynamic_poll_sec,
    compute_slow_tick_sleep_sec,
    content_poll_fallback_sec,
    vod_poll_interval_sec,
)
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def test_bilibili_archive_poll_uses_platform_config() -> None:
    cfg = AppConfig(
        platforms=PlatformsConfig(
            bilibili=BilibiliPlatformConfig(archive_poll_interval_sec=180)
        )
    )
    assert bilibili_archive_poll_sec(cfg) == 180
    assert bilibili_dynamic_poll_sec(cfg) == 120
    assert vod_poll_interval_sec(cfg) == 300


def test_content_poll_fallback_is_min_of_polls() -> None:
    cfg = AppConfig(
        monitor=MonitorConfig(vod_poll_interval_sec=300),
        platforms=PlatformsConfig(
            bilibili=BilibiliPlatformConfig(
                archive_poll_interval_sec=120,
                dynamic_poll_interval_sec=60,
            )
        ),
    )
    assert content_poll_fallback_sec(cfg) == 60


def test_slow_tick_sleep_immediate_when_vod_due_null(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAnullvod",
        profile_url="https://example.com/u",
        monitor_enabled=True,
        platform="douyin",
    )
    repo.set_content_sync_enabled(cid, enabled=True)
    assert compute_slow_tick_sleep_sec(cfg, conn) == 1.0


def test_slow_tick_sleep_waits_until_next_due(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    repo = CreatorRepo(conn)
    cid = repo.add(
        sec_uid="MS4wLjABAAAAfuturevod",
        profile_url="https://example.com/u",
        monitor_enabled=True,
        platform="douyin",
    )
    repo.set_content_sync_enabled(cid, enabled=True)
    future = (datetime.now(timezone.utc) + timedelta(seconds=45)).isoformat()
    repo.set_vod_due(cid, future)
    sleep_sec = compute_slow_tick_sleep_sec(cfg, conn)
    assert 40.0 <= sleep_sec <= 46.0


def test_slow_tick_sleep_fallback_when_no_content_creators(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        monitor=MonitorConfig(vod_poll_interval_sec=90),
        platforms=PlatformsConfig(
            bilibili=BilibiliPlatformConfig(
                archive_poll_interval_sec=120,
                dynamic_poll_interval_sec=60,
            )
        ),
    )
    conn = open_db(cfg)
    assert compute_slow_tick_sleep_sec(cfg, conn) == 60.0
