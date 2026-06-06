import sqlite3
import threading
from pathlib import Path

_connect_lock = threading.Lock()

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
  transcribe_status TEXT,
  cloud_upload_status TEXT,
  cloud_file_id TEXT,
  cloud_relative_path TEXT,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE TABLE IF NOT EXISTS cloud_uploads (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  creator_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_kind TEXT NOT NULL,
  local_path TEXT,
  cloud_file_id TEXT,
  cloud_relative_path TEXT,
  size INTEGER,
  pre_hash TEXT,
  upload_status TEXT NOT NULL,
  uploaded_at TEXT,
  error TEXT,
  FOREIGN KEY (session_id) REFERENCES live_sessions(id),
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE TABLE IF NOT EXISTS dynamics (
  dynamic_id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  dynamic_type TEXT,
  text TEXT,
  refs_json TEXT,
  image_count INTEGER NOT NULL DEFAULT 0,
  sync_status TEXT NOT NULL,
  local_dir TEXT,
  published_at TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE TABLE IF NOT EXISTS post_process_jobs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  creator_id TEXT NOT NULL,
  mp4_path TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES live_sessions(id),
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);
CREATE INDEX IF NOT EXISTS idx_post_process_jobs_status ON post_process_jobs(status);

CREATE TABLE IF NOT EXISTS live_pipeline_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  job_id TEXT,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  duration_ms INTEGER,
  FOREIGN KEY (session_id) REFERENCES live_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_lpe_session ON live_pipeline_events(session_id, started_at);
CREATE INDEX IF NOT EXISTS idx_lpe_stage ON live_pipeline_events(stage, started_at);
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


def _has_platform_sec_uid_unique(sql: str) -> bool:
    normalized = sql.replace(" ", "")
    return "UNIQUE(platform,sec_uid)" in normalized


def _migrate_creators_platform_sec_uid_unique(conn: sqlite3.Connection) -> None:
    """Migrate legacy UNIQUE(sec_uid) to UNIQUE(platform, sec_uid)."""
    sql = _creators_table_sql(conn)
    if not sql:
        return
    if _has_platform_sec_uid_unique(sql):
        return
    upper = sql.upper()
    if "SEC_UID" not in upper or "UNIQUE" not in upper:
        return

    existing = {row[1] for row in conn.execute("PRAGMA table_info(creators)").fetchall()}
    has_override = "auto_record_override" in existing
    override_ddl = (
        "auto_record_override TEXT NOT NULL DEFAULT 'inherit',\n          "
        if has_override
        else ""
    )
    tail_cols = ", auto_record_override" if has_override else ""

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript(
        f"""
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
          {override_ddl}UNIQUE(platform, sec_uid)
        );
        INSERT INTO creators__p6_unique (
          id, platform, sec_uid, display_name, profile_url, watch_live,
          monitor_enabled, unique_id, avatar_url, signature, follower_count,
          profile_synced_at, created_at{tail_cols}
        )
        SELECT
          id, platform, sec_uid, display_name, profile_url, watch_live,
          monitor_enabled, unique_id, avatar_url, signature, follower_count,
          profile_synced_at, created_at{tail_cols}
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


_LIVE_SESSION_COLUMNS = (
    ("transcribe_status", "TEXT"),
    ("cloud_upload_status", "TEXT"),
    ("cloud_file_id", "TEXT"),
    ("cloud_relative_path", "TEXT"),
)


def _migrate_live_sessions(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    for name, col_type in _LIVE_SESSION_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE live_sessions ADD COLUMN {name} {col_type}")
    conn.commit()


_LIVE_SESSION_V2_COLUMNS = (
    ("offline_streak", "INTEGER NOT NULL DEFAULT 0"),
    ("reconnect_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("segment_paths_json", "TEXT"),
)


def _migrate_live_sessions_v2(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    for name, col_type in _LIVE_SESSION_V2_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE live_sessions ADD COLUMN {name} {col_type}")
    conn.commit()


_LIVE_SESSION_V3_COLUMNS = (
    ("first_seen_live_at", "TEXT"),
    ("recording_started_at", "TEXT"),
    ("offline_since_at", "TEXT"),
    ("platform_live_started_at", "TEXT"),
)


def _migrate_live_sessions_v3(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    for name, col_type in _LIVE_SESSION_V3_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE live_sessions ADD COLUMN {name} {col_type}")
    conn.commit()


_LIVE_SESSION_V4_COLUMNS = (("pipeline_mode", "TEXT"),)


def _migrate_live_sessions_v4(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    for name, col_type in _LIVE_SESSION_V4_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE live_sessions ADD COLUMN {name} {col_type}")
    conn.execute(
        """
        UPDATE live_sessions
        SET pipeline_mode = 'legacy'
        WHERE pipeline_mode IS NULL
        """
    )
    conn.commit()


def _migrate_desktop_v1(conn: sqlite3.Connection) -> None:
    creator_cols = {row[1] for row in conn.execute("PRAGMA table_info(creators)").fetchall()}
    if "auto_record_override" not in creator_cols:
        conn.execute(
            "ALTER TABLE creators ADD COLUMN auto_record_override TEXT NOT NULL DEFAULT 'inherit'"
        )

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS creator_live_snapshots (
          creator_id TEXT PRIMARY KEY,
          is_live INTEGER NOT NULL DEFAULT 0,
          room_id TEXT,
          title TEXT,
          checked_at TEXT NOT NULL,
          FOREIGN KEY (creator_id) REFERENCES creators(id)
        );

        CREATE TABLE IF NOT EXISTS desktop_chat_threads (
          id TEXT PRIMARY KEY,
          creator_id TEXT NOT NULL,
          session_id TEXT,
          title TEXT,
          provider_name TEXT,
          model TEXT DEFAULT 'auto',
          context_mode TEXT DEFAULT 'both',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (creator_id) REFERENCES creators(id),
          FOREIGN KEY (session_id) REFERENCES live_sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_dct_session ON desktop_chat_threads(session_id);

        CREATE TABLE IF NOT EXISTS desktop_chat_messages (
          id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          thinking_text TEXT,
          duration_ms INTEGER,
          created_at TEXT NOT NULL,
          FOREIGN KEY (thread_id) REFERENCES desktop_chat_threads(id)
        );
        CREATE INDEX IF NOT EXISTS idx_dcm_thread ON desktop_chat_messages(thread_id, created_at);
        """
    )
    conn.commit()


def _migrate_desktop_v2(conn: sqlite3.Connection) -> None:
    snap_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(creator_live_snapshots)").fetchall()
    }
    if "probe_error" not in snap_cols:
        conn.execute(
            "ALTER TABLE creator_live_snapshots ADD COLUMN probe_error TEXT"
        )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS desktop_events (
          id TEXT PRIMARY KEY,
          event_type TEXT NOT NULL,
          creator_id TEXT,
          payload_json TEXT,
          created_at TEXT NOT NULL,
          delivered_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_desktop_events_pending
          ON desktop_events(delivered_at, created_at)
          WHERE delivered_at IS NULL;
        """
    )
    conn.commit()


def _migrate_monitor_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monitor_tasks (
          id TEXT PRIMARY KEY,
          creator_id TEXT NOT NULL,
          task_type TEXT NOT NULL,
          payload_json TEXT,
          priority INTEGER NOT NULL DEFAULT 10,
          status TEXT NOT NULL DEFAULT 'pending',
          dedupe_key TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_monitor_tasks_status_prio
          ON monitor_tasks(status, priority, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_monitor_tasks_dedupe_active
          ON monitor_tasks(dedupe_key)
          WHERE dedupe_key IS NOT NULL AND status IN ('pending', 'running');
        """
    )
    conn.commit()
    _migrate_monitor_v2(conn)


