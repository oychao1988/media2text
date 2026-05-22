from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.errors import ConfigError
from media2text.core.platform.base import PlatformAdapter


def get_adapter(platform: str, cfg: AppConfig) -> PlatformAdapter:
    """Return the adapter for *platform* (douyin today; bilibili in later P6 tasks)."""
    key = platform.strip().lower()
    if key == "douyin":
        from media2text.core.platform.douyin.catalog import build_adapter

        return build_adapter(cfg)
    if key == "bilibili":
        raise ConfigError("bilibili platform adapter is not implemented yet (P6)")
    raise ConfigError(f"unsupported platform: {platform!r}")
