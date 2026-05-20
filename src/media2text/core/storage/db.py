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


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
