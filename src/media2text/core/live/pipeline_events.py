from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from media2text.core.storage.repos import PipelineEventRepo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(
    conn,
    *,
    session_id: str,
    stage: str,
    status: str,
    job_id: str | None = None,
    detail: dict | None = None,
    duration_ms: int | None = None,
) -> str:
    """Insert a single-point pipeline event (no duration)."""
    repo = PipelineEventRepo(conn)
    return repo.insert(
        session_id=session_id,
        stage=stage,
        status=status,
        job_id=job_id,
        detail=detail,
        started_at=_now_iso(),
        ended_at=_now_iso(),
        duration_ms=0 if duration_ms is None else duration_ms,
    )


@contextmanager
def stage_event(
    conn,
    *,
    session_id: str,
    stage: str,
    job_id: str | None = None,
    detail: dict | None = None,
) -> Iterator[str]:
    """Record started on enter; completed or failed on exit."""
    repo = PipelineEventRepo(conn)
    started = _now_iso()
    t0 = datetime.now(timezone.utc)
    event_id = repo.insert(
        session_id=session_id,
        stage=stage,
        status="started",
        job_id=job_id,
        detail=detail,
        started_at=started,
        ended_at=None,
        duration_ms=None,
    )
    try:
        yield event_id
        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        repo.complete(
            event_id,
            status="completed",
            ended_at=_now_iso(),
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        detail_out = dict(detail or {})
        detail_out["error"] = str(exc)
        repo.complete(
            event_id,
            status="failed",
            ended_at=_now_iso(),
            duration_ms=duration_ms,
            detail=detail_out,
        )
        raise


def detail_json(detail: dict | None) -> str | None:
    if not detail:
        return None
    return json.dumps(detail, ensure_ascii=False)
