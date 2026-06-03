import os
import uuid
from datetime import datetime, timezone

from media2text.core.platform.douyin.models import AwemeItem
import json

from media2text.core.storage.models import (
    AwemeRow,
    CloudUploadRow,
    CreatorRow,
    DynamicRow,
    LiveSessionRow,
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
    ) -> str:
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO live_sessions
              (id, creator_id, room_id, ffmpeg_pid, started_at, temp_path, status,
               first_seen_live_at, recording_started_at, platform_live_started_at)
            VALUES (?, ?, ?, ?, ?, ?, 'recording', ?, ?, ?)
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
        for row in rows:
            if row.status != "recording" or row.ffmpeg_pid is None:
                continue
            if (row.reconnect_attempts or 0) > 0:
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
    ) -> None:
        self._conn.execute(
            """
            UPDATE live_sessions
            SET ffmpeg_pid = ?, temp_path = ?
            WHERE id = ?
            """,
            (ffmpeg_pid, temp_path, session_id),
        )
        self._conn.commit()


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
    ) -> str:
        uid = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO cloud_uploads
              (id, session_id, creator_id, platform, file_name, file_kind,
               local_path, size, pre_hash, upload_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
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
            if "mp4" not in kinds:
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
