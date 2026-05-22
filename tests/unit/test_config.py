from pathlib import Path

from media2text.core.config import AppConfig


def test_load_config_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.load()
    assert cfg.workspace == Path("./data")
    assert cfg.platforms.douyin.poll_interval_sec == 60
    assert cfg.platforms.bilibili.dynamic_poll_interval_sec == 120
