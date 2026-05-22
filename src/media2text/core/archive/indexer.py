from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import structlog

from media2text.core.archive.schema import clear_segments, migrate_archive, rebuild_fts
from media2text.core.storage.repos import CreatorRepo, DynamicRepo

log = structlog.get_logger()


@dataclass
class IndexStats:
    indexed_files: int = 0
    indexed_segments: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _SessionRef:
    session_type: str
    session_id: str
    creator_id: str
    sec_uid: str
    media_path: str
    started_at: str | None


def _iso_from_aweme_create_time(create_time: int | None) -> str | None:
    if create_time is None:
        return None
    return datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()


def _media_path_from_transcript(transcript_path: Path) -> Path:
    name = transcript_path.name
    if name.endswith(".transcript.json"):
        return transcript_path.with_name(name[: -len(".transcript.json")] + ".mp4")
    return transcript_path.with_suffix(".mp4")


def _resolve_session(
    conn: sqlite3.Connection,
    *,
    transcript_path: Path,
    workspace: Path,
) -> _SessionRef | None:
    media_path = _media_path_from_transcript(transcript_path)
    media_str = str(media_path.resolve())

    row = conn.execute(
        "SELECT id, creator_id, started_at FROM live_sessions WHERE local_path = ?",
        (media_str,),
    ).fetchone()
    if row:
        creator = CreatorRepo(conn).get(row["creator_id"])
        if creator:
            return _SessionRef(
                session_type="live",
                session_id=row["id"],
                creator_id=creator.id,
                sec_uid=creator.sec_uid,
                media_path=media_str,
                started_at=row["started_at"],
            )

    row = conn.execute(
        "SELECT aweme_id, creator_id, create_time FROM awemes WHERE local_path = ?",
        (media_str,),
    ).fetchone()
    if row:
        creator = CreatorRepo(conn).get(row["creator_id"])
        if creator:
            return _SessionRef(
                session_type="vod",
                session_id=row["aweme_id"],
                creator_id=creator.id,
                sec_uid=creator.sec_uid,
                media_path=media_str,
                started_at=_iso_from_aweme_create_time(row["create_time"]),
            )

    try:
        rel = transcript_path.resolve().relative_to((workspace / "creators").resolve())
        parts = rel.parts
        if transcript_path.name == "content.md" and len(parts) >= 3 and parts[1] == "dynamics":
            dynamic_id = parts[2]
            sec_uid = parts[0]
            creator = CreatorRepo(conn).get_by_sec_uid(sec_uid, platform="bilibili")
            if creator:
                row = DynamicRepo(conn).get(dynamic_id)
                published = row.published_at if row else None
                return _SessionRef(
                    session_type="dynamic",
                    session_id=dynamic_id,
                    creator_id=creator.id,
                    sec_uid=sec_uid,
                    media_path=str(transcript_path.resolve()),
                    started_at=published,
                )
        rel_media = media_path.resolve().relative_to((workspace / "creators").resolve())
        media_parts = rel_media.parts
        if len(media_parts) >= 3 and media_parts[1] in ("live", "videos"):
            sec_uid = media_parts[0]
            creator = CreatorRepo(conn).get_by_sec_uid(sec_uid)
            if not creator:
                return None
            session_type = "live" if media_parts[1] == "live" else "vod"
            session_id = media_path.stem
            return _SessionRef(
                session_type=session_type,
                session_id=session_id,
                creator_id=creator.id,
                sec_uid=sec_uid,
                media_path=media_str,
                started_at=None,
            )
    except ValueError:
        pass
    return None


def _load_segments(transcript_path: Path) -> list[dict] | None:
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("archive_index_skip_read", path=str(transcript_path), error=str(exc))
        return None
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return None
    return raw


def _load_dynamic_text(content_path: Path) -> list[dict] | None:
    try:
        text = content_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        log.warning("archive_index_skip_read", path=str(content_path), error=str(exc))
        return None
    if not text:
        return None
    return [{"start": None, "end": None, "text": text}]


