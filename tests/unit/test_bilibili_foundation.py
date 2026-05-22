import sqlite3

import pytest
import yaml

from media2text.core.config import AppConfig, BilibiliPlatformConfig, PlatformsConfig
from media2text.core.errors import ConfigError
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo


def test_bilibili_platform_config_defaults() -> None:
    b = BilibiliPlatformConfig()
    assert b.dynamic_poll_interval_sec == 120
    assert b.dynamic_poll_interval_min_sec == 5
    assert b.download_dynamic_images is True


def test_platforms_reject_dynamic_poll_below_min() -> None:
    with pytest.raises(ConfigError, match="dynamic_poll_interval_sec must be >= 5"):
        PlatformsConfig(
            bilibili=BilibiliPlatformConfig(
                dynamic_poll_interval_sec=4,
                dynamic_poll_interval_min_sec=5,
            )
        )


def test_app_config_load_rejects_invalid_bilibili_poll(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "platforms": {
                    "bilibili": {
                        "dynamic_poll_interval_sec": 2,
                        "dynamic_poll_interval_min_sec": 5,
                    }
                }
            }
        )
    )
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    with pytest.raises(ConfigError, match="dynamic_poll_interval_sec must be >= 5"):
        AppConfig.load()


def test_creators_unique_platform_sec_uid_allows_same_sec_uid(tmp_path) -> None:
    db_path = tmp_path / "media2text.db"
    conn = connect(db_path)
    repo = CreatorRepo(conn)
    repo.add(sec_uid="12345", profile_url="https://space.bilibili.com/12345", platform="douyin")
    repo.add(sec_uid="12345", profile_url="https://space.bilibili.com/12345", platform="bilibili")
    rows = conn.execute(
        "SELECT platform, sec_uid FROM creators ORDER BY platform"
    ).fetchall()
    assert len(rows) == 2
    assert [r[0] for r in rows] == ["bilibili", "douyin"]


def test_creators_migration_from_sec_uid_unique(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE creators (
          id TEXT PRIMARY KEY,
          platform TEXT NOT NULL,
          sec_uid TEXT NOT NULL UNIQUE,
          display_name TEXT,
          profile_url TEXT,
          watch_live INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO creators (id, platform, sec_uid, profile_url, watch_live, created_at)
        VALUES ('c1', 'douyin', 'sec1', 'https://example.com/u', 0, '2020-01-01T00:00:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    conn2 = connect(db_path)
    sql = conn2.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='creators'"
    ).fetchone()[0]
    assert "UNIQUE(platform,sec_uid)" in sql.replace(" ", "")
    assert CreatorRepo(conn2).get("c1") is not None
    CreatorRepo(conn2).add(
        sec_uid="sec1",
        profile_url="https://space.bilibili.com/sec1",
        platform="bilibili",
    )
