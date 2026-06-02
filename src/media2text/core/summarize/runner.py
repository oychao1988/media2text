from __future__ import annotations

from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.manifest import refresh_manifest
from media2text.core.storage.models import LiveSessionRow
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo
from media2text.core.summarize.chunker import chunk_plain_text, chunk_segments, format_chunk
from media2text.core.summarize.errors import SummarizeError
from media2text.core.summarize.grouper import build_suggested_groups
from media2text.core.summarize.merger import merge_sessions
from media2text.core.summarize.base import SummaryResult, usage_delta
from media2text.core.summarize.openai_backend import SummarizeBackend, primary_model
from media2text.core.summarize.prompts import resolve_profile
from media2text.core.summarize.reader import (
    load_content_md,
    load_transcript,
    transcript_path_for_media,
)
from media2text.core.summarize.writer import summary_paths_for_media, write_summary


def detect_media_kind(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    if path.name == "content.md" or "dynamics" in parts:
        return "dynamic"
    if "live" in parts:
        return "live"
    if "videos" in parts:
        return "vod"
    if path.suffix == ".transcript.json" or path.name.endswith(".transcript.json"):
        parent = path.parent
        if "live" in {x.lower() for x in parent.parts}:
            return "live"
        return "vod"
    return "vod"


def _resolve_media_and_transcript(path: Path) -> tuple[Path, Path]:
    if path.name.endswith(".transcript.json"):
        base = path.with_name(path.name.removesuffix(".transcript.json"))
        for ext in (".mp4", ".mkv", ".webm", ".flv"):
            candidate = base.with_suffix(ext)
            if candidate.is_file():
                return candidate, path
        return base, path
    if path.name == "content.md":
        return path, path
    tpath = transcript_path_for_media(path)
    return path, tpath


def summarize_one(
    media: Path,
    cfg: AppConfig,
    backend: SummarizeBackend,
    *,
    profile: str | None = None,
    force: bool = False,
) -> dict:
    media_path, transcript_path = _resolve_media_and_transcript(media)
    md_out, _ = summary_paths_for_media(
        media_path if media_path.name != "content.md" else media_path
    )
    if md_out.is_file() and not force:
        return {
            "media_path": str(media_path),
            "summary_path": str(md_out),
            "skipped": True,
        }

    kind = detect_media_kind(media_path)
    prof = resolve_profile(profile or cfg.summarize.default_profile, media_kind=kind)

    usage_before = backend.usage.copy() if hasattr(backend, "usage") else None

    if transcript_path.name == "content.md":
        doc = load_content_md(transcript_path)
        texts = chunk_plain_text(doc.plain_text, max_chars=cfg.summarize.chunk.max_chars)
        markdown = backend.summarize_chunks(prof, texts)
        chunk_count = len(texts)
        source = transcript_path
        write_media = media_path
    else:
        doc = load_transcript(transcript_path)
        if doc.segments:
            seg_chunks = chunk_segments(
                doc.segments,
                max_chars=cfg.summarize.chunk.max_chars,
                max_minutes=cfg.summarize.chunk.minutes,
            )
            texts = [format_chunk(c) for c in seg_chunks]
        else:
            texts = chunk_plain_text(doc.plain_text, max_chars=cfg.summarize.chunk.max_chars)
        markdown = backend.summarize_chunks(prof, texts)
        chunk_count = len(texts)
        source = transcript_path
        write_media = media_path

    llm_usage = None
    if usage_before is not None and hasattr(backend, "usage"):
        llm_usage = usage_delta(usage_before, backend.usage).to_dict()

    result = SummaryResult(
        engine=getattr(backend, "engine", "openai"),
        model=getattr(backend, "model", primary_model(cfg.summarize.llm)),
        profile=prof,
        markdown=markdown,
        chunks=chunk_count,
        provider_base_url=getattr(backend, "provider_base_url", None),
        llm_usage=llm_usage,
    )
    summary_md, _ = write_summary(write_media, result, source_transcript=source)
    return {
        "media_path": str(write_media),
        "summary_path": str(summary_md),
        "profile": prof,
        "chunks": chunk_count,
        "skipped": False,
        "llm_usage": llm_usage,
    }


def _media_for_transcript(tpath: Path) -> Path:
    stem = tpath.name.removesuffix(".transcript.json")
    mp4 = tpath.parent / f"{stem}.mp4"
    if mp4.is_file():
        return mp4
    return tpath.parent / stem


def _summary_missing(media: Path) -> bool:
    md, _ = summary_paths_for_media(media)
    return not md.is_file()


def discover_backfill_targets(
    workspace: Path,
    *,
    creator_sec_uid: str | None = None,
    force: bool = False,
) -> list[Path]:
    """Transcript sidecars under workspace that still need a summary."""
    if creator_sec_uid:
        root = workspace / "creators" / creator_sec_uid
        pattern = "**/*.transcript.json"
        glob_root = root
    else:
        glob_root = workspace / "creators"
        pattern = "**/*.transcript.json"

    if not glob_root.is_dir():
        return []

    deduped: list[Path] = []
    seen: set[str] = set()
    for tpath in sorted(glob_root.glob(pattern)):
        media = _media_for_transcript(tpath)
        if not force and not _summary_missing(media):
            continue
        if not tpath.is_file():
            continue
        key = str(media.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(media)
    return deduped


def _discover_from_path(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    targets: list[Path] = []
    targets.extend(sorted(path.glob("**/*.transcript.json")))
    for mp4 in sorted(path.glob("**/*.mp4")):
        if transcript_path_for_media(mp4).is_file():
            targets.append(mp4)
    for md in sorted(path.glob("**/content.md")):
        targets.append(md)
    return targets


def _discover_for_creator(conn, creator_id: str, workspace: Path) -> list[Path]:
    targets: list[Path] = []
    awemes = AwemeRepo(conn)
    for row in awemes.list_for_creator(creator_id):
        if row.local_path and transcript_path_for_media(Path(row.local_path)).is_file():
            targets.append(Path(row.local_path))

    live_repo = LiveSessionRepo(conn)
    for row in live_repo.list_completed_for_creator(creator_id):
        if row.local_path and transcript_path_for_media(Path(row.local_path)).is_file():
            targets.append(Path(row.local_path))

    seen: set[str] = set()
    unique: list[Path] = []
    for p in targets:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def run_batch(
    cfg: AppConfig,
    conn,
    backend: SummarizeBackend,
    *,
    paths: list[Path] | None = None,
    creator_id: str | None = None,
    profile: str | None = None,
    force: bool = False,
    limit: int | None = None,
) -> dict:
    workspace = cfg.ensure_workspace()
    targets: list[Path] = []
    if paths:
        for p in paths:
            targets.extend(_discover_from_path(p))
    if creator_id:
        targets.extend(_discover_for_creator(conn, creator_id, workspace))

    seen: set[str] = set()
    deduped: list[Path] = []
    for p in targets:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    max_run = cfg.summarize.max_files_per_run
    if max_run and max_run > 0:
        deduped = deduped[:max_run]
    if limit is not None and limit > 0:
        deduped = deduped[:limit]

    results: list[dict] = []
    errors: list[dict] = []
    summarized = 0
    skipped = 0
    batch_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}

    for media in deduped:
        try:
            item = summarize_one(
                media, cfg, backend, profile=profile, force=force
            )
            if item.get("skipped"):
                skipped += 1
            else:
                summarized += 1
                u = item.get("llm_usage")
                if u:
                    batch_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                    batch_usage["completion_tokens"] += u.get("completion_tokens", 0)
                    batch_usage["total_tokens"] += u.get("total_tokens", 0)
                    batch_usage["requests"] += u.get("requests", 0)
            results.append(item)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(media), "error": str(exc)})

    suggested: list[dict] = []
    if creator_id:
        creator = CreatorRepo(conn).get(creator_id)
        if creator:
            rows = LiveSessionRepo(conn).list_completed_for_creator(creator_id)
            groups = build_suggested_groups(
                creator_id=creator_id,
                rows=rows,
                workspace=workspace,
                merge_gap_minutes=cfg.summarize.merge_gap_minutes,
                tz=cfg.summarize.merge_date_tz,
            )
            suggested = [g.to_dict() for g in groups]
            refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=workspace)
    elif results:
        sec_uids: set[str] = set()
        for item in results:
            mp = item.get("media_path")
            if not mp:
                continue
            parts = Path(mp).parts
            if "creators" in parts:
                idx = parts.index("creators")
                if idx + 1 < len(parts):
                    sec_uids.add(parts[idx + 1])
        for sec_uid in sec_uids:
            refresh_manifest(conn, sec_uid=sec_uid, workspace=workspace)

    return {
        "ok": not errors,
        "command": "summarize run",
        "summarized": summarized,
        "skipped": skipped,
        "llm_usage": batch_usage if batch_usage["requests"] else None,
        "results": results,
        "suggested_groups": suggested,
        "errors": errors,
    }


