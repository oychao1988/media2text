import json
import uuid
from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.models import AwemeRow, CreatorRow, DynamicRow
from media2text.core.storage.write_aware import WriteAwareRepo

class CreatorRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

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
        def _body() -> str:
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

        return self._mutate("creator.add", _body)

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
        def _body() -> bool:
            cur = self._conn.execute(
                "UPDATE creators SET monitor_enabled = ? WHERE id = ?",
                (1 if enabled else 0, creator_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

        return self._mutate("creator.set_monitor_enabled", _body)

    def set_content_sync_enabled(self, creator_id: str, *, enabled: bool) -> bool:
        def _body() -> bool:
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

        return self._mutate("creator.set_content_sync_enabled", _body)

    def set_auto_record_override(self, creator_id: str, override: str) -> bool:
        def _body() -> bool:
            cur = self._conn.execute(
                "UPDATE creators SET auto_record_override = ? WHERE id = ?",
                (override, creator_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

        return self._mutate("creator.set_auto_record_override", _body)

    def set_vod_due(self, creator_id: str, iso: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET vod_due_at = ? WHERE id = ?",
                (iso, creator_id),
            )
            self._conn.commit()

        self._mutate("creator.set_vod_due", _body)

    def set_archive_due(self, creator_id: str, iso: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET archive_due_at = ? WHERE id = ?",
                (iso, creator_id),
            )
            self._conn.commit()

        self._mutate("creator.set_archive_due", _body)

    def set_dynamic_due(self, creator_id: str, iso: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET dynamic_due_at = ? WHERE id = ?",
                (iso, creator_id),
            )
            self._conn.commit()

        self._mutate("creator.set_dynamic_due", _body)

    def clear_vod_due(self, creator_id: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET vod_due_at = NULL WHERE id = ?",
                (creator_id,),
            )
            self._conn.commit()

        self._mutate("creator.clear_vod_due", _body)

    def clear_archive_due(self, creator_id: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET archive_due_at = NULL WHERE id = ?",
                (creator_id,),
            )
            self._conn.commit()

        self._mutate("creator.clear_archive_due", _body)

    def clear_dynamic_due(self, creator_id: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET dynamic_due_at = NULL WHERE id = ?",
                (creator_id,),
            )
            self._conn.commit()

        self._mutate("creator.clear_dynamic_due", _body)

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
        def _body():
            self._conn.execute(
                "UPDATE creators SET sync_needs_download = 1 WHERE id = ?",
                (creator_id,),
            )
            self._conn.commit()

        self._mutate("creator.mark_sync_needs_download", _body)

    def clear_sync_needs_download(self, creator_id: str) -> None:
        def _body():
            self._conn.execute(
                "UPDATE creators SET sync_needs_download = 0 WHERE id = ?",
                (creator_id,),
            )
            self._conn.commit()

        self._mutate("creator.clear_sync_needs_download", _body)

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
        def _body() -> bool:
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

        return self._mutate("creator.update_profile", _body)

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
        def _body() -> bool:
            cur = self._conn.execute("DELETE FROM creators WHERE id = ?", (creator_id,))
            self._conn.commit()
            return cur.rowcount > 0

        return self._mutate("creator.remove", _body)


class AwemeRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

    def upsert_listed(self, *, creator_id: str, item: AwemeItem) -> bool:
        def _body() -> bool:
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

        return self._mutate("aweme.upsert_listed", _body)

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
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                    UPDATE awemes SET sync_status = 'downloaded', local_path = ?, updated_at = ?
                    WHERE aweme_id = ?
                    """,
                (local_path, now, aweme_id),
            )
            self._conn.commit()

        self._mutate("aweme.mark_downloaded", _body)

    def mark_failed(self, aweme_id: str, *, error: str) -> None:
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                    UPDATE awemes SET sync_status = 'failed', transcribe_status = ?, updated_at = ?
                    WHERE aweme_id = ?
                    """,
                (error[:500], now, aweme_id),
            )
            self._conn.commit()

        self._mutate("aweme.mark_failed", _body)

    def reset_failed_to_listed(self, aweme_id: str) -> bool:
        def _body() -> bool:
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

        return self._mutate("aweme.reset_failed_to_listed", _body)

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
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                    UPDATE awemes SET local_path = NULL, updated_at = ?
                    WHERE aweme_id = ?
                    """,
                (now, aweme_id),
            )
            self._conn.commit()

        self._mutate("aweme.clear_local_path", _body)

    def delete(self, aweme_id: str) -> bool:
        def _body() -> bool:
            cur = self._conn.execute(
                "DELETE FROM awemes WHERE aweme_id = ?",
                (aweme_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

        return self._mutate("aweme.delete", _body)

    def mark_transcribed(self, aweme_id: str, *, transcript_path: str) -> None:
        def _body():
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

        self._mutate("aweme.mark_transcribed", _body)

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


class DynamicRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

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
        def _body() -> bool:
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

        return self._mutate("dynamic.upsert_listed", _body)

    def mark_synced(
        self,
        dynamic_id: str,
        *,
        image_count: int,
        text: str | None = None,
        refs_json: str | None = None,
    ) -> None:
        def _body():
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

        self._mutate("dynamic.mark_synced", _body)

    def mark_failed(self, dynamic_id: str, *, error: str) -> None:
        def _body():
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                    UPDATE dynamics SET sync_status = 'failed', updated_at = ?
                    WHERE dynamic_id = ?
                    """,
                (now, dynamic_id),
            )
            self._conn.commit()

        self._mutate("dynamic.mark_failed", _body)

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


