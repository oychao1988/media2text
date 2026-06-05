"""Cached doctor health for GET /api/health."""

from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.doctor_checks import build_doctor_report
from media2text.core.workspace import open_db

_cache: dict | None = None


def get_health_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = refresh_health_cache()
    return _cache


def refresh_health_cache(cfg: AppConfig | None = None) -> dict:
    global _cache
    cfg = cfg or AppConfig.load()
    conn = open_db(cfg)
    try:
        report = build_doctor_report(cfg, conn)
    finally:
        conn.close()
    _cache = {
        "ok": True,
        "ready": True,
        "doctor_ok": report["ok"],
        "checks": report["checks"],
        "compliance_accepted": report["compliance_accepted"],
        "index_stale": report["index_stale"],
        "monitor_lock_pid": report["monitor_lock_pid"],
        "api_features": {"config_provider_secrets": True},
    }
    return _cache


def clear_health_cache() -> None:
    global _cache
    _cache = None