def backfill_batch(
    cfg: AppConfig,
    conn,
    backend: SummarizeBackend,
    *,
    creator_id: str | None = None,
    profile: str | None = None,
    force: bool = False,
    limit: int | None = None,
) -> dict:
    workspace = cfg.ensure_workspace()
    creator_sec_uid: str | None = None
    if creator_id:
        creator = CreatorRepo(conn).get(creator_id)
        if not creator:
            raise SummarizeError(f"creator not found: {creator_id}")
        creator_sec_uid = creator.sec_uid

    deduped = discover_backfill_targets(
        workspace,
        creator_sec_uid=creator_sec_uid,
        force=force,
    )
    pending = len(deduped)

    max_run = cfg.summarize.max_files_per_run
    if max_run and max_run > 0:
        deduped = deduped[:max_run]
    if limit is not None and limit > 0:
        deduped = deduped[:limit]

    results: list[dict] = []
    errors: list[dict] = []
    summarized = 0
    skipped = 0
    batch_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}

    for media in deduped:
        try:
            item = summarize_one(
                media, cfg, backend, profile=profile, force=force
            )
            if item.get("skipped"):
                skipped += 1
            else:
                summarized += 1
                u = item.get("llm_usage")
                if u:
                    batch_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                    batch_usage["completion_tokens"] += u.get("completion_tokens", 0)
                    batch_usage["total_tokens"] += u.get("total_tokens", 0)
                    batch_usage["requests"] += u.get("requests", 0)
            results.append(item)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(media), "error": str(exc)})

    sec_uids: set[str] = set()
    for item in results:
        mp = item.get("media_path")
        if not mp:
            continue
        parts = Path(mp).parts
        if "creators" in parts:
            idx = parts.index("creators")
            if idx + 1 < len(parts):
                sec_uids.add(parts[idx + 1])
    if creator_sec_uid:
        sec_uids.add(creator_sec_uid)
    for sec_uid in sorted(sec_uids):
        refresh_manifest(conn, sec_uid=sec_uid, workspace=workspace)

    return {
        "ok": not errors,
        "command": "summarize backfill",
        "pending": pending,
        "summarized": summarized,
        "skipped": skipped,
        "llm_usage": batch_usage if batch_usage["requests"] else None,
        "results": results,
        "errors": errors,
    }


