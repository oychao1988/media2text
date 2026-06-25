from __future__ import annotations

from datetime import datetime, timezone

from media2text.core.storage.repos import _percentile


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_g1_detected_to_recording_ms(conn, *, since_iso: str | None = None) -> dict:
    """G1: latency from detected_live to recording started per session (milliseconds)."""
    params: tuple = ()
    since_clause = ""
    if since_iso:
        since_clause = "AND started_at >= ?"
        params = (since_iso,)

    rows = conn.execute(
        f"""
        SELECT session_id,
               MIN(CASE WHEN stage = 'detected_live' THEN started_at END) AS detected_at,
               MIN(CASE WHEN stage = 'recording' AND status = 'started'
                        THEN started_at END) AS recording_at
        FROM live_pipeline_events
        WHERE 1=1 {since_clause}
        GROUP BY session_id
        HAVING detected_at IS NOT NULL AND recording_at IS NOT NULL
        """,
        params,
    ).fetchall()

    deltas_ms: list[int] = []
    for row in rows:
        detected = _parse_iso(str(row["detected_at"]))
        recording = _parse_iso(str(row["recording_at"]))
        if detected is None or recording is None:
            continue
        delta = (recording - detected).total_seconds() * 1000.0
        if delta >= 0:
            deltas_ms.append(int(delta))

    deltas_ms.sort()
    if not deltas_ms:
        return {
            "sample_count": 0,
            "p50_ms": None,
            "p95_ms": None,
            "threshold_ms": 30_000,
            "environment": "mock" if since_iso is None else "filtered",
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "sample_count": len(deltas_ms),
        "p50_ms": _percentile(deltas_ms, 50),
        "p95_ms": _percentile(deltas_ms, 95),
        "threshold_ms": 30_000,
        "environment": "mock" if len(deltas_ms) <= 3 else "production",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