def _migrate_monitor_v2(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(monitor_tasks)").fetchall()}
    if "attempt_count" not in cols:
        conn.execute(
            "ALTER TABLE monitor_tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


_AWEME_COLUMNS = (("download_url", "TEXT"), ("media_urls", "TEXT"))


def _migrate_hermes_v1(conn: sqlite3.Connection) -> None:
    """Migrate desktop_chat_* to Hermes sessions/messages (M0)."""
    import json

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "_legacy_desktop_chat_threads" in tables:
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          display_thread_id TEXT NOT NULL,
          parent_session_id TEXT,
          title TEXT,
          creator_id TEXT,
          active_binding_json TEXT,
          token_estimate INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (parent_session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_display_thread
          ON sessions(display_thread_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_parent
          ON sessions(parent_session_id);

        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          seq INTEGER NOT NULL,
          role TEXT NOT NULL,
          content TEXT,
          tool_call_id TEXT,
          tool_name TEXT,
          tool_calls_json TEXT,
          thinking_text TEXT,
          input_tokens INTEGER,
          output_tokens INTEGER,
          duration_ms INTEGER,
          message_kind TEXT NOT NULL DEFAULT 'normal',
          created_at TEXT NOT NULL,
          FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_session_seq
          ON messages(session_id, seq);
        """
    )

    if "desktop_chat_threads" not in tables:
        conn.commit()
        return

    session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if session_count == 0:
        thread_rows = conn.execute("SELECT * FROM desktop_chat_threads").fetchall()
        for row in thread_rows:
            binding = {
                "provider_name": row["provider_name"],
                "model": row["model"] or "auto",
                "context_mode": row["context_mode"] or "both",
                "session_id": row["session_id"],
            }
            conn.execute(
                """
                INSERT INTO sessions (
                  id, display_thread_id, parent_session_id, title, creator_id,
                  active_binding_json, token_estimate, created_at, updated_at
                )
                VALUES (?, ?, NULL, ?, ?, ?, 0, ?, ?)
                """,
                (
                    row["id"],
                    row["id"],
                    row["title"],
                    row["creator_id"],
                    json.dumps(binding),
                    row["created_at"],
                    row["updated_at"],
                ),
            )

        for thread_row in thread_rows:
            tid = thread_row["id"]
            seq = 0
            msg_rows = conn.execute(
                """
                SELECT * FROM desktop_chat_messages
                WHERE thread_id = ?
                ORDER BY created_at
                """,
                (tid,),
            ).fetchall()
            for msg in msg_rows:
                seq += 1
                conn.execute(
                    """
                    INSERT INTO messages (
                      id, session_id, seq, role, content, tool_call_id, tool_name,
                      tool_calls_json, thinking_text, input_tokens, output_tokens,
                      duration_ms, message_kind, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL, ?, 'normal', ?)
                    """,
                    (
                        msg["id"],
                        tid,
                        seq,
                        msg["role"],
                        msg["content"],
                        msg["thinking_text"],
                        msg["duration_ms"],
                        msg["created_at"],
                    ),
                )

    conn.execute(
        "ALTER TABLE desktop_chat_threads RENAME TO _legacy_desktop_chat_threads"
    )
    conn.execute(
        "ALTER TABLE desktop_chat_messages RENAME TO _legacy_desktop_chat_messages"
    )
    conn.commit()


def _migrate_awemes_v1(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(awemes)").fetchall()}
    for name, col_type in _AWEME_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE awemes ADD COLUMN {name} {col_type}")
    conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with _connect_lock:
        conn.executescript(SCHEMA)
        _migrate_creators(conn)
        _migrate_live_sessions(conn)
        _migrate_live_sessions_v2(conn)
        _migrate_live_sessions_v3(conn)
        _migrate_live_sessions_v4(conn)
        _migrate_desktop_v1(conn)
        _migrate_desktop_v2(conn)
        _migrate_monitor_v1(conn)
        _migrate_awemes_v1(conn)
        _migrate_hermes_v1(conn)
        from media2text.core.archive.schema import migrate_archive

        migrate_archive(conn)
    return conn
