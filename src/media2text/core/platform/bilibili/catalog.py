from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.auth import session_path
from media2text.core.platform.bilibili.httpx_client import client_from_storage


def build_adapter(cfg: AppConfig) -> BilibiliAdapterV1:
    ws = cfg.ensure_workspace()
    session = session_path(ws)
    if session.is_file():
        return BilibiliAdapterV1(client_from_storage(session), session_path=session)
    return BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)
