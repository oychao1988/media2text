import json
from unittest.mock import patch

from media2text.core.config import AppConfig
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.platform.bilibili.adapter import FIXTURE_ROOT
from media2text.core.platform.bilibili.dynamic import sync_creator_dynamics
from media2text.core.platform.bilibili.parse import parse_dynamic_feed
from media2text.core.storage.db import connect
from media2text.core.manifest import refresh_manifest
from media2text.core.storage.repos import CreatorRepo, DynamicRepo


def _load_feed_fixture() -> dict:
    return json.loads((FIXTURE_ROOT / "feed_space.json").read_text())


def test_parse_dynamic_feed_fixture() -> None:
    items, next_offset, has_more = parse_dynamic_feed(_load_feed_fixture())
    assert len(items) == 2
    assert has_more is False
    assert next_offset is None

    opus = items[0]
    assert opus.dynamic_id == "dyn_opus_001"
    assert opus.dynamic_type == "draw"
    assert "opus fixture" in opus.text
    assert len(opus.image_urls) == 2
    assert opus.image_urls[0].endswith("fixture_img1.png")

    av = items[1]
    assert av.dynamic_id == "dyn_av_002"
    assert av.dynamic_type == "av"
    assert av.bvid == "BV1fixture00001"
    assert "Fixture archive" in av.text
    assert av.image_urls and av.image_urls[0].endswith("fixture_cover.jpg")


def test_sync_creator_dynamics_persists_files_and_dedupes_bvid(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = connect(cfg.ensure_workspace() / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
        monitor_enabled=True,
    )

    first = sync_creator_dynamics(cfg, cid)
    assert first["ok"] is True
    assert first["new_count"] == 2
    assert first["images_downloaded"] == 3
    assert first["bvid_registered"] == 1

    base = cfg.ensure_workspace() / "creators" / "12345"
    opus_dir = base / "dynamics" / "dyn_opus_001"
    assert "Hello from opus fixture body." in (opus_dir / "content.md").read_text(encoding="utf-8")
    meta = json.loads((opus_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["dynamic_id"] == "dyn_opus_001"
    assert len(meta["image_urls"]) == 2

    av_meta = json.loads((base / "dynamics" / "dyn_av_002" / "meta.json").read_text())
    assert av_meta["refs"]["bvid"] == "BV1fixture00001"
    aweme_row = conn.execute(
        "SELECT aweme_id FROM awemes WHERE aweme_id = ?",
        ("BV1fixture00001",),
    ).fetchone()
    assert aweme_row is not None

    dynamics = DynamicRepo(conn)
    assert dynamics.is_synced("dyn_opus_001")
    assert dynamics.is_synced("dyn_av_002")

    manifest_path = refresh_manifest(
        conn, sec_uid="12345", workspace=cfg.ensure_workspace(), platform="bilibili"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["platform"] == "bilibili"
    assert len(manifest["dynamics"]) == 2
    assert manifest["dynamics"][0]["dynamic_id"] in ("dyn_opus_001", "dyn_av_002")
    assert any("content_md" in d for d in manifest["dynamics"])

    second = sync_creator_dynamics(cfg, cid)
    assert second["new_count"] == 0
    assert second["images_downloaded"] == 0


def test_max_dynamic_images_per_item_truncates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        platforms={
            "bilibili": {
                "download_dynamic_images": True,
                "max_dynamic_images_per_item": 1,
            }
        },
    )
    conn = connect(cfg.ensure_workspace() / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="999",
        profile_url="https://space.bilibili.com/999",
        platform="bilibili",
    )
    outcome = sync_creator_dynamics(cfg, cid)
    assert outcome["ok"] is True
    row = DynamicRepo(conn).get("dyn_opus_001")
    assert row is not None
    assert row.image_count <= 1
    meta = json.loads(
        (
            cfg.ensure_workspace()
            / "creators"
            / "999"
            / "dynamics"
            / "dyn_opus_001"
            / "meta.json"
        ).read_text()
    )
    assert len(meta["image_urls"]) == 1


def test_slow_tick_includes_dynamic_tick(tmp_path, monkeypatch) -> None:
    import threading

    from media2text.core.live.scheduler import SlowTickLoop

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    dynamic_stub = {
        "platform": "bilibili",
        "creators": 1,
        "marked": 1,
        "interval_sec": 120,
        "errors": [],
        "auth_required": False,
        "platform_changed": False,
    }

    def record_wait(timeout=None):
        stop.set()
        return True

    stop.wait = record_wait  # type: ignore[method-assign]

    with (
        patch.object(watcher, "_run_vod_tick", return_value={}),
        patch.object(watcher, "_run_archive_tick", return_value={}),
        patch.object(watcher, "_run_dynamic_tick", return_value=dynamic_stub) as mock_dynamic,
    ):
        SlowTickLoop(watcher, cfg, creator_id=None, stop=stop)._run()

    mock_dynamic.assert_called_once()
    assert mock_dynamic.return_value["interval_sec"] == 120


def test_run_dynamic_tick_marks_bilibili_due(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = MonitorWatcher(cfg)
    conn = connect(cfg.ensure_workspace() / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
        monitor_enabled=True,
    )
    CreatorRepo(conn).set_content_sync_enabled(cid, enabled=True)

    result = watcher._run_dynamic_tick(conn=conn, creator_id=cid)

    row = CreatorRepo(conn).get(cid)
    conn.close()
    assert result["platform"] == "bilibili"
    assert result["interval_sec"] == cfg.platforms.bilibili.dynamic_poll_interval_sec
    assert row is not None
    assert row.dynamic_due_at is not None


def test_dynamics_table_roundtrip(tmp_path) -> None:
    conn = connect(tmp_path / "db.sqlite")
    CreatorRepo(conn).add(
        sec_uid="mid1",
        profile_url="https://space.bilibili.com/mid1",
        platform="bilibili",
    )
    c1 = conn.execute("SELECT id FROM creators WHERE sec_uid = ?", ("mid1",)).fetchone()[0]
    repo = DynamicRepo(conn)
    assert repo.upsert_listed(
        creator_id=c1,
        dynamic_id="d1",
        dynamic_type="opus",
        text="hello",
        refs_json='{"bvid":"BV1test"}',
        local_dir="dynamics/d1",
        published_at="2026-01-01T00:00:00+00:00",
    )
    repo.mark_synced("d1", image_count=2, text="hello")
    row = repo.get("d1")
    assert row is not None
    assert row.sync_status == "synced"
    assert row.image_count == 2
    assert repo.is_synced("d1")
