from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.storage.models import CreatorRow


def effective_auto_record(creator: CreatorRow, cfg: AppConfig) -> bool:
    o = (creator.auto_record_override or "inherit").lower()
    if o == "on":
        return True
    if o == "off":
        return False
    return bool(cfg.live.auto_record)
