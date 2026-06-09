from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.manifest import refresh_manifest
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateWriter:
    """Single write path for live session mutations (R2c minimal → R3b full)."""

    def __init__(
        self,
        conn,
        *,
        cfg: AppConfig,
        notify: NotifyService | None = None,
    ) -> None:
        self._conn = conn
        self._cfg = cfg
        self._sessions = LiveSessionRepo(conn)
        self._creators = CreatorRepo(conn)
        self._notify = notify or NotifyService(cfg)

    def write_obs(
        self,
        session_id: str,
        *,
        ffmpeg_alive: bool | None,
        stt_alive: bool | None,
        still_live: bool | None,
    ) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            UPDATE live_sessions SET
              obs_ffmpeg_alive = COALESCE(?, obs_ffmpeg_alive),
              obs_stt_alive = COALESCE(?, obs_stt_alive),
              obs_still_live = COALESCE(?, obs_still_live),
              obs_polled_at = ?
            WHERE id = ?
            """,
            (
                None if ffmpeg_alive is None else int(ffmpeg_alive),
                None if stt_alive is None else int(stt_alive),
                None if still_live is None else int(still_live),
                now,
                session_id,
            ),
        )
        self._conn.commit()

    def create_session(
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
        return self._sessions.create(
            creator_id=creator_id,
            room_id=room_id,
            temp_path=temp_path,
            ffmpeg_pid=ffmpeg_pid,
            platform_live_started_at=platform_live_started_at,
            pipeline_mode=pipeline_mode,
            session_dir=session_dir,
        )

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
        self._sessions.update_status(
            session_id,
            status=status,
            local_path=local_path,
            error=error,
            ended=ended,
            transcribe_status=transcribe_status,
            cloud_upload_status=cloud_upload_status,
            cloud_file_id=cloud_file_id,
            cloud_relative_path=cloud_relative_path,
        )

    def update_recording_state(
        self,
        session_id: str,
        *,
        ffmpeg_pid: int,
        temp_path: str,
        session_dir: str | None = None,
    ) -> None:
        self._sessions.update_recording_state(
            session_id,
            ffmpeg_pid=ffmpeg_pid,
            temp_path=temp_path,
            session_dir=session_dir,
        )

    def clear_pid(self, session_id: str) -> None:
        self._sessions.clear_pid(session_id)

    def append_segment_path(self, session_id: str, path: str) -> None:
        self._sessions.append_segment_path(session_id, path)

    def increment_reconnect_attempts(self, session_id: str) -> int:
        return self._sessions.increment_reconnect_attempts(session_id)

    def mark_stale_recordings_failed(self) -> int:
        return self._sessions.mark_stale_recordings_failed()

    def refresh_creator_manifest(
        self,
        *,
        sec_uid: str,
        workspace: Path,
        platform: str,
    ) -> None:
        refresh_manifest(
            self._conn,
            sec_uid=sec_uid,
            workspace=workspace,
            platform=platform,
        )

    def update_snapshot(self, creator_id: str, live_info) -> bool:
        from media2text.core.live.snapshot import upsert_live_snapshot

        changed = upsert_live_snapshot(self._conn, creator_id, live_info)
        if changed:
            self._enqueue_creator_updated_no_commit(creator_id)
            self._conn.commit()
        return changed

    def mark_snapshot_probe_failed(self, creator_id: str, *, error: str) -> bool:
        from media2text.core.live.snapshot import touch_snapshot_probe_failed

        changed = touch_snapshot_probe_failed(self._conn, creator_id, error=error)
        self._enqueue_creator_updated_no_commit(creator_id)
        self._conn.commit()
        return changed

    def record_pipeline_event(
        self,
        *,
        session_id: str,
        stage: str,
        status: str,
        job_id: str | None = None,
        detail: dict | None = None,
        duration_ms: int | None = None,
    ) -> str:
        from media2text.core.live.pipeline_events import record_event

        return record_event(
            self._conn,
            session_id=session_id,
            stage=stage,
            status=status,
            job_id=job_id,
            detail=detail,
            duration_ms=duration_ms,
        )

    def set_offline_since(self, session_id: str, iso: str, *, creator_id: str) -> None:
        now = _now_iso()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "UPDATE live_sessions SET offline_since_at = ? WHERE id = ?",
                (iso, session_id),
            )
            self._conn.execute(
                """
                UPDATE live_sessions SET
                  obs_still_live = 0,
                  obs_polled_at = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
            self._insert_pipeline_event(
                session_id=session_id,
                stage="recording",
                status="offline_pending",
            )
            self._enqueue_creator_updated_no_commit(creator_id)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        creator = self._creators.get(creator_id)
        if creator is not None:
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.LIVE_ENDED,
                    title=creator_label(creator),
                    body=(
                        f"检测到下播，等待 {self._cfg.live.offline_confirm_sec}s 确认后停录\n"
                        f"session: {session_id[:8]}…"
                    ),
                    creator_id=creator_id,
                    session_id=session_id,
                    dedupe_key=f"{EventKind.LIVE_ENDED.value}:{session_id}",
                )
            )

    def clear_offline_since(self, session_id: str, *, creator_id: str) -> None:
        now = _now_iso()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "UPDATE live_sessions SET offline_since_at = NULL WHERE id = ?",
                (session_id,),
            )
            self._conn.execute(
                """
                UPDATE live_sessions SET
                  obs_still_live = 1,
                  obs_polled_at = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
            self._insert_pipeline_event(
                session_id=session_id,
                stage="recording",
                status="offline_cancelled",
            )
            self._enqueue_creator_updated_no_commit(creator_id)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _insert_pipeline_event(
        self,
        *,
        session_id: str,
        stage: str,
        status: str,
        job_id: str | None = None,
        detail: dict | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        now = _now_iso()
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
                now,
                now,
                0,
            ),
        )
        return event_id

    def enqueue_creator_updated(self, creator_id: str) -> str:
        event_id = self._enqueue_creator_updated_no_commit(creator_id)
        self._conn.commit()
        return event_id

    def _enqueue_creator_updated_no_commit(self, creator_id: str) -> str:
        event_id = str(uuid.uuid4())
        now = _now_iso()
        self._conn.execute(
            """
            INSERT INTO desktop_events (id, event_type, creator_id, payload_json, created_at)
            VALUES (?, 'creator.updated', ?, NULL, ?)
            """,
            (event_id, creator_id, now),
        )
        return event_id