def index_transcript_file(
    conn: sqlite3.Connection,
    transcript_path: Path,
    workspace: Path,
) -> int:
    """Upsert segments for one transcript file. Returns segment count or 0 if skipped."""
    migrate_archive(conn)
    path = transcript_path.resolve()
    if not path.is_file():
        return 0

    session = _resolve_session(conn, transcript_path=path, workspace=workspace)
    if session is None:
        log.warning("archive_index_skip_no_session", path=str(path))
        return 0

    if path.name == "content.md":
        segments = _load_dynamic_text(path)
    else:
        segments = _load_segments(path)
    if segments is None:
        return 0

    transcript_str = str(path)
    conn.execute("DELETE FROM transcript_segments WHERE transcript_path = ?", (transcript_str,))
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = seg.get("start")
        end = seg.get("end")
        conn.execute(
            """
            INSERT INTO transcript_segments (
              session_type, session_id, creator_id, sec_uid, media_path, transcript_path,
              segment_index, start_sec, end_sec, text, started_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_type,
                session.session_id,
                session.creator_id,
                session.sec_uid,
                session.media_path,
                transcript_str,
                idx,
                float(start) if start is not None else None,
                float(end) if end is not None else None,
                text,
                session.started_at,
                now,
            ),
        )
        count += 1
    conn.commit()
    if count:
        rebuild_fts(conn)
    return count


def _collect_transcript_paths(
    conn: sqlite3.Connection,
    workspace: Path,
    *,
    creator_id: str | None,
) -> list[Path]:
    paths: set[Path] = set()
    creators = CreatorRepo(conn)
    if creator_id:
        rows = [creators.get(creator_id)]
    else:
        rows = creators.list_all()

    for creator in rows:
        if not creator:
            continue
        for row in conn.execute(
            "SELECT local_path FROM live_sessions WHERE creator_id = ? AND local_path IS NOT NULL",
            (creator.id,),
        ):
            p = Path(row["local_path"]).with_suffix(".transcript.json")
            if p.is_file():
                paths.add(p.resolve())
        for row in conn.execute(
            "SELECT local_path FROM awemes WHERE creator_id = ? AND local_path IS NOT NULL",
            (creator.id,),
        ):
            p = Path(row["local_path"]).with_suffix(".transcript.json")
            if p.is_file():
                paths.add(p.resolve())

    creators_root = workspace / "creators"
    if creators_root.is_dir():
        glob_pattern = "**/*.transcript.json"
        if creator_id:
            c = creators.get(creator_id)
            if c:
                root = creators_root / c.sec_uid
                if root.is_dir():
                    for p in root.glob(glob_pattern):
                        paths.add(p.resolve())
        else:
            for p in creators_root.glob(glob_pattern):
                paths.add(p.resolve())

    for creator in rows:
        if not creator or creator.platform != "bilibili":
            continue
        dyn_root = creators_root / creator.sec_uid / "dynamics"
        if dyn_root.is_dir():
            for content_md in dyn_root.glob("*/content.md"):
                paths.add(content_md.resolve())
    return sorted(paths)


def index_all(
    conn: sqlite3.Connection,
    workspace: Path,
    *,
    creator_id: str | None = None,
    rebuild: bool = False,
) -> IndexStats:
    migrate_archive(conn)
    stats = IndexStats()
    if rebuild:
        clear_segments(conn)

    for transcript_path in _collect_transcript_paths(conn, workspace, creator_id=creator_id):
        try:
            n = index_transcript_file(conn, transcript_path, workspace)
            if n == 0:
                stats.skipped.append(str(transcript_path))
            else:
                stats.indexed_files += 1
                stats.indexed_segments += n
        except Exception as exc:  # noqa: BLE001
            log.exception("archive_index_file_failed", path=str(transcript_path))
            stats.errors.append({"path": str(transcript_path), "error": str(exc)})

    if rebuild:
        rebuild_fts(conn)
    return stats
