"""Cross-process desktop state notifications via SQLite outbox."""

from __future__ import annotations

from media2text.core.storage.repos import DesktopEventRepo


def enqueue_creator_updated(conn, creator_id: str) -> str:
    return DesktopEventRepo(conn).enqueue_creator_updated(creator_id)
