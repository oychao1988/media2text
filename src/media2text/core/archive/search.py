from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from media2text.core.archive.models import Hit
from media2text.core.archive.schema import migrate_archive


class InvalidSearchSyntaxError(ValueError):
    pass


@dataclass
class SearchResult:
    ok: bool
    query: str
    hits: list[Hit] = field(default_factory=list)
    indexed: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        payload: dict = {
            "ok": self.ok,
            "query": self.query,
            "indexed": self.indexed,
            "hits": [h.to_dict() for h in self.hits],
        }
        if self.error:
            payload["error"] = self.error
        return payload


def _segment_count(conn: sqlite3.Connection) -> int:
    migrate_archive(conn)
    row = conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()
    return int(row[0]) if row else 0


def _fts_query(raw: str) -> str:
    q = raw.strip()
    if not q:
        raise InvalidSearchSyntaxError("empty query")
    if q.count('"') % 2 == 1:
        raise InvalidSearchSyntaxError("invalid search syntax")
    return q.replace('"', '""')


def search_archive(
    conn: sqlite3.Connection,
    query: str,
    *,
    creator_id: str | None = None,
    limit: int = 20,
) -> SearchResult:
    migrate_archive(conn)
    if _segment_count(conn) == 0:
        return SearchResult(
            ok=False,
            query=query,
            indexed=False,
            error="no indexed transcripts; run: media2text archive index",
        )

    try:
        fts_q = _fts_query(query)
    except InvalidSearchSyntaxError:
        return SearchResult(ok=False, query=query, error="invalid search syntax")

    sql = """
        SELECT
          s.id,
          s.start_sec,
          s.session_id,
          s.session_type,
          s.creator_id,
          s.sec_uid,
          s.media_path,
          s.transcript_path,
          s.started_at,
          snippet(transcript_fts, 0, '', '', '…', 48) AS excerpt
        FROM transcript_segments s
        JOIN transcript_fts ON transcript_fts.rowid = s.id
        WHERE transcript_fts MATCH ?
    """
    params: list[object] = [fts_q]
    if creator_id:
        sql += " AND s.creator_id = ?"
        params.append(creator_id)
    sql += " ORDER BY s.started_at DESC, s.id LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "syntax error" in msg or "malformed" in msg or "fts5" in msg:
            return SearchResult(
                ok=False,
                query=query,
                error="invalid search syntax",
            )
        raise

    hits: list[Hit] = []
    for row in rows:
        start = row["start_sec"]
        excerpt = row["excerpt"] or ""
        hits.append(
            Hit(
                segment_id=int(row["id"]),
                offset_sec=float(start) if start is not None else None,
                start_sec=float(start) if start is not None else None,
                session_id=row["session_id"],
                session_type=row["session_type"],
                creator_id=row["creator_id"],
                sec_uid=row["sec_uid"],
                excerpt=excerpt,
                transcript_path=row["transcript_path"],
                open_path=row["media_path"],
                started_at=row["started_at"],
            )
        )

    return SearchResult(ok=True, query=query, hits=hits)
