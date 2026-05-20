import os
import uuid
from datetime import datetime, timezone

from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.models import AwemeRow, CreatorRow, LiveSessionRow


class CreatorRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def add(
        self,
        *,
        sec_uid: str,
        profile_url: str,
        monitor_enabled: bool = False,
        display_name: str | None = None,
        unique_id: str | None = None,
        avatar_url: str | None = None,
        signature: str | None = None,
        follower_count: int | None = None,
        profile_synced_at: str | None = None,
    ) -> str:
        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO creators (
              id, platform, sec_uid, display_name, profile_url, watch_live,
              monitor_enabled, unique_id, avatar_url, signature, follower_count,
              profile_synced_at, created_at
            )
            VALUES (?, 'douyin', ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                sec_uid,
                display_name,
                profile_url,
                1 if monitor_enabled else 0,
                unique_id,
                avatar_url,
                signature,
                follower_count,
                profile_synced_at,
                now,
            ),
        )
        self._conn.commit()
        return cid

    def get(self, creator_id: str) -> CreatorRow | None:
        row = self._conn.execute("SELECT * FROM creators WHERE id = ?", (creator_id,)).fetchone()
        if not row:
            return None
        return CreatorRow(**dict(row))

    def get_by_sec_uid(self, sec_uid: str) -> CreatorRow | None:
        row = self._conn.execute("SELECT * FROM creators WHERE sec_uid = ?", (sec_uid,)).fetchone()
        if not row:
            return None
        return CreatorRow(**dict(row))

    def list_all(self) -> list[CreatorRow]:
        rows = self._conn.execute("SELECT * FROM creators ORDER BY created_at").fetchall()
        return [CreatorRow(**dict(r)) for r in rows]

    def list_monitored(self) -> list[CreatorRow]:
        rows = self._conn.execute(
            "SELECT * FROM creators WHERE monitor_enabled = 1 ORDER BY created_at"
        ).fetchall()
        return [CreatorRow(**dict(r)) for r in rows]

    def list_live_watched(self) -> list[CreatorRow]:
        """Deprecated: use list_monitored."""
        return self.list_monitored()

    def set_monitor_enabled(self, creator_id: str, *, enabled: bool) -> bool:
        cur = self._conn.execute(
            "UPDATE creators SET monitor_enabled = ? WHERE id = ?",
            (1 if enabled else 0, creator_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_profile(
        self,
        creator_id: str,
        *,
        display_name: str | None = None,
        unique_id: str | None = None,
        avatar_url: str | None = None,
        signature: str | None = None,
        follower_count: int | None = None,
        profile_synced_at: str | None = None,
    ) -> bool:
        cur = self._conn.execute(
            """
            UPDATE creators
            SET display_name = ?, unique_id = ?, avatar_url = ?, signature = ?,
                follower_count = ?, profile_synced_at = ?
            WHERE id = ?
            """,
            (
                display_name,
                unique_id,
                avatar_url,
                signature,
                follower_count,
                profile_synced_at,
                creator_id,
            ),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count_awemes(self, creator_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM awemes WHERE creator_id = ?",
            (creator_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def count_pending_download(self, creator_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS c FROM awemes
            WHERE creator_id = ? AND sync_status = 'listed'
            """,
            (creator_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def remove(self, creator_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM creators WHERE id = ?", (creator_id,))
        self._conn.commit()
        return cur.rowcount > 0


class AwemeRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def upsert_listed(self, *, creator_id: str, item: AwemeItem) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT aweme_id FROM awemes WHERE aweme_id = ?",
            (item.aweme_id,),
        ).fetchone()
        if existing:
            self._conn.execute(
                """
                UPDATE awemes
                SET title = ?, create_time = ?, updated_at = ?
                WHERE aweme_id = ?
                """,
                (item.title, item.create_time, now, item.aweme_id),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            """
            INSERT INTO awemes
              (aweme_id, creator_id, title, create_time, media_type, sync_status, updated_at)
            VALUES (?, ?, ?, ?, ?, 'listed', ?)
            """,
            (item.aweme_id, creator_id, item.title, item.create_time, item.media_type, now),
        )
        self._conn.commit()
        return True

    def list_pending_download(
        self,
        *,
        creator_id: str | None = None,
        monitor_only: bool = False,
    ) -> list[AwemeRow]:
        if creator_id:
            rows = self._conn.execute(
                "SELECT * FROM awemes WHERE creator_id = ? AND sync_status = 'listed'",
                (creator_id,),
            ).fetchall()
        elif monitor_only:
            rows = self._conn.execute(
                """
                SELECT a.* FROM awemes a
                INNER JOIN creators c ON c.id = a.creator_id
                WHERE a.sync_status = 'listed' AND c.monitor_enabled = 1
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM awemes WHERE sync_status = 'listed'"
            ).fetchall()
        return [AwemeRow(**dict(r)) for r in rows]

    def mark_downloaded(self, aweme_id: str, *, local_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE awemes SET sync_status = 'downloaded', local_path = ?, updated_at = ?
            WHERE aweme_id = ?
            """,
            (local_path, now, aweme_id),
        )
        self._conn.commit()

    def mark_failed(self, aweme_id: str, *, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE awemes SET sync_status = 'failed', transcribe_status = ?, updated_at = ?
            WHERE aweme_id = ?
            """,
            (error[:500], now, aweme_id),
        )
        self._conn.commit()

    def list_for_creator(self, creator_id: str) -> list[AwemeRow]:
        rows = self._conn.execute(
            "SELECT * FROM awemes WHERE creator_id = ? ORDER BY create_time DESC",
            (creator_id,),
        ).fetchall()
        return [AwemeRow(**dict(r)) for r in rows]

    def mark_transcribed(self, aweme_id: str, *, transcript_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE awemes
            SET transcribe_status = 'done', transcript_path = ?, updated_at = ?
            WHERE aweme_id = ?
            """,
            (transcript_path, now, aweme_id),
        )
        self._conn.commit()

    def list_downloaded_without_transcript(
        self,
        *,
        creator_id: str | None = None,
        monitor_only: bool = False,
    ) -> list[AwemeRow]:
        if creator_id:
            rows = self._conn.execute(
                """
                SELECT * FROM awemes
                WHERE creator_id = ? AND sync_status = 'downloaded'
                  AND (transcribe_status IS NULL OR transcribe_status != 'done')
                """,
                (creator_id,),
            ).fetchall()
        elif monitor_only:
            rows = self._conn.execute(
                """
                SELECT a.* FROM awemes a
                INNER JOIN creators c ON c.id = a.creator_id
                WHERE a.sync_status = 'downloaded'
                  AND (a.transcribe_status IS NULL OR a.transcribe_status != 'done')
                  AND c.monitor_enabled = 1
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM awemes
                WHERE sync_status = 'downloaded'
                  AND (transcribe_status IS NULL OR transcribe_status != 'done')
                """
            ).fetchall()
        return [AwemeRow(**dict(r)) for r in rows]


class LiveSessionRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def create(
        self,
        *,
        creator_id: str,
        room_id: str | None,
        temp_path: str,
        ffmpeg_pid: int,
    ) -> str:
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO live_sessions
              (id, creator_id, room_id, ffmpeg_pid, started_at, temp_path, status)
            VALUES (?, ?, ?, ?, ?, ?, 'recording')
            """,
            (sid, creator_id, room_id, ffmpeg_pid, now, temp_path),
        )
        self._conn.commit()
        return sid

    def get_active_for_creator(self, creator_id: str) -> LiveSessionRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM live_sessions
            WHERE creator_id = ? AND status IN ('recording', 'remuxing')
            ORDER BY started_at DESC LIMIT 1
            """,
            (creator_id,),
        ).fetchone()
        if not row:
            return None
        session = LiveSessionRow(**dict(row))
        if session.status != "recording" or session.ffmpeg_pid is None:
            return session
        try:
            os.kill(session.ffmpeg_pid, 0)
        except OSError:
            self.update_status(
                session.id,
                status="failed",
                error="stale_recording",
                ended=True,
            )
            return None
        return session

    def mark_stale_recordings_failed(self) -> int:
        rows = self.list_active()
        count = 0
        for row in rows:
            if row.status != "recording" or row.ffmpeg_pid is None:
                continue
            try:
                os.kill(row.ffmpeg_pid, 0)
            except OSError:
                self.update_status(
                    row.id,
                    status="failed",
                    error="stale_recording",
                    ended=True,
                )
                count += 1
        return count

    def list_active(self) -> list[LiveSessionRow]:
        rows = self._conn.execute(
            "SELECT * FROM live_sessions WHERE status IN ('recording', 'remuxing')"
        ).fetchall()
        return [LiveSessionRow(**dict(r)) for r in rows]

    def get(self, session_id: str) -> LiveSessionRow | None:
        row = self._conn.execute(
            "SELECT * FROM live_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return LiveSessionRow(**dict(row)) if row else None

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        local_path: str | None = None,
        error: str | None = None,
        ended: bool = False,
    ) -> None:
        ended_at = datetime.now(timezone.utc).isoformat() if ended else None
        self._conn.execute(
            """
            UPDATE live_sessions
            SET status = ?, local_path = COALESCE(?, local_path), error = ?, ended_at = COALESCE(?, ended_at)
            WHERE id = ?
            """,
            (status, local_path, error, ended_at, session_id),
        )
        self._conn.commit()

    def clear_pid(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE live_sessions SET ffmpeg_pid = NULL WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()
