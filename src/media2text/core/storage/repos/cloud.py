import uuid
from datetime import datetime, timezone
from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.storage.models import CloudUploadRow
from media2text.core.storage.write_aware import WriteAwareRepo

_VIDEO_CLEANUP_FILE_KINDS = frozenset({"mp4", "flv", "m4s", "init_mp4"})  # sync cloud.cleanup


class CloudUploadRepo(WriteAwareRepo):
    def __init__(self, conn, *, cfg: AppConfig | None = None) -> None:
        super().__init__(conn, cfg=cfg)

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
        def _body() -> str:
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

        return self._mutate("cloud_upload.create", _body)

    def mark_done(
        self,
        upload_id: str,
        *,
        cloud_file_id: str,
        cloud_relative_path: str,
    ) -> None:
        def _body():
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

        self._mutate("cloud_upload.mark_done", _body)

    def mark_failed(self, upload_id: str, *, error: str) -> None:
        def _body():
            self._conn.execute(
                """
                    UPDATE cloud_uploads
                    SET upload_status = 'failed', error = ?
                    WHERE id = ?
                    """,
                (error, upload_id),
            )
            self._conn.commit()

        self._mutate("cloud_upload.mark_failed", _body)

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
                OR ls.transcribe_status IN (
                  'done', 'skipped', 'none', 'completed', 'failed'
                )
              )
            ORDER BY cu.uploaded_at ASC
            """,
            (f"{root_prefix}%",),
        ).fetchall()
        candidates = [CloudUploadRow(**dict(r)) for r in rows]
        video_only = [c for c in candidates if c.file_kind in _VIDEO_CLEANUP_FILE_KINDS]
        if not require_transcripts:
            return video_only
        by_session: dict[str, list[CloudUploadRow]] = {}
        for row in video_only:
            by_session.setdefault(row.session_id, []).append(row)
        eligible: list[CloudUploadRow] = []
        for session_id, uploads in by_session.items():
            session = self._conn.execute(
                "SELECT transcribe_status FROM live_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            ts = session[0] if session else None
            if ts in ("failed", "pending"):
                continue
            if ts in ("done", "completed"):
                session_kinds = {
                    u.file_kind
                    for u in self.list_for_session(session_id)
                    if u.upload_status == "done"
                }
                if "transcript_json" not in session_kinds:
                    continue
            eligible.extend(uploads)
        eligible.sort(key=lambda r: r.uploaded_at or "")
        return eligible

    def delete_record(self, upload_id: str) -> None:
        def _body():
            self._conn.execute("DELETE FROM cloud_uploads WHERE id = ?", (upload_id,))
            self._conn.commit()

        self._mutate("cloud_upload.delete_record", _body)

    def delete_records_by_cloud_file_id(self, cloud_file_id: str) -> int:
        def _body() -> int:
            cur = self._conn.execute(
                "DELETE FROM cloud_uploads WHERE cloud_file_id = ?",
                (cloud_file_id,),
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

        return self._mutate("cloud_upload.delete_records_by_cloud_file_id", _body)

