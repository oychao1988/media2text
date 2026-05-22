import pytest

from media2text.core.config import AppConfig
from media2text.core.errors import ConfigError
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.registry import get_adapter


def test_get_adapter_douyin_uses_fixture_without_session(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    adapter = get_adapter("douyin", cfg)
    assert isinstance(adapter, DouyinAdapterV1)
    profile = adapter.get_user_profile(sec_uid="MS4wLjABAAAAtest")
    assert profile.display_name


def test_get_adapter_bilibili_not_implemented() -> None:
    with pytest.raises(ConfigError, match="not implemented"):
        get_adapter("bilibili", AppConfig())


def test_get_adapter_unknown_platform() -> None:
    with pytest.raises(ConfigError, match="unsupported platform"):
        get_adapter("tiktok", AppConfig())
