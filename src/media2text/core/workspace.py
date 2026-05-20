from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.storage.db import connect


def db_path(workspace: Path) -> Path:
    return workspace / "media2text.db"


def open_db(cfg: AppConfig):
    ws = cfg.ensure_workspace()
    return connect(db_path(ws))
