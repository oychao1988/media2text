"""Register bvid from dynamics or other sources without duplicate awemes rows."""

from __future__ import annotations

from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo


def register_bvid(
    awemes: AwemeRepo,
    *,
    creator_id: str,
    bvid: str,
    title: str | None = None,
    create_time: int | None = None,
) -> bool:
    """Upsert archive row by bvid; returns True if newly listed."""
    bvid = bvid.strip()
    if not bvid.startswith("BV"):
        return False
    return awemes.upsert_listed(
        creator_id=creator_id,
        item=AwemeItem(aweme_id=bvid, title=title, create_time=create_time),
    )
