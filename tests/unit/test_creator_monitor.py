import json
import sqlite3

from typer.testing import CliRunner

from media2text.cli.main import app
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def test_monitor_enabled_migration_from_watch_live(tmp_path) -> None:
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
        VALUES ('c1', 'douyin', 'sec1', 'https://example.com/u', 1, '2020-01-01T00:00:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    conn2 = connect(db_path)
    row = CreatorRepo(conn2).get("c1")
    assert row is not None
    assert row.monitor_enabled == 1


def test_creator_monitor_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAcli",
        profile_url="https://www.douyin.com/user/cli",
        monitor_enabled=False,
    )
    runner = CliRunner()
    on = runner.invoke(app, ["creator", "monitor", cid, "--json"])
    assert on.exit_code == 0
    assert json.loads(on.stdout)["monitor_enabled"] is True
    off = runner.invoke(app, ["creator", "monitor", cid, "--off", "--json"])
    assert off.exit_code == 0
    assert json.loads(off.stdout)["monitor_enabled"] is False


def test_download_run_monitor_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    monitored = creators.add(
        sec_uid="MS4wLjABAAAAmon",
        profile_url="https://example.com/mon",
        monitor_enabled=True,
    )
    unmonitored = creators.add(
        sec_uid="MS4wLjABAAAAunmon",
        profile_url="https://example.com/unmon",
        monitor_enabled=False,
    )
    from media2text.core.storage.repos import AwemeRepo
    from media2text.core.platform.douyin.models import AwemeItem

    awemes = AwemeRepo(conn)
    awemes.upsert_listed(
        creator_id=monitored,
        item=AwemeItem(aweme_id="111", title="a", create_time=1),
    )
    awemes.upsert_listed(
        creator_id=unmonitored,
        item=AwemeItem(aweme_id="222", title="b", create_time=2),
    )
    pending = awemes.list_pending_download(monitor_only=True)
    assert len(pending) == 1
    assert pending[0].aweme_id == "111"
