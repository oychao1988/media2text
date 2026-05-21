"""SQLite schema and FTS5 triggers for transcript archive indexing."""

from __future__ import annotations

import sqlite3

_SEGMENTS_DDL = """
CREATE TABLE IF NOT EXISTS transcript_segments (
  id INTEGER PRIMARY KEY,
  session_type TEXT NOT NULL,
  session_id TEXT NOT NULL,
  creator_id TEXT NOT NULL,
  sec_uid TEXT NOT NULL,
  media_path TEXT NOT NULL,
  transcript_path TEXT NOT NULL,
  segment_index INTEGER NOT NULL,
  start_sec REAL,
  end_sec REAL,
  text TEXT NOT NULL,
  started_at TEXT,
  indexed_at TEXT NOT NULL,
  UNIQUE(transcript_path, segment_index)
);
"""

_FTS_DDL = """
CREATE VIRTUAL TABLE transcript_fts USING fts5(
  text,
  content='transcript_segments',
  content_rowid='id',
  tokenize='trigram'
);
"""

_FTS_TRIGGERS_IF_NOT_EXISTS = """
CREATE TRIGGER IF NOT EXISTS transcript_segments_ai AFTER INSERT ON transcript_segments BEGIN
  INSERT INTO transcript_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS transcript_segments_ad AFTER DELETE ON transcript_segments BEGIN
  INSERT INTO transcript_fts(transcript_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS transcript_segments_au AFTER UPDATE ON transcript_segments BEGIN
  INSERT INTO transcript_fts(transcript_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO transcript_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def _fts_needs_upgrade(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='transcript_fts'"
    ).fetchone()
    if row is None:
        return True
    sql = row["sql"] or ""
    return "trigram" not in sql


def _drop_fts(conn: sqlite3.Connection) -> None:
    for name in (
        "transcript_segments_au",
        "transcript_segments_ad",
        "transcript_segments_ai",
    ):
        conn.execute(f"DROP TRIGGER IF EXISTS {name}")
    conn.execute("DROP TABLE IF EXISTS transcript_fts")


def migrate_archive(conn: sqlite3.Connection) -> None:
    conn.executescript(_SEGMENTS_DDL)
    upgraded = _fts_needs_upgrade(conn)
    if upgraded:
        _drop_fts(conn)
        conn.executescript(_FTS_DDL)
    conn.executescript(_FTS_TRIGGERS_IF_NOT_EXISTS)
    conn.commit()
    if upgraded:
        row = conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()
        if row and int(row[0]) > 0:
            conn.execute("INSERT INTO transcript_fts(transcript_fts) VALUES('rebuild')")
            conn.commit()


def rebuild_fts(conn: sqlite3.Connection) -> None:
    migrate_archive(conn)
    conn.execute("INSERT INTO transcript_fts(transcript_fts) VALUES('rebuild')")
    conn.commit()


def clear_segments(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM transcript_segments")
    conn.commit()
    rebuild_fts(conn)
