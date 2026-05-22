from unittest.mock import patch

from media2text.core.config import AppConfig
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import CreatorRepo


def test_monitor_run_once_vod_tick(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    watcher = MonitorWatcher(cfg)
    cid = CreatorRepo(watcher._conn).add(
        sec_uid="MS4wLjABAAAAvod",
        profile_url="https://example.com/vod",
        monitor_enabled=True,
    )
    live_stub = {"started": [], "active": 0, "errors": [], "auth_required": False}
    with (
        patch.object(watcher._douyin_live, "run_once", return_value=live_stub),
        patch.object(
            watcher._bilibili_live,
            "run_once",
            return_value={**live_stub, "platform": "bilibili", "checked": 0},
        ),
        patch(
            "media2text.core.monitor.watcher.run_pipeline",
            return_value={
                "ok": True,
                "sync": {"ok": True},
                "download": {"ok": True, "downloaded": 0},
                "transcribed": 0,
                "errors": [],
                "auth_required": False,
            },
        ) as mock_pipeline,
    ):
        result = watcher.run_once(creator_id=cid)
    mock_pipeline.assert_called_once_with(cfg, creator_id=cid)
    assert result["vod"]["creators"] == 1
    assert len(result["vod"]["results"]) == 1
    assert result["archive"]["creators"] == 0
    assert "dynamic" in result
