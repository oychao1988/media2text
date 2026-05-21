import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS creators (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  sec_uid TEXT NOT NULL UNIQUE,
  display_name TEXT,
  profile_url TEXT,
  watch_live INTEGER NOT NULL DEFAULT 0,
  monitor_enabled INTEGER NOT NULL DEFAULT 0,
  unique_id TEXT,
  avatar_url TEXT,
  signature TEXT,
  follower_count INTEGER,
  profile_synced_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS awemes (
  aweme_id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  title TEXT,
  create_time INTEGER,
  media_type TEXT,
  sync_status TEXT NOT NULL,
  local_path TEXT,
  transcribe_status TEXT,
  transcript_path TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE TABLE IF NOT EXISTS live_sessions (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  room_id TEXT,
  ffmpeg_pid INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  local_path TEXT,
  temp_path TEXT,
  status TEXT NOT NULL,
  error TEXT,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);
"""

_CREATOR_COLUMNS = (
    ("monitor_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("unique_id", "TEXT"),
    ("avatar_url", "TEXT"),
    ("signature", "TEXT"),
    ("follower_count", "INTEGER"),
    ("profile_synced_at", "TEXT"),
)


def _migrate_creators(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(creators)").fetchall()}
    added_monitor_enabled = False
    for name, col_type in _CREATOR_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE creators ADD COLUMN {name} {col_type}")
            if name == "monitor_enabled":
                added_monitor_enabled = True
    # One-time backfill when the column is first added — not on every connect.
    if added_monitor_enabled:
        conn.execute(
            """
            UPDATE creators
            SET monitor_enabled = 1
            WHERE watch_live = 1 AND (monitor_enabled IS NULL OR monitor_enabled = 0)
            """
        )
    conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_creators(conn)
    from media2text.core.archive.schema import migrate_archive

    migrate_archive(conn)
    return conn
