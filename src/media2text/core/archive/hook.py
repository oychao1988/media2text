from __future__ import annotations

from pathlib import Path

import structlog

from media2text.core.archive.indexer import index_transcript_file
from media2text.core.config import AppConfig
from media2text.core.workspace import open_db

log = structlog.get_logger()


def index_transcript_safe(cfg: AppConfig, transcript_path: Path) -> None:
    """Best-effort incremental index after transcribe; never raises."""
    try:
        conn = open_db(cfg)
        ws = cfg.ensure_workspace()
        n = index_transcript_file(conn, Path(transcript_path), ws)
        log.info("archive_index_upsert", path=str(transcript_path), segments=n)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "archive_index_failed",
            path=str(transcript_path),
            error=str(exc),
        )
