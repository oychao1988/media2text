"""Fallback archive listing from locally synced dynamics when arc/search is rate-limited."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from media2text.core.platform.douyin.models import AwemeItem


def _parse_create_time(published_at: str | None) -> int | None:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except ValueError:
        return None


def list_awemes_from_dynamics_workspace(creator_root: Path) -> list[AwemeItem]:
    """Collect BV* from dynamics/*/meta.json (refs.bvid) after sync-dynamics."""
    dynamics_dir = creator_root / "dynamics"
    if not dynamics_dir.is_dir():
        return []

    seen: set[str] = set()
    items: list[AwemeItem] = []
    for meta_path in sorted(dynamics_dir.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        refs = meta.get("refs") or {}
        bvid = refs.get("bvid") if isinstance(refs, dict) else None
        if not bvid or not str(bvid).startswith("BV"):
            continue
        bvid_str = str(bvid).strip()
        if bvid_str in seen:
            continue
        seen.add(bvid_str)
        title = None
        content_md = meta_path.parent / "content.md"
        if content_md.is_file():
            first = content_md.read_text(encoding="utf-8").splitlines()[:1]
            if first and first[0].strip():
                title = first[0].strip().lstrip("# ").strip()
        items.append(
            AwemeItem(
                aweme_id=bvid_str,
                title=title,
                create_time=_parse_create_time(meta.get("published_at")),
            )
        )
    return items
