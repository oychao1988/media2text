import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS creators (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  sec_uid TEXT NOT NULL,
  display_name TEXT,
  profile_url TEXT,
  watch_live INTEGER NOT NULL DEFAULT 0,
  monitor_enabled INTEGER NOT NULL DEFAULT 0,
  unique_id TEXT,
  avatar_url TEXT,
  signature TEXT,
  follower_count INTEGER,
  profile_synced_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(platform, sec_uid)
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


def _creators_table_sql(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='creators'"
    ).fetchone()
    return row[0] if row else None


def _migrate_creators_platform_sec_uid_unique(conn: sqlite3.Connection) -> None:
    """Migrate legacy UNIQUE(sec_uid) to UNIQUE(platform, sec_uid)."""
    sql = _creators_table_sql(conn)
    if not sql:
        return
    if "UNIQUE(platform, sec_uid)" in sql.replace(" ", ""):
        return
    upper = sql.upper()
    if "SEC_UID" not in upper or "UNIQUE" not in upper:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript(
        """
        CREATE TABLE creators__p6_unique (
          id TEXT PRIMARY KEY,
          platform TEXT NOT NULL,
          sec_uid TEXT NOT NULL,
          display_name TEXT,
          profile_url TEXT,
          watch_live INTEGER NOT NULL DEFAULT 0,
          monitor_enabled INTEGER NOT NULL DEFAULT 0,
          unique_id TEXT,
          avatar_url TEXT,
          signature TEXT,
          follower_count INTEGER,
          profile_synced_at TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(platform, sec_uid)
        );
        INSERT INTO creators__p6_unique (
          id, platform, sec_uid, display_name, profile_url, watch_live,
          monitor_enabled, unique_id, avatar_url, signature, follower_count,
          profile_synced_at, created_at
        )
        SELECT
          id, platform, sec_uid, display_name, profile_url, watch_live,
          monitor_enabled, unique_id, avatar_url, signature, follower_count,
          profile_synced_at, created_at
        FROM creators;
        DROP TABLE creators;
        ALTER TABLE creators__p6_unique RENAME TO creators;
        """
    )
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()


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
    _migrate_creators_platform_sec_uid_unique(conn)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_creators(conn)
    from media2text.core.archive.schema import migrate_archive

    migrate_archive(conn)
    return conn
