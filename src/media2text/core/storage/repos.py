import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from media2text.core.platform.douyin.models import AwemeItem
import json

from media2text.core.live.probe_guard import ProbeExecutionGuard
from media2text.core.storage.models import (
    AwemeRow,
    CloudUploadRow,
    CreatorAgentJobRow,
    CreatorLiveSnapshotRow,
    CreatorRow,
    DesktopChatMessageRow,
    DesktopChatThreadRow,
    DesktopEventRow,
    DynamicRow,
    LiveSessionRow,
    MonitorTaskRow,
    PipelineEventRow,
    PostProcessJobRow,
)


class CreatorRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def add(
        self,
        *,
        sec_uid: str,
        profile_url: str,
        platform: str = "douyin",
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
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                platform,
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

    def get_by_sec_uid(self, sec_uid: str, *, platform: str | None = None) -> CreatorRow | None:
        if platform:
            row = self._conn.execute(
                "SELECT * FROM creators WHERE sec_uid = ? AND platform = ?",
                (sec_uid, platform),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM creators WHERE sec_uid = ?", (sec_uid,)
            ).fetchone()
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

    def list_content_sync_enabled(self) -> list[CreatorRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM creators
            WHERE content_sync_enabled = 1
            ORDER BY created_at
            """
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

    def set_content_sync_enabled(self, creator_id: str, *, enabled: bool) -> bool:
        if enabled:
            now = datetime.now(timezone.utc).isoformat()
            row = self.get(creator_id)
            if row is None:
                return False
            if row.platform == "bilibili":
                cur = self._conn.execute(
                    """
                    UPDATE creators
                    SET content_sync_enabled = 1,
                        archive_due_at = COALESCE(archive_due_at, ?),
                        dynamic_due_at = COALESCE(dynamic_due_at, ?)
                    WHERE id = ?
                    """,
                    (now, now, creator_id),
                )
            else:
                cur = self._conn.execute(
                    """
                    UPDATE creators
                    SET content_sync_enabled = 1,
                        vod_due_at = COALESCE(vod_due_at, ?)
                    WHERE id = ?
                    """,
                    (now, creator_id),
                )
        else:
            cur = self._conn.execute(
                """
                UPDATE creators
                SET content_sync_enabled = 0,
                    vod_due_at = NULL,
                    archive_due_at = NULL,
                    dynamic_due_at = NULL,
                    sync_needs_download = 0
                WHERE id = ?
                """,
                (creator_id,),
            )
        self._conn.commit()
        return cur.rowcount > 0

    def set_auto_record_override(self, creator_id: str, override: str) -> bool:
        cur = self._conn.execute(
            "UPDATE creators SET auto_record_override = ? WHERE id = ?",
            (override, creator_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_vod_due(self, creator_id: str, iso: str) -> None:
        self._conn.execute(
            "UPDATE creators SET vod_due_at = ? WHERE id = ?",
            (iso, creator_id),
        )
        self._conn.commit()

    def set_archive_due(self, creator_id: str, iso: str) -> None:
        self._conn.execute(
            "UPDATE creators SET archive_due_at = ? WHERE id = ?",
            (iso, creator_id),
        )
        self._conn.commit()

    def set_dynamic_due(self, creator_id: str, iso: str) -> None:
        self._conn.execute(
            "UPDATE creators SET dynamic_due_at = ? WHERE id = ?",
            (iso, creator_id),
        )
        self._conn.commit()

    def clear_vod_due(self, creator_id: str) -> None:
        self._conn.execute(
            "UPDATE creators SET vod_due_at = NULL WHERE id = ?",
            (creator_id,),
        )
        self._conn.commit()

    def clear_archive_due(self, creator_id: str) -> None:
        self._conn.execute(
            "UPDATE creators SET archive_due_at = NULL WHERE id = ?",
            (creator_id,),
        )
        self._conn.commit()

    def clear_dynamic_due(self, creator_id: str) -> None:
        self._conn.execute(
            "UPDATE creators SET dynamic_due_at = NULL WHERE id = ?",
            (creator_id,),
        )
        self._conn.commit()

    def schedule_vod_poll(self, creator_id: str, interval_sec: float) -> None:
        next_at = datetime.now(timezone.utc) + timedelta(seconds=interval_sec)
        self.set_vod_due(creator_id, next_at.isoformat())

    def schedule_archive_poll(self, creator_id: str, interval_sec: float) -> None:
        next_at = datetime.now(timezone.utc) + timedelta(seconds=interval_sec)
        self.set_archive_due(creator_id, next_at.isoformat())

    def schedule_dynamic_poll(self, creator_id: str, interval_sec: float) -> None:
        next_at = datetime.now(timezone.utc) + timedelta(seconds=interval_sec)
        self.set_dynamic_due(creator_id, next_at.isoformat())

    def mark_sync_needs_download(self, creator_id: str) -> None:
        self._conn.execute(
            "UPDATE creators SET sync_needs_download = 1 WHERE id = ?",
            (creator_id,),
        )
        self._conn.commit()

    def clear_sync_needs_download(self, creator_id: str) -> None:
        self._conn.execute(
            "UPDATE creators SET sync_needs_download = 0 WHERE id = ?",
            (creator_id,),
        )
        self._conn.commit()

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
        media_urls_json = json.dumps(item.media_urls) if item.media_urls else None
        has_urls = bool(item.download_url or item.media_urls)
        existing = self._conn.execute(
            "SELECT aweme_id, sync_status FROM awemes WHERE aweme_id = ?",
            (item.aweme_id,),
        ).fetchone()
        if existing:
            reset_listed = existing["sync_status"] == "failed" and has_urls
            self._conn.execute(
                """
                UPDATE awemes
                SET title = ?, create_time = ?, media_type = ?,
                    download_url = COALESCE(?, download_url),
                    media_urls = COALESCE(?, media_urls),
                    sync_status = CASE WHEN ? THEN 'listed' ELSE sync_status END,
                    transcribe_status = CASE WHEN ? THEN NULL ELSE transcribe_status END,
                    updated_at = ?
                WHERE aweme_id = ?
                """,
                (
                    item.title,
                    item.create_time,
                    item.media_type,
                    item.download_url,
                    media_urls_json,
                    1 if reset_listed else 0,
                    1 if reset_listed else 0,
                    now,
                    item.aweme_id,
                ),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            """
            INSERT INTO awemes
              (aweme_id, creator_id, title, create_time, media_type, sync_status,
               download_url, media_urls, updated_at)
            VALUES (?, ?, ?, ?, ?, 'listed', ?, ?, ?)
            """,
            (
                item.aweme_id,
                creator_id,
                item.title,
                item.create_time,
                item.media_type,
                item.download_url,
                media_urls_json,
                now,
            ),
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
                WHERE a.sync_status = 'listed' AND c.content_sync_enabled = 1
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

    def reset_failed_to_listed(self, aweme_id: str) -> bool:
        """Move a failed aweme back to the download queue."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            UPDATE awemes
            SET sync_status = 'listed', transcribe_status = NULL, updated_at = ?
            WHERE aweme_id = ? AND sync_status = 'failed'
            """,
            (now, aweme_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def get(self, aweme_id: str) -> AwemeRow | None:
        row = self._conn.execute(
            "SELECT * FROM awemes WHERE aweme_id = ?",
            (aweme_id,),
        ).fetchone()
        return AwemeRow(**dict(row)) if row else None

    def list_for_creator(self, creator_id: str) -> list[AwemeRow]:
        rows = self._conn.execute(
            "SELECT * FROM awemes WHERE creator_id = ? ORDER BY create_time DESC",
            (creator_id,),
        ).fetchall()
        return [AwemeRow(**dict(r)) for r in rows]

    def clear_local_path(self, aweme_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE awemes SET local_path = NULL, updated_at = ?
            WHERE aweme_id = ?
            """,
            (now, aweme_id),
        )
        self._conn.commit()

    def delete(self, aweme_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM awemes WHERE aweme_id = ?",
            (aweme_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

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
                  AND c.content_sync_enabled = 1
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


class DynamicRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get(self, dynamic_id: str) -> DynamicRow | None:
        row = self._conn.execute(
            "SELECT * FROM dynamics WHERE dynamic_id = ?",
            (dynamic_id,),
        ).fetchone()
        return DynamicRow(**dict(row)) if row else None

    def is_synced(self, dynamic_id: str) -> bool:
        row = self.get(dynamic_id)
        return row is not None and row.sync_status == "synced"

    def upsert_listed(
        self,
        *,
        creator_id: str,
        dynamic_id: str,
        dynamic_type: str | None,
        text: str | None,
        refs_json: str | None,
        local_dir: str | None,
        published_at: str | None,
    ) -> bool:
        """Insert listed row; returns True if newly inserted."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(dynamic_id)
        if existing:
            self._conn.execute(
                """
                UPDATE dynamics
                SET dynamic_type = ?, text = ?, refs_json = ?, local_dir = ?,
                    published_at = ?, updated_at = ?
                WHERE dynamic_id = ?
                """,
                (
                    dynamic_type,
                    text,
                    refs_json,
                    local_dir,
                    published_at,
                    now,
                    dynamic_id,
                ),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            """
            INSERT INTO dynamics (
              dynamic_id, creator_id, dynamic_type, text, refs_json,
              image_count, sync_status, local_dir, published_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, 'listed', ?, ?, ?)
            """,
            (
                dynamic_id,
                creator_id,
                dynamic_type,
                text,
                refs_json,
                local_dir,
                published_at,
                now,
            ),
        )
        self._conn.commit()
        return True

    def mark_synced(
        self,
        dynamic_id: str,
        *,
        image_count: int,
        text: str | None = None,
        refs_json: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE dynamics
            SET sync_status = 'synced', image_count = ?, text = COALESCE(?, text),
                refs_json = COALESCE(?, refs_json), updated_at = ?
            WHERE dynamic_id = ?
            """,
            (image_count, text, refs_json, now, dynamic_id),
        )
        self._conn.commit()

    def mark_failed(self, dynamic_id: str, *, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE dynamics SET sync_status = 'failed', updated_at = ?
            WHERE dynamic_id = ?
            """,
            (now, dynamic_id),
        )
        self._conn.commit()

    def refs_for(self, dynamic_id: str) -> dict:
        row = self.get(dynamic_id)
        if not row or not row.refs_json:
            return {}
        try:
            data = json.loads(row.refs_json)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def list_for_creator(self, creator_id: str) -> list[DynamicRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM dynamics
            WHERE creator_id = ?
            ORDER BY published_at DESC, updated_at DESC
            """,
            (creator_id,),
        ).fetchall()
        return [DynamicRow(**dict(r)) for r in rows]


class LiveSessionRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def create(
        self,
        *,
        creator_id: str,
        room_id: str | None,
        temp_path: str,
        ffmpeg_pid: int | None = None,
        platform_live_started_at: str | None = None,
        pipeline_mode: str | None = None,
        session_dir: str | None = None,
    ) -> str:
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO live_sessions
              (id, creator_id, room_id, ffmpeg_pid, started_at, temp_path, status,
               first_seen_live_at, recording_started_at, platform_live_started_at,
               pipeline_mode, session_dir)
            VALUES (?, ?, ?, ?, ?, ?, 'recording', ?, ?, ?, ?, ?)
            """,
            (
                sid,
                creator_id,
                room_id,
                ffmpeg_pid,
                now,
                temp_path,
                now,
                now,
                platform_live_started_at,
                pipeline_mode,
                session_dir,
            ),
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
        if (session.reconnect_attempts or 0) > 0:
            return session
        if session.ffmpeg_pid <= 0:
            return session
        try:
            os.kill(session.ffmpeg_pid, 0)
        except OSError:
            # Leave session for poll_active_recordings / mark_stale; do not
            # preempt finalize with stale_recording (see issue #78).
            return session
        return session

    def mark_stale_recordings_failed(self) -> int:
        rows = self.list_active()
        count = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            if row.status != "recording":
                continue
            if row.ffmpeg_pid is None:
                try:
                    started = datetime.fromisoformat(
                        row.started_at.replace("Z", "+00:00")
                    )
                except ValueError:
                    started = now
                age_sec = (now - started).total_seconds()
                temp_missing = not row.temp_path or not Path(row.temp_path).is_file()
                # Stream resolve + streaming STT startup can exceed 10s; avoid
                # marking failed while prepare_live_recording is still in flight.
                if age_sec > 60 and temp_missing:
                    self.update_status(
                        row.id,
                        status="failed",
                        error="recording_never_started",
                        ended=True,
                    )
                    count += 1
                continue
            if (row.reconnect_attempts or 0) > 0:
                continue
            if row.obs_ffmpeg_alive == 0:
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

    def get_latest_for_creator(self, creator_id: str) -> LiveSessionRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM live_sessions
            WHERE creator_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (creator_id,),
        ).fetchone()
        return LiveSessionRow(**dict(row)) if row else None

    def list_completed_for_creator(self, creator_id: str) -> list[LiveSessionRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM live_sessions
            WHERE creator_id = ? AND status = 'completed' AND local_path IS NOT NULL
            ORDER BY started_at ASC
            """,
            (creator_id,),
        ).fetchall()
        return [LiveSessionRow(**dict(r)) for r in rows]

    def clear_local_path(self, session_id: str) -> None:
        self._conn.execute(
            """
            UPDATE live_sessions
            SET local_path = NULL, temp_path = NULL
            WHERE id = ?
            """,
            (session_id,),
        )
        self._conn.commit()

    def delete(self, session_id: str) -> bool:
        self._conn.execute(
            "DELETE FROM cloud_uploads WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute(
            "DELETE FROM live_session_parts WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute(
            "DELETE FROM segment_process_jobs WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute(
            "DELETE FROM post_process_jobs WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute(
            "DELETE FROM pipeline_events WHERE session_id = ?",
            (session_id,),
        )
        cur = self._conn.execute(
            "DELETE FROM live_sessions WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_status(
        self,
        session_id: str,
        *,
        status: str | None = None,
        local_path: str | None = None,
        error: str | None = None,
        ended: bool = False,
        transcribe_status: str | None = None,
        cloud_upload_status: str | None = None,
        cloud_file_id: str | None = None,
        cloud_relative_path: str | None = None,
    ) -> None:
        ended_at = datetime.now(timezone.utc).isoformat() if ended else None
        self._conn.execute(
            """
            UPDATE live_sessions
            SET status = COALESCE(?, status),
                local_path = COALESCE(?, local_path),
                error = COALESCE(?, error),
                ended_at = COALESCE(?, ended_at),
                transcribe_status = COALESCE(?, transcribe_status),
                cloud_upload_status = COALESCE(?, cloud_upload_status),
                cloud_file_id = COALESCE(?, cloud_file_id),
                cloud_relative_path = COALESCE(?, cloud_relative_path)
            WHERE id = ?
            """,
            (
                status,
                local_path,
                error,
                ended_at,
                transcribe_status,
                cloud_upload_status,
                cloud_file_id,
                cloud_relative_path,
                session_id,
            ),
        )
        self._conn.commit()

    def clear_pid(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE live_sessions SET ffmpeg_pid = NULL WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()

    def increment_offline_streak(self, session_id: str) -> int:
        self._conn.execute(
            """
            UPDATE live_sessions
            SET offline_streak = offline_streak + 1
            WHERE id = ?
            """,
            (session_id,),
        )
        self._conn.commit()
        row = self.get(session_id)
        return row.offline_streak if row else 0

    def reset_offline_streak(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE live_sessions SET offline_streak = 0 WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()

    def set_offline_since(self, session_id: str, iso_ts: str) -> None:
        self._conn.execute(
            "UPDATE live_sessions SET offline_since_at = ? WHERE id = ?",
            (iso_ts, session_id),
        )
        self._conn.commit()

    def clear_offline_since(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE live_sessions SET offline_since_at = NULL WHERE id = ?",
            (session_id,),
        )
        self._conn.commit()

    def increment_reconnect_attempts(self, session_id: str) -> int:
        self._conn.execute(
            """
            UPDATE live_sessions
            SET reconnect_attempts = reconnect_attempts + 1
            WHERE id = ?
            """,
            (session_id,),
        )
        self._conn.commit()
        row = self.get(session_id)
        return row.reconnect_attempts if row else 0

    def append_segment_path(self, session_id: str, path: str) -> None:
        paths = self.list_segment_paths(session_id)
        paths.append(path)
        self._conn.execute(
            "UPDATE live_sessions SET segment_paths_json = ? WHERE id = ?",
            (json.dumps(paths), session_id),
        )
        self._conn.commit()

    def list_segment_paths(self, session_id: str) -> list[str]:
        row = self.get(session_id)
        if not row or not row.segment_paths_json:
            return []
        try:
            data = json.loads(row.segment_paths_json)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def update_recording_state(
        self,
        session_id: str,
        *,
        ffmpeg_pid: int,
        temp_path: str,
        session_dir: str | None = None,
    ) -> None:
        if session_dir is not None:
            self._conn.execute(
                """
                UPDATE live_sessions
                SET ffmpeg_pid = ?, temp_path = ?, session_dir = ?
                WHERE id = ?
                """,
                (ffmpeg_pid, temp_path, session_dir, session_id),
            )
        else:
            self._conn.execute(
                """
                UPDATE live_sessions
                SET ffmpeg_pid = ?, temp_path = ?
                WHERE id = ?
                """,
                (ffmpeg_pid, temp_path, session_id),
            )
        self._conn.commit()

    def list_streaming_summary_since(self, since_iso: str) -> list[dict]:
        from media2text.core.live.transcript_writer import count_transcript_segments

        rows = self._conn.execute(
            """
            SELECT id, creator_id, pipeline_mode, transcribe_status, local_path,
                   temp_path, started_at, ended_at, status
            FROM live_sessions
            WHERE started_at >= ? AND pipeline_mode = 'streaming'
            ORDER BY started_at DESC
            """,
            (since_iso,),
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            data = dict(row)
            media_path = data.get("local_path") or data.get("temp_path")
            out.append(
                {
                    "session_id": data["id"],
                    "creator_id": data["creator_id"],
                    "pipeline_mode": data.get("pipeline_mode"),
                    "transcribe_status": data.get("transcribe_status"),
                    "status": data.get("status"),
                    "started_at": data.get("started_at"),
                    "ended_at": data.get("ended_at"),
                    "transcript_segment_count": count_transcript_segments(media_path),
                }
            )
        return out


class PostProcessJobRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def enqueue(
        self,
        *,
        session_id: str,
        creator_id: str,
        mp4_path: str,
    ) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO post_process_jobs
              (id, session_id, creator_id, mp4_path, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (job_id, session_id, creator_id, mp4_path, now, now),
        )
        self._conn.commit()
        return job_id

    def get(self, job_id: str) -> PostProcessJobRow | None:
        row = self._conn.execute(
            "SELECT * FROM post_process_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return PostProcessJobRow(**dict(row)) if row else None

    def list_pending(self, *, limit: int = 10) -> list[PostProcessJobRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM post_process_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [PostProcessJobRow(**dict(r)) for r in rows]

    def claim_pending(self, *, limit: int = 1) -> list[PostProcessJobRow]:
        claimed: list[PostProcessJobRow] = []
        now = datetime.now(timezone.utc).isoformat()
        for _ in range(limit):
            row = self._conn.execute(
                """
                SELECT id FROM post_process_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                break
            cur = self._conn.execute(
                """
                UPDATE post_process_jobs
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            if cur.rowcount != 1:
                continue
            job = self.get(row["id"])
            if job:
                claimed.append(job)
        self._conn.commit()
        return claimed

    def mark_running(self, job_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE post_process_jobs
            SET status = 'running', updated_at = ?
            WHERE id = ?
            """,
            (now, job_id),
        )
        self._conn.commit()

    def update_stage(self, job_id: str, *, stage: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE post_process_jobs
            SET stage = ?, updated_at = ?
            WHERE id = ?
            """,
            (stage, now, job_id),
        )
        self._conn.commit()

    def mark_done(self, job_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE post_process_jobs
            SET status = 'done', updated_at = ?
            WHERE id = ?
            """,
            (now, job_id),
        )
        self._conn.commit()

    def mark_failed(self, job_id: str, *, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE post_process_jobs
            SET status = 'failed', error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, now, job_id),
        )
        self._conn.commit()

    def retry_failed(self, job_id: str) -> bool:
        """Reset a failed job to pending. Returns True if updated."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            UPDATE post_process_jobs
            SET status = 'pending', stage = NULL, error = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
            """,
            (now, job_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
        rows = self._conn.execute(
            "SELECT id, updated_at FROM post_process_jobs WHERE status = 'running'"
        ).fetchall()
        count = 0
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            try:
                updated = datetime.fromisoformat(
                    str(row["updated_at"]).replace("Z", "+00:00")
                )
            except ValueError:
                updated = datetime.now(timezone.utc)
            if updated.timestamp() > cutoff:
                continue
            self._conn.execute(
                """
                UPDATE post_process_jobs
                SET status = 'pending', stage = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            count += 1
        self._conn.commit()
        return count

    def list_in_flight(self, *, limit: int = 50) -> list[PostProcessJobRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM post_process_jobs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [PostProcessJobRow(**dict(r)) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM post_process_jobs
            GROUP BY status
            """
        ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}


class CreatorAgentJobRepo:
    """Job queue for creator distill bootstrap / evolve (Hermes §24.4.6)."""

    _ACTIVE_BOOTSTRAP = ("pending", "running", "deferred")

    def __init__(self, conn) -> None:
        self._conn = conn

    def get(self, job_id: str) -> CreatorAgentJobRow | None:
        row = self._conn.execute(
            "SELECT * FROM creator_agent_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return CreatorAgentJobRow(**dict(row)) if row else None

    def find_active_bootstrap(self, creator_id: str) -> CreatorAgentJobRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE creator_id = ? AND kind = 'bootstrap'
              AND status IN ('pending', 'running', 'deferred')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (creator_id,),
        ).fetchone()
        return CreatorAgentJobRow(**dict(row)) if row else None

    def list_deferred_bootstrap(self, *, limit: int = 50) -> list[CreatorAgentJobRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE kind = 'bootstrap' AND status = 'deferred'
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [CreatorAgentJobRow(**dict(r)) for r in rows]

    def find_evolve_by_source(self, creator_id: str, source_id: str) -> CreatorAgentJobRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE creator_id = ? AND kind = 'evolve' AND source_id = ?
              AND status IN ('pending', 'running', 'done')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (creator_id, source_id),
        ).fetchone()
        return CreatorAgentJobRow(**dict(row)) if row else None

    def enqueue_evolve(
        self,
        *,
        creator_id: str,
        source_id: str,
        trigger: str,
        payload: dict | None = None,
    ) -> str | None:
        """Enqueue evolve; returns job id or None if idempotent skip."""
        existing = self.find_evolve_by_source(creator_id, source_id)
        if existing:
            return None

        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload) if payload else None
        self._conn.execute(
            """
            INSERT INTO creator_agent_jobs (
              id, creator_id, kind, status, trigger, source_id,
              payload_json, created_at, updated_at
            )
            VALUES (?, ?, 'evolve', 'pending', ?, ?, ?, ?, ?)
            """,
            (job_id, creator_id, trigger, source_id, payload_json, now, now),
        )
        self._conn.commit()
        return job_id

    def enqueue_bootstrap(
        self,
        *,
        creator_id: str,
        trigger: str,
        payload: dict | None = None,
        force: bool = False,
    ) -> str | None:
        """Enqueue bootstrap; returns job id or None if idempotent skip."""
        existing = self.find_active_bootstrap(creator_id)
        if existing:
            if force and existing.status == "deferred":
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute(
                    """
                    UPDATE creator_agent_jobs
                    SET status = 'pending', trigger = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (trigger, now, existing.id),
                )
                self._conn.commit()
                return existing.id
            if existing.status in ("pending", "running"):
                return None
            if existing.status == "deferred" and not force:
                return existing.id

        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload) if payload else None
        self._conn.execute(
            """
            INSERT INTO creator_agent_jobs (
              id, creator_id, kind, status, trigger, source_id,
              payload_json, created_at, updated_at
            )
            VALUES (?, ?, 'bootstrap', 'pending', ?, NULL, ?, ?, ?)
            """,
            (job_id, creator_id, trigger, payload_json, now, now),
        )
        self._conn.commit()
        return job_id

    def mark_deferred(self, job_id: str, *, payload: dict | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload) if payload else None
        self._conn.execute(
            """
            UPDATE creator_agent_jobs
            SET status = 'deferred', payload_json = COALESCE(?, payload_json), updated_at = ?
            WHERE id = ?
            """,
            (payload_json, now, job_id),
        )
        self._conn.commit()

    def promote_deferred(self, job_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            UPDATE creator_agent_jobs
            SET status = 'pending', updated_at = ?
            WHERE id = ? AND status = 'deferred'
            """,
            (now, job_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def claim_pending(self, *, limit: int = 1) -> list[CreatorAgentJobRow]:
        """Claim jobs; evolve (higher priority) before bootstrap."""
        claimed: list[CreatorAgentJobRow] = []
        now = datetime.now(timezone.utc).isoformat()
        for _ in range(limit):
            row = self._conn.execute(
                """
                SELECT id FROM creator_agent_jobs
                WHERE status = 'pending'
                ORDER BY
                  CASE kind WHEN 'evolve' THEN 0 WHEN 'bootstrap' THEN 1 ELSE 2 END,
                  created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                break
            cur = self._conn.execute(
                """
                UPDATE creator_agent_jobs
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            if cur.rowcount != 1:
                continue
            job = self.get(row["id"])
            if job:
                claimed.append(job)
        self._conn.commit()
        return claimed

    def mark_done(self, job_id: str, *, payload: dict | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload) if payload else None
        self._conn.execute(
            """
            UPDATE creator_agent_jobs
            SET status = 'done', payload_json = COALESCE(?, payload_json), updated_at = ?
            WHERE id = ?
            """,
            (payload_json, now, job_id),
        )
        self._conn.commit()

    def mark_failed(self, job_id: str, *, error: str, payload: dict | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        merged = payload or {}
        merged["error"] = error
        self._conn.execute(
            """
            UPDATE creator_agent_jobs
            SET status = 'failed', payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(merged), now, job_id),
        )
        self._conn.commit()

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
        rows = self._conn.execute(
            "SELECT id, updated_at FROM creator_agent_jobs WHERE status = 'running'"
        ).fetchall()
        count = 0
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            try:
                updated = datetime.fromisoformat(
                    str(row["updated_at"]).replace("Z", "+00:00")
                )
            except ValueError:
                updated = datetime.now(timezone.utc)
            if updated.timestamp() > cutoff:
                continue
            self._conn.execute(
                """
                UPDATE creator_agent_jobs
                SET status = 'pending', updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            count += 1
        self._conn.commit()
        return count

    def distill_status(self, creator_id: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT kind, status, COUNT(*) AS n
            FROM creator_agent_jobs
            WHERE creator_id = ?
            GROUP BY kind, status
            """,
            (creator_id,),
        ).fetchall()
        by_kind: dict[str, dict[str, int]] = {}
        for row in rows:
            kind = str(row["kind"])
            by_kind.setdefault(kind, {})[str(row["status"])] = int(row["n"])
        latest = self._conn.execute(
            """
            SELECT * FROM creator_agent_jobs
            WHERE creator_id = ? AND kind = 'bootstrap'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (creator_id,),
        ).fetchone()
        latest_row = CreatorAgentJobRow(**dict(latest)) if latest else None
        return {"by_kind": by_kind, "latest_bootstrap": latest_row}


class MonitorTaskRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def enqueue(
        self,
        *,
        creator_id: str,
        task_type: str,
        dedupe_key: str | None = None,
        priority: int = 10,
        payload_json: str | None = None,
    ) -> str | None:
        ProbeExecutionGuard.record_violation("enqueue")
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                """
                INSERT INTO monitor_tasks
                  (id, creator_id, task_type, payload_json, priority, status,
                   dedupe_key, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    task_id,
                    creator_id,
                    task_type,
                    payload_json,
                    priority,
                    dedupe_key,
                    now,
                ),
            )
            self._conn.commit()
            return task_id
        except sqlite3.IntegrityError:
            return None

    def ensure_task(
        self,
        *,
        creator_id: str,
        task_type: str,
        dedupe_key: str,
        priority: int,
        payload_json: str | None = None,
    ) -> str | None:
        ProbeExecutionGuard.record_violation("ensure_task")
        return self.enqueue(
            creator_id=creator_id,
            task_type=task_type,
            dedupe_key=dedupe_key,
            priority=priority,
            payload_json=payload_json,
        )

    def cancel_pending(self, *, dedupe_key: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'cancelled', finished_at = ?
            WHERE dedupe_key = ? AND status = 'pending'
            """,
            (now, dedupe_key),
        )
        self._conn.commit()
        return cur.rowcount

    def has_active_dedupe(self, dedupe_key: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM monitor_tasks
            WHERE dedupe_key = ? AND status IN ('pending', 'running')
            LIMIT 1
            """,
            (dedupe_key,),
        ).fetchone()
        return row is not None

    def mark_running(self, task_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'running', started_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, task_id),
        )
        self._conn.commit()

    def get(self, task_id: str) -> MonitorTaskRow | None:
        row = self._conn.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return MonitorTaskRow(**dict(row)) if row else None

    def _select_fair_pending_id(
        self,
        *,
        min_priority: int,
        max_priority: int | None,
    ) -> str | None:
        """Pick oldest pending task per creator, then lowest priority globally."""
        if max_priority is not None:
            row = self._conn.execute(
                """
                SELECT t.id FROM monitor_tasks t
                INNER JOIN (
                  SELECT creator_id, MIN(created_at) AS min_created
                  FROM monitor_tasks
                  WHERE status = 'pending'
                    AND priority >= ? AND priority <= ?
                  GROUP BY creator_id
                ) heads
                  ON t.creator_id = heads.creator_id
                 AND t.created_at = heads.min_created
                WHERE t.status = 'pending'
                  AND t.priority >= ? AND t.priority <= ?
                ORDER BY t.priority ASC, t.created_at ASC
                LIMIT 1
                """,
                (min_priority, max_priority, min_priority, max_priority),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT t.id FROM monitor_tasks t
                INNER JOIN (
                  SELECT creator_id, MIN(created_at) AS min_created
                  FROM monitor_tasks
                  WHERE status = 'pending' AND priority >= ?
                  GROUP BY creator_id
                ) heads
                  ON t.creator_id = heads.creator_id
                 AND t.created_at = heads.min_created
                WHERE t.status = 'pending' AND t.priority >= ?
                ORDER BY t.priority ASC, t.created_at ASC
                LIMIT 1
                """,
                (min_priority, min_priority),
            ).fetchone()
        return str(row["id"]) if row else None

    def claim_pending(
        self,
        *,
        limit: int = 1,
        max_priority: int | None = None,
        min_priority: int = 0,
    ) -> list[MonitorTaskRow]:
        claimed: list[MonitorTaskRow] = []
        now = datetime.now(timezone.utc).isoformat()
        for _ in range(limit):
            task_id = self._select_fair_pending_id(
                min_priority=min_priority,
                max_priority=max_priority,
            )
            if not task_id:
                break
            row = {"id": task_id}
            cur = self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'running', started_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            if cur.rowcount != 1:
                continue
            task = self.get(row["id"])
            if task:
                claimed.append(task)
        self._conn.commit()
        return claimed

    def mark_done(self, task_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'done', finished_at = ?
            WHERE id = ?
            """,
            (now, task_id),
        )
        self._conn.commit()

    def mark_failed(self, task_id: str, *, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'failed', error = ?, finished_at = ?
            WHERE id = ?
            """,
            (error, now, task_id),
        )
        self._conn.commit()

    def fail_or_retry(self, task_id: str, *, error: str, max_retries: int) -> str:
        """On worker failure: retry (pending) or DLQ (failed). Returns outcome."""
        row = self.get(task_id)
        if not row:
            return "missing"
        next_attempt = int(row.attempt_count) + 1
        if next_attempt < max_retries:
            self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'pending', attempt_count = ?, error = ?,
                    started_at = NULL, finished_at = NULL
                WHERE id = ?
                """,
                (next_attempt, error, task_id),
            )
            self._conn.commit()
            return "retry"
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'failed', attempt_count = ?, error = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (next_attempt, error, now, task_id),
        )
        self._conn.commit()
        return "failed"

    def retry_failed(self, task_id: str) -> bool:
        """Reset a failed task to pending. Returns True if updated."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'pending', attempt_count = 0, error = NULL,
                started_at = NULL, finished_at = NULL, created_at = ?
            WHERE id = ? AND status = 'failed'
            """,
            (now, task_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def list_in_flight(self, *, limit: int = 50) -> list[MonitorTaskRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM monitor_tasks
            WHERE status IN ('pending', 'running')
            ORDER BY
              CASE status WHEN 'running' THEN 0 ELSE 1 END,
              priority ASC,
              created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [MonitorTaskRow(**dict(r)) for r in rows]

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
        rows = self._conn.execute(
            "SELECT id, started_at FROM monitor_tasks WHERE status = 'running'"
        ).fetchall()
        count = 0
        for row in rows:
            started = row["started_at"]
            if started:
                try:
                    started_dt = datetime.fromisoformat(
                        str(started).replace("Z", "+00:00")
                    )
                except ValueError:
                    started_dt = datetime.now(timezone.utc)
                if started_dt.timestamp() > cutoff:
                    continue
            elif older_than_sec > 0:
                continue
            self._conn.execute(
                """
                UPDATE monitor_tasks
                SET status = 'pending', started_at = NULL, error = NULL
                WHERE id = ?
                """,
                (row["id"],),
            )
            count += 1
        self._conn.commit()
        return count

    def release_running_content_tasks(self) -> int:
        """Yield Playwright to live lane while sessions are actively recording."""
        cur = self._conn.execute(
            """
            UPDATE monitor_tasks
            SET status = 'pending', started_at = NULL, error = NULL
            WHERE status = 'running'
              AND task_type IN ('sync_catalog', 'download', 'sync_dynamic')
            """
        )
        self._conn.commit()
        return cur.rowcount

    def count_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM monitor_tasks
            GROUP BY status
            """
        ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    def count_failed_recent_24h(self) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=24)
        ).isoformat()
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM monitor_tasks
            WHERE status = 'failed'
              AND finished_at IS NOT NULL
              AND finished_at >= ?
            """,
            (cutoff,),
        ).fetchone()
        return int(row["n"]) if row else 0


class PipelineEventRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        session_id: str,
        stage: str,
        status: str,
        job_id: str | None = None,
        detail: dict | None = None,
        started_at: str,
        ended_at: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        import uuid

        event_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO live_pipeline_events
              (id, session_id, job_id, stage, status, detail_json,
               started_at, ended_at, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                job_id,
                stage,
                status,
                json.dumps(detail, ensure_ascii=False) if detail else None,
                started_at,
                ended_at,
                duration_ms,
            ),
        )
        self._conn.commit()
        return event_id

    def complete(
        self,
        event_id: str,
        *,
        status: str,
        ended_at: str,
        duration_ms: int | None = None,
        detail: dict | None = None,
    ) -> None:
        if detail is not None:
            self._conn.execute(
                """
                UPDATE live_pipeline_events
                SET status = ?, ended_at = ?, duration_ms = ?, detail_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    ended_at,
                    duration_ms,
                    json.dumps(detail, ensure_ascii=False),
                    event_id,
                ),
            )
        else:
            self._conn.execute(
                """
                UPDATE live_pipeline_events
                SET status = ?, ended_at = ?, duration_ms = ?
                WHERE id = ?
                """,
                (status, ended_at, duration_ms, event_id),
            )
        self._conn.commit()

    def list_for_session(self, session_id: str) -> list[PipelineEventRow]:
        rows = self._conn.execute(
            """
            SELECT * FROM live_pipeline_events
            WHERE session_id = ?
            ORDER BY started_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [PipelineEventRow(**dict(r)) for r in rows]

    def stats_since(self, since_iso: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT stage, duration_ms
            FROM live_pipeline_events
            WHERE started_at >= ?
              AND duration_ms IS NOT NULL
              AND status = 'completed'
            """,
            (since_iso,),
        ).fetchall()
        by_stage: dict[str, list[int]] = {}
        for row in rows:
            stage = str(row["stage"])
            ms = int(row["duration_ms"])
            by_stage.setdefault(stage, []).append(ms)
        out: list[dict] = []
        for stage, values in sorted(by_stage.items()):
            values.sort()
            out.append(
                {
                    "stage": stage,
                    "count": len(values),
                    "p50_ms": _percentile(values, 50),
                    "p95_ms": _percentile(values, 95),
                }
            )
        return out

    def streaming_metrics_since(self, since_iso: str) -> dict:
        s1 = self._percentile_stats_for_events(
            since_iso, stage="streaming_stt", status="completed"
        )
        first_final = self._percentile_stats_for_events(
            since_iso, stage="streaming_stt", status="first_final"
        )
        s2 = self._offline_to_complete_stats(since_iso)
        s3 = self._offline_to_summarize_stats(since_iso)
        return {
            "s1_finalize_stt_ms": s1,
            "s2_offline_to_complete_ms": s2,
            "s3_offline_to_summarize_ms": s3,
            "first_final_latency_ms": first_final,
        }

    def _percentile_stats_for_events(
        self, since_iso: str, *, stage: str, status: str
    ) -> dict:
        rows = self._conn.execute(
            """
            SELECT duration_ms
            FROM live_pipeline_events
            WHERE started_at >= ?
              AND stage = ?
              AND status = ?
              AND duration_ms IS NOT NULL
            """,
            (since_iso, stage, status),
        ).fetchall()
        values = [int(row["duration_ms"]) for row in rows]
        return _aggregate_ms(values)

    def _offline_to_complete_stats(self, since_iso: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT ls.ended_at AS completed_at,
                   (
                     SELECT started_at FROM live_pipeline_events e
                     WHERE e.session_id = ls.id
                       AND e.stage = 'recording'
                       AND e.status = 'offline_pending'
                     ORDER BY started_at ASC LIMIT 1
                   ) AS offline_at
            FROM live_sessions ls
            WHERE ls.started_at >= ?
              AND ls.pipeline_mode = 'streaming'
              AND ls.status = 'completed'
              AND ls.ended_at IS NOT NULL
            """,
            (since_iso,),
        ).fetchall()
        deltas: list[int] = []
        for row in rows:
            offline_at = row["offline_at"]
            completed_at = row["completed_at"]
            if not offline_at or not completed_at:
                continue
            try:
                t0 = datetime.fromisoformat(str(offline_at).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            deltas.append(max(0, int((t1 - t0).total_seconds() * 1000)))
        return _aggregate_ms(deltas)

    def _offline_to_summarize_stats(self, since_iso: str) -> dict:
        rows = self._conn.execute(
            """
            SELECT (
                     SELECT started_at FROM live_pipeline_events e
                     WHERE e.session_id = ls.id
                       AND e.stage = 'recording'
                       AND e.status = 'offline_pending'
                     ORDER BY started_at ASC LIMIT 1
                   ) AS offline_at,
                   (
                     SELECT ended_at FROM live_pipeline_events e
                     WHERE e.session_id = ls.id
                       AND e.stage = 'summarize'
                       AND e.status = 'completed'
                     ORDER BY ended_at DESC LIMIT 1
                   ) AS summarize_at
            FROM live_sessions ls
            WHERE ls.started_at >= ?
              AND ls.pipeline_mode = 'streaming'
            """,
            (since_iso,),
        ).fetchall()
        deltas: list[int] = []
        for row in rows:
            offline_at = row["offline_at"]
            summarize_at = row["summarize_at"]
            if not offline_at or not summarize_at:
                continue
            try:
                t0 = datetime.fromisoformat(str(offline_at).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(summarize_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            deltas.append(max(0, int((t1 - t0).total_seconds() * 1000)))
        return _aggregate_ms(deltas)


def _aggregate_ms(values: list[int]) -> dict:
    if not values:
        return {"count": 0, "p50_ms": 0, "p95_ms": 0}
    values.sort()
    return {
        "count": len(values),
        "p50_ms": _percentile(values, 50),
        "p95_ms": _percentile(values, 95),
    }


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return int(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))


class CloudUploadRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def create(
        self,
        *,
        session_id: str,
        creator_id: str,
        platform: str,
        file_name: str,
        file_kind: str,
        local_path: str | None = None,
        size: int | None = None,
        pre_hash: str | None = None,
        part_index: int | None = None,
    ) -> str:
        uid = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO cloud_uploads
              (id, session_id, creator_id, platform, file_name, file_kind,
               local_path, size, pre_hash, upload_status, part_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                uid,
                session_id,
                creator_id,
                platform,
                file_name,
                file_kind,
                local_path,
                size,
                pre_hash,
                part_index,
            ),
        )
        self._conn.commit()
        return uid

    def mark_done(
        self,
        upload_id: str,
        *,
        cloud_file_id: str,
        cloud_relative_path: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE cloud_uploads
            SET upload_status = 'done',
                cloud_file_id = ?,
                cloud_relative_path = ?,
                uploaded_at = ?,
                error = NULL
            WHERE id = ?
            """,
            (cloud_file_id, cloud_relative_path, now, upload_id),
        )
        self._conn.commit()

    def mark_failed(self, upload_id: str, *, error: str) -> None:
        self._conn.execute(
            """
            UPDATE cloud_uploads
            SET upload_status = 'failed', error = ?
            WHERE id = ?
            """,
            (error, upload_id),
        )
        self._conn.commit()

    def list_for_session(self, session_id: str) -> list[CloudUploadRow]:
        rows = self._conn.execute(
            "SELECT * FROM cloud_uploads WHERE session_id = ? ORDER BY uploaded_at",
            (session_id,),
        ).fetchall()
        return [CloudUploadRow(**dict(r)) for r in rows]

    def find_done_by_local_path(
        self,
        workspace: Path,
        local_path: str | None,
        *,
        file_kinds: tuple[str, ...] = ("mp4", "flv", "m4s", "m3u8", "init_mp4"),
    ) -> CloudUploadRow | None:
        from media2text.core.storage.cloud_path import (
            normalize_workspace_rel,
            paths_match_workspace_rel,
        )

        target_rel = normalize_workspace_rel(workspace, local_path)
        if not target_rel:
            return None
        rows = self._conn.execute(
            """
            SELECT * FROM cloud_uploads
            WHERE upload_status = 'done'
              AND cloud_file_id IS NOT NULL
              AND local_path IS NOT NULL
            ORDER BY uploaded_at DESC
            """
        ).fetchall()
        for row in rows:
            upload = CloudUploadRow(**dict(row))
            if upload.file_kind not in file_kinds:
                continue
            if paths_match_workspace_rel(workspace, upload.local_path, target_rel):
                return upload
        return None

    def list_cleanup_candidates(
        self,
        *,
        root_prefix: str,
        require_transcripts: bool,
    ) -> list[CloudUploadRow]:
        rows = self._conn.execute(
            """
            SELECT cu.*
            FROM cloud_uploads cu
            JOIN live_sessions ls ON ls.id = cu.session_id
            WHERE cu.upload_status = 'done'
              AND cu.cloud_relative_path LIKE ?
              AND (
                ls.transcribe_status IS NULL
                OR ls.transcribe_status IN ('done', 'skipped', 'none')
              )
            ORDER BY cu.uploaded_at ASC
            """,
            (f"{root_prefix}%",),
        ).fetchall()
        candidates = [CloudUploadRow(**dict(r)) for r in rows]
        if not require_transcripts:
            return candidates
        by_session: dict[str, list[CloudUploadRow]] = {}
        for row in candidates:
            by_session.setdefault(row.session_id, []).append(row)
        eligible: list[CloudUploadRow] = []
        for session_id, uploads in by_session.items():
            kinds = {u.file_kind for u in uploads}
            if not kinds.intersection({"mp4", "flv"}):
                continue
            session = self._conn.execute(
                "SELECT transcribe_status FROM live_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            ts = session[0] if session else None
            if ts == "failed" or ts == "pending":
                continue
            if ts == "done" and "transcript_json" not in kinds:
                continue
            eligible.extend(uploads)
        eligible.sort(key=lambda r: r.uploaded_at or "")
        return eligible

    def delete_record(self, upload_id: str) -> None:
        self._conn.execute("DELETE FROM cloud_uploads WHERE id = ?", (upload_id,))
        self._conn.commit()


class LiveSnapshotRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def upsert(
        self,
        creator_id: str,
        *,
        is_live: bool,
        room_id: str | None = None,
        title: str | None = None,
        checked_at: str | None = None,
    ) -> bool:
        now = checked_at or datetime.now(timezone.utc).isoformat()
        live_int = 1 if is_live else 0
        existing = self.get(creator_id)
        if existing is not None:
            unchanged = (
                existing.is_live == live_int
                and existing.room_id == room_id
                and existing.title == title
            )
            self._conn.execute(
                """
                UPDATE creator_live_snapshots
                SET is_live = ?, room_id = ?, title = ?, checked_at = ?, probe_error = NULL
                WHERE creator_id = ?
                """,
                (live_int, room_id, title, now, creator_id),
            )
            self._conn.commit()
            return not unchanged
        self._conn.execute(
            """
            INSERT INTO creator_live_snapshots (
              creator_id, is_live, room_id, title, checked_at, probe_error
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (creator_id, live_int, room_id, title, now),
        )
        self._conn.commit()
        return True

    def touch_probe(self, creator_id: str, *, probe_error: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(creator_id)
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO creator_live_snapshots (
                  creator_id, is_live, room_id, title, checked_at, probe_error
                )
                VALUES (?, 0, NULL, NULL, ?, ?)
                """,
                (creator_id, now, probe_error),
            )
            self._conn.commit()
            return True
        self._conn.execute(
            """
            UPDATE creator_live_snapshots
            SET checked_at = ?, probe_error = ?
            WHERE creator_id = ?
            """,
            (now, probe_error, creator_id),
        )
        self._conn.commit()
        return True

    def get(self, creator_id: str) -> CreatorLiveSnapshotRow | None:
        row = self._conn.execute(
            "SELECT * FROM creator_live_snapshots WHERE creator_id = ?",
            (creator_id,),
        ).fetchone()
        if not row:
            return None
        return CreatorLiveSnapshotRow(**dict(row))


class DesktopEventRepo:
    def __init__(self, conn) -> None:
        self._conn = conn

    def enqueue_creator_updated(
        self, creator_id: str, *, payload: dict | None = None
    ) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload) if payload else None
        self._conn.execute(
            """
            INSERT INTO desktop_events (id, event_type, creator_id, payload_json, created_at)
            VALUES (?, 'creator.updated', ?, ?, ?)
            """,
            (event_id, creator_id, payload_json, now),
        )
        self._conn.commit()
        return event_id

    def claim_pending(self, *, limit: int = 50) -> list[DesktopEventRow]:
        rows = self._conn.execute(
            """
            SELECT id FROM desktop_events
            WHERE delivered_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[DesktopEventRow] = []
        for row in rows:
            full = self.get(row["id"])
            if full:
                out.append(full)
        return out

    def mark_delivered(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE desktop_events SET delivered_at = ? WHERE id = ?",
            (now, event_id),
        )
        self._conn.commit()

    def get(self, event_id: str) -> DesktopEventRow | None:
        row = self._conn.execute(
            "SELECT * FROM desktop_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        return DesktopEventRow(**dict(row)) if row else None


class DesktopChatRepo:
    """Backward-compatible facade over Hermes SessionDB (M0)."""

    def __init__(self, conn) -> None:
        from media2text.agent.hermes_state import MessageRow, SessionDB, parse_binding

        self._conn = conn
        self._db = SessionDB(conn)
        self._MessageRow = MessageRow
        self._parse_binding = parse_binding

    def _row_to_thread(self, row) -> DesktopChatThreadRow:
        binding = self._parse_binding(row["active_binding_json"])
        return DesktopChatThreadRow(
            id=row["display_thread_id"],
            creator_id=row["creator_id"],
            session_id=binding.get("session_id"),
            title=row["title"],
            provider_name=binding.get("provider_name"),
            model=str(binding.get("model") or "auto"),
            context_mode=str(binding.get("context_mode") or "both"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_thread(
        self,
        *,
        creator_id: str | None,
        session_id: str | None = None,
        title: str | None = None,
        provider_name: str | None = None,
        model: str = "auto",
        context_mode: str = "both",
    ) -> str:
        thread_id = str(uuid.uuid4())
        self._db.create_session(
            display_thread_id=thread_id,
            creator_id=creator_id,
            title=title,
            provider_name=provider_name,
            model=model,
            context_mode=context_mode,
            live_session_id=session_id,
        )
        return thread_id

    def get_thread(self, thread_id: str) -> DesktopChatThreadRow | None:
        row = self._db.get_thread_by_display_id(thread_id)
        if not row:
            return None
        return self._row_to_thread(row)

    def add_message(
        self,
        thread_id: str,
        *,
        role: str,
        content: str,
        thinking_text: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        session_id = self._db.get_active_session_for_thread(thread_id)
        return self._db.append_message(
            session_id,
            self._MessageRow(
                role=role,
                content=content,
                thinking_text=thinking_text,
                duration_ms=duration_ms,
            ),
        )

    def list_messages(self, thread_id: str) -> list[DesktopChatMessageRow]:
        rows = self._db.get_messages(thread_id)
        return [
            DesktopChatMessageRow(
                id=row["id"],
                thread_id=thread_id,
                role=row["role"],
                content=row["content"] or "",
                thinking_text=row["thinking_text"],
                duration_ms=row["duration_ms"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_threads(
        self,
        *,
        creator_id: str | None = None,
        session_id: str | None = None,
    ) -> list[DesktopChatThreadRow]:
        rows = self._db.list_threads(creator_id=creator_id, live_session_id=session_id)
        return [self._row_to_thread(row) for row in rows]

    def update_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        context_mode: str | None = None,
        session_id: str | None = None,
        clear_session: bool = False,
    ) -> bool:
        return self._db.update_session(
            thread_id,
            title=title,
            provider_name=provider_name,
            model=model,
            context_mode=context_mode,
            live_session_id=session_id,
            clear_live_session=clear_session,
        )

    def delete_thread(self, thread_id: str) -> bool:
        return self._db.delete_thread(thread_id)
