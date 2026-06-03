from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from media2text.core.config import AppConfig
from media2text.core.storage.models import LiveSessionRow
from media2text.core.summarize.base import SummaryResult, usage_delta
from media2text.core.summarize.chunker import chunk_plain_text, chunk_segments, format_chunk
from media2text.core.summarize.errors import SummarizeError
from media2text.core.summarize.grouper import session_start_ts
from media2text.core.summarize.openai_backend import SummarizeBackend, primary_model
from media2text.core.summarize.prompts import resolve_profile
from media2text.core.summarize.reader import TranscriptSegment, load_transcript, transcript_path_for_media
from media2text.core.summarize.writer import write_merged_summary


def _yyyymmdd_from_sessions(sessions: list[LiveSessionRow], tz: str) -> str:
    starts = [session_start_ts(s) for s in sessions]
    starts = [t for t in starts if t]
    if not starts:
        raise SummarizeError("cannot determine merge date from sessions")
    first = min(starts)
    local = first.astimezone(ZoneInfo(tz))
    return local.strftime("%Y%m%d")


def merge_sessions(
    cfg: AppConfig,
    *,
    backend: SummarizeBackend,
    sessions: list[LiveSessionRow],
    workspace: Path,
    profile: str | None = None,
    force: bool = False,
) -> tuple[Path, Path]:
    del workspace  # reserved for future path resolution
    if len(sessions) < 2:
        raise SummarizeError("merge requires at least two sessions")

    creator_ids = {s.creator_id for s in sessions}
    if len(creator_ids) != 1:
        raise SummarizeError("all sessions must share the same creator_id")

    paths = [Path(s.local_path) for s in sessions if s.local_path]
    if len(paths) != len(sessions):
        raise SummarizeError("missing local_path on session")

    prof = resolve_profile(
        profile or cfg.summarize.default_profile,
        media_kind="live",
    )

    live_dir = paths[0].parent
    date_key = _yyyymmdd_from_sessions(sessions, cfg.summarize.merge_date_tz)
    merged_md = live_dir / f"{date_key}_merged.summary.md"
    if merged_md.is_file() and not force:
        return merged_md, merged_md.with_suffix(".summary.json")

    sources: list[dict] = []
    all_segments: list[TranscriptSegment] = []
    plain_blocks: list[str] = []

    for i, (session, media) in enumerate(zip(sessions, paths, strict=True), start=1):
        doc = load_transcript(transcript_path_for_media(media))
        sources.append(
            {
                "session_id": session.id,
                "media_path": str(media),
                "part": i,
            }
        )
        if doc.segments:
            for seg in doc.segments:
                all_segments.append(
                    TranscriptSegment(
                        start=seg.start,
                        end=seg.end,
                        text=f"(Part {i}) {seg.text}",
                    )
                )
        else:
            plain_blocks.append(f"## Part {i}\n{doc.plain_text}")

    chunk_cfg = cfg.summarize.chunk

    usage_before = backend.usage.copy() if hasattr(backend, "usage") else None

    if all_segments:
        seg_chunks = chunk_segments(
            all_segments,
            max_chars=chunk_cfg.max_chars,
            max_minutes=chunk_cfg.minutes,
        )
        texts = [format_chunk(c) for c in seg_chunks]
        markdown = backend.summarize_chunks(prof, texts, merge_pass=True)
        chunk_count = len(texts)
    else:
        full_text = "\n\n".join(plain_blocks)
        texts = chunk_plain_text(full_text, max_chars=chunk_cfg.max_chars)
        markdown = backend.summarize_chunks(prof, texts, merge_pass=True)
        chunk_count = len(texts)

    llm_usage = None
    if usage_before is not None and hasattr(backend, "usage"):
        llm_usage = usage_delta(usage_before, backend.usage).to_dict()

    result = SummaryResult(
        engine=getattr(backend, "engine", cfg.summarize.engine),
        model=getattr(backend, "model", primary_model(cfg.summarize.llm)),
        profile=prof,
        markdown=markdown,
        chunks=chunk_count,
        provider_base_url=getattr(backend, "provider_base_url", None),
        llm_usage=llm_usage,
    )
    return write_merged_summary(
        live_dir,
        date_key,
        result,
        sources=sources,
        parse_sections=cfg.summarize.parse_sections,
    )
