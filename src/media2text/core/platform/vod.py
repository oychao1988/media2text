"""Platform-dispatching VOD sync and download (Douyin aweme / Bilibili archive)."""

from __future__ import annotations

from typing import Literal

from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

SyncMode = Literal["full", "incremental"]


def sync_creator(cfg: AppConfig, creator_id: str, *, mode: SyncMode = "full") -> dict:
    conn = open_db(cfg)
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return {"ok": False, "error": "creator not found"}
    if creator.platform == "bilibili":
        from media2text.core.platform.bilibili.catalog import sync_creator as bili_sync

        return bili_sync(cfg, creator_id, mode=mode)
    from media2text.core.platform.douyin.catalog import sync_creator as dy_sync

    return dy_sync(cfg, creator_id, mode=mode)


def _merge_download_results(parts: list[dict]) -> dict:
    if not parts:
        return {"ok": True, "downloaded": 0, "failed": 0, "errors": []}
    downloaded = sum(int(p.get("downloaded") or 0) for p in parts)
    failed = sum(int(p.get("failed") or 0) for p in parts)
    errors: list[dict] = []
    for p in parts:
        errors.extend(p.get("errors") or [])
    return {
        "ok": all(p.get("ok", False) for p in parts) and failed == 0,
        "downloaded": downloaded,
        "failed": failed,
        "errors": errors,
    }


def download_pending(
    cfg: AppConfig,
    *,
    creator_id: str | None = None,
    limit: int | None = None,
) -> dict:
    if creator_id:
        conn = open_db(cfg)
        creator = CreatorRepo(conn).get(creator_id)
        if not creator:
            return {"ok": False, "downloaded": 0, "failed": 0, "errors": []}
        if creator.platform == "bilibili":
            from media2text.core.platform.bilibili.download import download_pending as bili_dl

            return bili_dl(cfg, creator_id=creator_id, limit=limit)
        from media2text.core.platform.douyin.download import download_pending as dy_dl

        return dy_dl(cfg, creator_id=creator_id, limit=limit)

    from media2text.core.platform.bilibili.download import download_pending as bili_dl
    from media2text.core.platform.douyin.download import download_pending as dy_dl

    return _merge_download_results(
        [
            dy_dl(cfg, creator_id=None, limit=limit),
            bili_dl(cfg, creator_id=None, limit=limit),
        ]
    )
