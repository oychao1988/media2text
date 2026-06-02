from pathlib import Path

from media2text.core.config import AppConfig, LiveConfig


def test_load_config_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.load()
    assert cfg.workspace == Path("./data")
    assert cfg.platforms.douyin.poll_interval_sec == 60
    assert cfg.platforms.bilibili.dynamic_poll_interval_sec == 120


def test_summarize_config_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.load()
    assert cfg.summarize.enabled is False
    assert len(cfg.summarize.llm.providers) == 1
    assert cfg.summarize.llm.providers[0].name == "nvidia"
    assert cfg.summarize.llm.providers[0].models == ["deepseek-ai/deepseek-v4-pro"]
    assert cfg.summarize.merge_gap_minutes == 60


def test_live_config_recording_defaults() -> None:
    lc = LiveConfig()
    assert lc.live_poll_interval_sec == 20
    assert lc.offline_confirm_polls == 3
    assert lc.ffmpeg_exit_recheck is True
    assert lc.max_reconnect_attempts == 2
    assert lc.min_recording_sec_before_offline_end == 45
