from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from media2text.core.archive.models import Hit
from media2text.core.archive.search import search_archive


@dataclass
class TimelineResult:
    ok: bool
    keyword: str
    creator_id: str
    days: int
    hits: list[Hit] = field(default_factory=list)
    indexed: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        payload: dict = {
            "ok": self.ok,
            "keyword": self.keyword,
            "creator_id": self.creator_id,
            "days": self.days,
            "sort": "started_at_asc",
            "indexed": self.indexed,
            "hits": [h.to_dict() for h in self.hits],
        }
        if self.error:
            payload["error"] = self.error
        return payload


def _parse_started_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def timeline_archive(
    conn: sqlite3.Connection,
    keyword: str,
    *,
    creator_id: str,
    days: int = 30,
    limit: int = 500,
) -> TimelineResult:
    """Cross-session keyword timeline for one creator, oldest session first."""
    base = search_archive(conn, keyword, creator_id=creator_id, limit=limit)
    if not base.ok:
        return TimelineResult(
            ok=False,
            keyword=keyword,
            creator_id=creator_id,
            days=days,
            indexed=base.indexed,
            error=base.error,
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    hits: list[Hit] = []
    for hit in base.hits:
        started = _parse_started_at(hit.started_at)
        if started is not None and started < cutoff:
            continue
        hits.append(hit)

    hits.sort(
        key=lambda h: (
            _parse_started_at(h.started_at) or datetime.min.replace(tzinfo=timezone.utc),
            h.start_sec if h.start_sec is not None else 0.0,
            h.segment_id,
        )
    )
    return TimelineResult(
        ok=True,
        keyword=keyword,
        creator_id=creator_id,
        days=days,
        hits=hits,
    )
