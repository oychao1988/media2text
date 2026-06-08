from __future__ import annotations

from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.desktop.state_events import enqueue_creator_updated
from media2text.core.live.pipeline_events import record_event
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


class StateWriter:
    """Single write path for session obs_* and offline semantics (R2c-1 minimal set)."""

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
        now = datetime.now(timezone.utc).isoformat()
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

    def set_offline_since(self, session_id: str, iso: str, *, creator_id: str) -> None:
        self._sessions.set_offline_since(session_id, iso)
        self.write_obs(session_id, still_live=False, ffmpeg_alive=None, stt_alive=None)
        record_event(
            self._conn,
            session_id=session_id,
            stage="recording",
            status="offline_pending",
        )
        self._emit_live_ended(creator_id, session_id)
        enqueue_creator_updated(self._conn, creator_id)

    def clear_offline_since(self, session_id: str, *, creator_id: str) -> None:
        self._sessions.clear_offline_since(session_id)
        self.write_obs(session_id, still_live=True, ffmpeg_alive=None, stt_alive=None)
        record_event(
            self._conn,
            session_id=session_id,
            stage="recording",
            status="offline_cancelled",
        )
        enqueue_creator_updated(self._conn, creator_id)

    def _emit_live_ended(self, creator_id: str, session_id: str) -> None:
        creator = self._creators.get(creator_id)
        if creator is None:
            return
        label = creator_label(creator)
        self._notify.emit(
            NotifyEvent(
                kind=EventKind.LIVE_ENDED,
                title=label,
                body=(
                    f"检测到下播，等待 {self._cfg.live.offline_confirm_sec}s 确认后停录\n"
                    f"session: {session_id[:8]}…"
                ),
            )
        )
