from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.adapter import DouyinAdapterV1
from media2text.core.platform.douyin.auth import session_path
from media2text.core.platform.douyin.httpx_client import client_from_storage
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def build_adapter(cfg: AppConfig) -> DouyinAdapterV1:
    ws = cfg.ensure_workspace()
    session = session_path(ws)
    if session.is_file():
        return DouyinAdapterV1(client_from_storage(session), session_path=session)
    from media2text.core.platform.douyin.live import FIXTURE_ROOT

    return DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)


def sync_creator(cfg: AppConfig, creator_id: str) -> dict:
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    awemes = AwemeRepo(conn)
    creator = creators.get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator not found"}

    adapter = build_adapter(cfg)
    max_pages = cfg.platforms.douyin.max_sync_pages
    cursor = ""
    pages = 0
    new_count = 0
    total_listed = 0

    while True:
        items, next_cursor, has_more = adapter.list_awemes(sec_uid=creator.sec_uid, max_cursor=cursor)
        for item in items:
            if awemes.upsert_listed(creator_id=creator.id, item=item):
                new_count += 1
            total_listed += 1
        pages += 1
        if not has_more or not next_cursor:
            break
        if max_pages and pages >= max_pages:
            break
        cursor = next_cursor

    return {
        "ok": True,
        "creator_id": creator_id,
        "new_count": new_count,
        "total_listed": total_listed,
        "pages": pages,
        "auth_required": False,
    }
