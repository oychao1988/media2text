"""Post-transcribe hooks for live finalize and similar pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.transcript_writer import resolve_summarize_paths
from media2text.core.summarize.errors import SummarizeConfigError
from media2text.core.summarize.factory import create_summarize_backend, summarize_engine_available
from media2text.core.summarize.runner import summarize_one

log = structlog.get_logger()


def maybe_summarize_after_transcribe(
    cfg: AppConfig,
    mp4: Path,
    *,
    transcribe_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not cfg.summarize.enabled or not cfg.summarize.on_transcribe_complete:
        return {}

    workspace = cfg.ensure_workspace()
    media = Path(mp4)
    if not media.is_absolute():
        media = media.resolve()
    resolved = resolve_summarize_paths(media, workspace=workspace)
    if resolved is None:
        reason = "no_transcript"
        if transcribe_meta:
            if transcribe_meta.get("transcribe_error"):
                reason = "transcribe_failed"
            elif transcribe_meta.get("transcribe_skipped"):
                reason = str(
                    transcribe_meta.get("transcribe_skip_reason") or "transcribe_skipped"
                )
        log.warning("live_summarize_skipped", path=str(mp4), reason=reason)
        return {"summarize_skipped": True, "summarize_skip_reason": reason}

    write_media, _transcript_path = resolved

    ok, reason = summarize_engine_available(cfg)
    if not ok:
        log.warning("live_summarize_skipped", path=str(write_media), reason=reason or "summarize_unavailable")
        return {
            "summarize_skipped": True,
            "summarize_skip_reason": reason or "summarize_unavailable",
        }

    try:
        backend = create_summarize_backend(cfg)
    except SummarizeConfigError as exc:
        log.warning("live_summarize_skipped", path=str(write_media), reason=str(exc))
        return {"summarize_skipped": True, "summarize_skip_reason": str(exc)}

    try:
        item = summarize_one(write_media, cfg, backend)
    except Exception as exc:  # noqa: BLE001
        log.exception("live_summarize_failed", path=str(write_media), error=str(exc))
        return {"summarize_error": str(exc)}

    if item.get("skipped"):
        return {
            "summarize_skipped": True,
            "summary_path": item.get("summary_path"),
            "summarize_skip_reason": "already_exists",
        }

    log.info("live_summarize_completed", path=str(write_media), summary_path=item.get("summary_path"))
    return {
        "summarized": True,
        "summary_path": item.get("summary_path"),
        "profile": item.get("profile"),
        "chunks": item.get("chunks"),
    }
