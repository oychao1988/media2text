"""Monitor watch daemon control — logs only; start/stop use embedded MonitorSupervisor via /api/runtime."""

from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.runtime.log_format import format_daemon_log_lines
from media2text.core.runtime.monitor_log import is_sink_active, tail_lines
from media2text.core.runtime.status import LOG_NAME, build_daemon_status_legacy
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db


def daemon_status(cfg: AppConfig) -> dict:
    conn = open_db(cfg)
    try:
        return build_daemon_status_legacy(cfg, conn)
    finally:
        conn.close()


def read_daemon_logs(cfg: AppConfig, *, tail: int = 5) -> dict:
    ws = cfg.ensure_workspace()
    log_path = ws / LOG_NAME
    n = max(1, min(tail, 500))
    if is_sink_active():
        raw_lines = tail_lines(tail=n, log_path=log_path)
    elif not log_path.is_file():
        return {"ok": True, "lines": [], "path": str(log_path)}
    else:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "error": str(exc), "path": str(log_path), "lines": []}
        raw_lines = text.splitlines()[-n:]
    conn = open_db(cfg)
    try:
        creator_names = {
            row.id: (row.display_name or row.sec_uid)
            for row in CreatorRepo(conn).list_all()
        }
    finally:
        conn.close()
    return {
        "ok": True,
        "path": str(log_path),
        "lines": format_daemon_log_lines(raw_lines, creator_names=creator_names),
    }
