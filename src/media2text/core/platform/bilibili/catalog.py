from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.auth import session_path
from media2text.core.platform.bilibili.httpx_client import client_from_storage
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db


def build_adapter(cfg: AppConfig) -> BilibiliAdapterV1:
    ws = cfg.ensure_workspace()
    session = session_path(ws)
    if session.is_file():
        return BilibiliAdapterV1(client_from_storage(session), session_path=session)
    return BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)


def sync_creator(cfg: AppConfig, creator_id: str) -> dict:
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    awemes = AwemeRepo(conn)
    creator = creators.get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator not found"}
    if creator.platform != "bilibili":
        return {"ok": False, "error": "creator is not bilibili"}

    adapter = build_adapter(cfg)
    max_pages = cfg.platforms.bilibili.max_sync_pages
    cursor = ""
    pages = 0
    new_count = 0
    total_listed = 0

    try:
        while True:
            items, next_cursor, has_more = adapter.list_awemes(
                sec_uid=creator.sec_uid, max_cursor=cursor
            )
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
    except AuthRequired as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "auth_required": True,
            "platform_changed": False,
            "error": str(exc),
        }
    except PlatformChanged as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "auth_required": False,
            "platform_changed": True,
            "error": str(exc),
        }
    except ParseFailed as exc:
        return {
            "ok": False,
            "creator_id": creator_id,
            "auth_required": False,
            "platform_changed": True,
            "error": str(exc),
        }

    return {
        "ok": True,
        "creator_id": creator_id,
        "new_count": new_count,
        "total_listed": total_listed,
        "pages": pages,
        "auth_required": False,
        "platform_changed": False,
    }