def merge_batch(
    cfg: AppConfig,
    conn,
    backend: SummarizeBackend,
    *,
    session_ids: list[str] | None = None,
    path_list: list[Path] | None = None,
    creator_id: str | None = None,
    date: str | None = None,
    group_index: int | None = None,
    profile: str | None = None,
    force: bool = False,
) -> dict:
    workspace = cfg.ensure_workspace()
    live_repo = LiveSessionRepo(conn)
    sessions: list[LiveSessionRow] = []

    if session_ids:
        for sid in session_ids:
            row = live_repo.get(sid)
            if not row:
                raise SummarizeError(f"session not found: {sid}")
            sessions.append(row)
    elif path_list:
        for p in path_list:
            row = conn.execute(
                "SELECT * FROM live_sessions WHERE local_path = ?",
                (str(p),),
            ).fetchone()
            if row:
                sessions.append(LiveSessionRow(**dict(row)))
        if len(sessions) != len(path_list):
            raise SummarizeError("could not resolve all paths to live_sessions")
    elif creator_id and date:
        rows = live_repo.list_completed_for_creator(creator_id)
        groups = build_suggested_groups(
            creator_id=creator_id,
            rows=rows,
            workspace=workspace,
            merge_gap_minutes=cfg.summarize.merge_gap_minutes,
            tz=cfg.summarize.merge_date_tz,
        )
        matching = [g for g in groups if g.date == date]
        if not matching:
            raise SummarizeError(f"no suggested group for date {date}")
        if len(matching) > 1 and group_index is None:
            raise SummarizeError(
                f"multiple suggested groups for {date}; pass --group-index (0..{len(matching)-1})"
            )
        idx = group_index if group_index is not None else 0
        if idx < 0 or idx >= len(matching):
            raise SummarizeError(f"group_index out of range: {idx}")
        chosen = matching[idx]
        for sid in chosen.session_ids:
            row = live_repo.get(sid)
            if row:
                sessions.append(row)
    else:
        raise SummarizeError(
            "provide --sessions, --paths, or --creator with --date"
        )

    sessions.sort(key=lambda s: s.started_at)
    usage_before = backend.usage.copy() if hasattr(backend, "usage") else None
    md_path, _ = merge_sessions(
        cfg,
        backend=backend,
        sessions=sessions,
        workspace=workspace,
        profile=profile,
        force=force,
    )

    creator = CreatorRepo(conn).get(sessions[0].creator_id)
    if creator:
        refresh_manifest(conn, sec_uid=creator.sec_uid, workspace=workspace)

    llm_usage = None
    if usage_before is not None and hasattr(backend, "usage"):
        llm_usage = usage_delta(usage_before, backend.usage).to_dict()

    return {
        "ok": True,
        "command": "summarize merge",
        "merged_summary_path": str(md_path),
        "session_ids": [s.id for s in sessions],
        "parts": len(sessions),
        "llm_usage": llm_usage,
    }
