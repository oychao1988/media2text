import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.storage.models import (
    CreatorLiveSnapshotRow,
    LiveSessionRow,
    PostProcessJobRow,
)
from media2text.core.storage.write_aware import WriteAwareRepo

class LiveSessionRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

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
        def _body():
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

        return self._mutate("live_session.create", _body)

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
        def _body() -> int:
            rows = self.list_active()
            count = 0
            now = datetime.now(timezone.utc)
            for row in rows:
                if row.status != "recording":
                    continue
                if row.ffmpeg_pid is None:
                    try:
                        started = datetime.fromisoformat(row.started_at.replace("Z", "+00:00"))
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
                if row.offline_since_at:
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

        return self._mutate("live_session.mark_stale_failed", _body)

    def list_active(self) -> list[LiveSessionRow]:
        rows = self._conn.execute(
            "SELECT * FROM live_sessions WHERE status IN ('recording', 'remuxing')"
        ).fetchall()
        return [LiveSessionRow(**dict(r)) for r in rows]

    def list_recording_creator_ids(self) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT creator_id FROM live_sessions
            WHERE status IN ('recording', 'remuxing')
            """
        ).fetchall()
        return [str(r["creator_id"]) for r in rows]

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
        def _body() -> None:
            self._conn.execute(
                """
                UPDATE live_sessions
                SET local_path = NULL, temp_path = NULL
                WHERE id = ?
                """,
                (session_id,),
            )
            self._conn.commit()

        self._mutate("live_session.clear_local_path", _body)

    def delete(self, session_id: str) -> bool:
        def _body():
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
                "DELETE FROM live_pipeline_events WHERE session_id = ?",
                (session_id,),
            )
            cur = self._conn.execute(
                "DELETE FROM live_sessions WHERE id = ?",
                (session_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

        return self._mutate("live_session.delete", _body)

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
        def _body() -> None:
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

        self._mutate("live_session.update_status", _body)

    def clear_pid(self, session_id: str) -> None:
        def _body() -> None:
            self._conn.execute(
                "UPDATE live_sessions SET ffmpeg_pid = NULL WHERE id = ?",
                (session_id,),
            )
            self._conn.commit()

        self._mutate("live_session.clear_pid", _body)

    def increment_offline_streak(self, session_id: str) -> int:
        def _body():
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

        return self._mutate("live_session.increment_offline_streak", _body)

    def reset_offline_streak(self, session_id: str) -> None:
        def _body() -> None:
            self._conn.execute(
                "UPDATE live_sessions SET offline_streak = 0 WHERE id = ?",
                (session_id,),
            )
            self._conn.commit()

        self._mutate("live_session.reset_offline_streak", _body)

    def set_offline_since(self, session_id: str, iso_ts: str) -> None:
        def _body() -> None:
            self._conn.execute(
                "UPDATE live_sessions SET offline_since_at = ? WHERE id = ?",
                (iso_ts, session_id),
            )
            self._conn.commit()

        self._mutate("live_session.set_offline_since", _body)

    def clear_offline_since(self, session_id: str) -> None:
        def _body() -> None:
            self._conn.execute(
                "UPDATE live_sessions SET offline_since_at = NULL WHERE id = ?",
                (session_id,),
            )
            self._conn.commit()

        self._mutate("live_session.clear_offline_since", _body)

    def increment_reconnect_attempts(self, session_id: str) -> int:
        def _body():
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

        return self._mutate("live_session.increment_reconnect_attempts", _body)

    def append_segment_path(self, session_id: str, path: str) -> None:
        def _body() -> None:
            paths = self.list_segment_paths(session_id)
            paths.append(path)
            self._conn.execute(
                "UPDATE live_sessions SET segment_paths_json = ? WHERE id = ?",
                (json.dumps(paths), session_id),
            )
            self._conn.commit()

        self._mutate("live_session.append_segment_path", _body)

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
        def _body() -> None:
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

        self._mutate("live_session.update_recording_state", _body)

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


class PostProcessJobRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def get_active_for_session(self, session_id: str) -> PostProcessJobRow | None:
        row = self._conn.execute(
            """
            SELECT * FROM post_process_jobs
            WHERE session_id = ? AND status IN ('pending', 'running')
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return PostProcessJobRow(**dict(row)) if row else None

    def enqueue(
        self,
        *,
        session_id: str,
        creator_id: str,
        mp4_path: str,
    ) -> str:
        def _body() -> str:
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

        return self._mutate("post_process.enqueue", _body)

    def ensure_enqueue(
        self,
        *,
        session_id: str,
        creator_id: str,
        mp4_path: str,
    ) -> str:
        """Return existing pending/running job id for session, or enqueue a new one."""
        existing = self.get_active_for_session(session_id)
        if existing is not None:
            return existing.id
        return self.enqueue(
            session_id=session_id,
            creator_id=creator_id,
            mp4_path=mp4_path,
        )

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
        def _body() -> list[PostProcessJobRow]:
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

        return self._mutate("post_process.claim_pending", _body)

    def mark_running(self, job_id: str) -> None:
        def _body() -> None:
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

        self._mutate("post_process.mark_running", _body)

    def update_stage(self, job_id: str, *, stage: str) -> None:
        def _body() -> None:
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

        self._mutate("post_process.update_stage", _body)

    def mark_done(self, job_id: str) -> None:
        def _body() -> None:
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

        self._mutate("post_process.mark_done", _body)

    def mark_failed(self, job_id: str, *, error: str) -> None:
        def _body() -> None:
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

        self._mutate("post_process.mark_failed", _body)

    def retry_failed(self, job_id: str) -> bool:
        def _body() -> bool:
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

        return self._mutate("post_process.retry_failed", _body)

    def reset_stale_running(self, *, older_than_sec: int = 3600) -> int:
        def _body() -> int:
            cutoff = datetime.now(timezone.utc).timestamp() - older_than_sec
            rows = self._conn.execute(
                """
                SELECT j.id, j.updated_at, j.session_id, s.status AS session_status
                FROM post_process_jobs j
                LEFT JOIN live_sessions s ON s.id = j.session_id
                WHERE j.status = 'running'
                """
            ).fetchall()
            count = 0
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                try:
                    updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
                except ValueError:
                    updated = datetime.now(timezone.utc)
                if updated.timestamp() > cutoff:
                    continue
                session_status = (row["session_status"] or "").strip().lower()
                if session_status in ("completed", "failed"):
                    self._conn.execute(
                        """
                        UPDATE post_process_jobs
                        SET status = 'failed', stage = NULL,
                            error = 'superseded:session_terminal', updated_at = ?
                        WHERE id = ?
                        """,
                        (now, row["id"]),
                    )
                else:
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

        return self._mutate("post_process.reset_stale_running", _body)

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




class LiveSnapshotRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def upsert(
        self,
        creator_id: str,
        *,
        is_live: bool,
        room_id: str | None = None,
        title: str | None = None,
        checked_at: str | None = None,
    ) -> bool:
        def _write() -> bool:
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

        return self._mutate("live_snapshot.upsert", _write)

    def touch_probe(self, creator_id: str, *, probe_error: str) -> bool:
        def _write() -> bool:
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

        return self._mutate("live_snapshot.touch_probe", _write)

    def get(self, creator_id: str) -> CreatorLiveSnapshotRow | None:
        row = self._conn.execute(
            "SELECT * FROM creator_live_snapshots WHERE creator_id = ?",
            (creator_id,),
        ).fetchone()
        if not row:
            return None
        return CreatorLiveSnapshotRow(**dict(row))

