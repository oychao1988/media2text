from __future__ import annotations

DEFAULT_STREAMING_TARGETS_MS: dict[str, int] = {
    "s1_finalize_stt_p95": 10_000,
    "s2_offline_to_complete_p95": 50_000,
    "s3_offline_to_summarize_p95": 180_000,
    "first_final_latency_p95": 30_000,
}

_METRIC_TARGET_PAIRS: tuple[tuple[str, str], ...] = (
    ("s1_finalize_stt_ms", "s1_finalize_stt_p95"),
    ("s2_offline_to_complete_ms", "s2_offline_to_complete_p95"),
    ("s3_offline_to_summarize_ms", "s3_offline_to_summarize_p95"),
    ("first_final_latency_ms", "first_final_latency_p95"),
)


def streaming_targets_ms() -> dict[str, int]:
    return dict(DEFAULT_STREAMING_TARGETS_MS)


def check_streaming_targets(
    metrics: dict,
    targets_ms: dict[str, int] | None = None,
) -> dict:
    """Compare streaming P95 metrics against targets; return gate result."""
    targets = targets_ms or DEFAULT_STREAMING_TARGETS_MS
    violations: list[dict] = []
    checked: list[dict] = []
    skipped: list[dict] = []

    for metric_key, target_key in _METRIC_TARGET_PAIRS:
        if metric_key not in metrics:
            skipped.append({"metric": metric_key, "reason": "not_available"})
            continue
        if target_key not in targets:
            skipped.append({"metric": metric_key, "reason": "no_target"})
            continue
        stat = metrics.get(metric_key) or {}
        count = int(stat.get("count") or 0)
        if count == 0:
            skipped.append({"metric": metric_key, "reason": "no_samples"})
            continue
        p95_ms = int(stat.get("p95_ms") or 0)
        target = int(targets[target_key])
        item = {
            "metric": metric_key,
            "p95_ms": p95_ms,
            "target_ms": target,
            "count": count,
        }
        checked.append(item)
        if p95_ms > target:
            violations.append({**item, "over_by_ms": p95_ms - target})

    return {
        "passed": len(violations) == 0,
        "checked": checked,
        "violations": violations,
        "skipped": skipped,
        "insufficient_data": len(checked) == 0,
    }
