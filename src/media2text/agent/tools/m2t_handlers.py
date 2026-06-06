"""m2t domain tool handlers — direct core calls, no HTTP self-call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from media2text.agent.profile_resolver import AgentProfileContext


from media2text.api.services import recording as recording_svc
from media2text.api.services import runtime as runtime_svc
from media2text.api.services.sessions_list import list_creator_sessions
from media2text.api.services.transcript import (
    _media_path_for_session,
    read_summary_text,
    read_transcript_payload,
)
from media2text.core.config import AppConfig
from media2text.core.creator import service as creator_svc
from media2text.core.live.post_process import drain_pending_jobs
from media2text.core.live.status import build_live_status
from media2text.core.notify import NotifyService
from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo


@dataclass
class ToolContext:
    cfg: AppConfig
    conn: Any
    creator_id: str | None = None
    supervisor: Any | None = None
    session_id: str | None = None
    display_thread_id: str | None = None
    profile: AgentProfileContext | dict[str, Any] | None = None


def _ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    out.update(extra)
    return out


def _resolve_creator(ctx: ToolContext, params: dict[str, Any]) -> str | None:
    return params.get("creator_id") or ctx.creator_id


def m2t_get_live_status(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = _resolve_creator(ctx, params)
    if cid:
        return _ok(build_live_status(ctx.cfg, ctx.conn, creator_id=cid, command="agent tool"))
    return _ok(runtime_svc.get_runtime_status(ctx.cfg, ctx.supervisor))


def m2t_list_creators(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    repo = CreatorRepo(ctx.conn)
    rows = repo.list_all() if params.get("all") else repo.list_monitored()
    stale_days = ctx.cfg.monitor.profile_stale_days
    items = [creator_svc.creator_list_item(r, stale_days=stale_days) for r in rows]
    return _ok({"creators": items})


def m2t_get_creator(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = params.get("creator_id")
    if not cid:
        return _err("MISSING_CREATOR", "creator_id required")
    detail = creator_svc.get_creator_detail(ctx.cfg, cid)
    if not detail:
        return _err("NOT_FOUND", "creator not found")
    return _ok(detail)


def m2t_start_recording(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = _resolve_creator(ctx, params)
    if not cid:
        return _err("MISSING_CREATOR", "未指定 creator_id")
    result = recording_svc.start_recording(ctx.cfg, ctx.conn, cid)
    if not result.get("ok"):
        return result
    return _ok(result)


def m2t_stop_recording(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = _resolve_creator(ctx, params)
    if not cid:
        return _err("MISSING_CREATOR", "未指定 creator_id")
    result = recording_svc.stop_recording(ctx.cfg, ctx.conn, cid)
    if not result.get("ok"):
        return result
    return _ok(result)


def m2t_daemon_start(ctx: ToolContext, **_params: Any) -> dict[str, Any]:
    if ctx.supervisor is None:
        return _err("NO_SUPERVISOR", "monitor supervisor unavailable")
    result = runtime_svc.start_runtime(ctx.cfg, ctx.supervisor)
    return result if result.get("ok") else result


def m2t_daemon_stop(ctx: ToolContext, **_params: Any) -> dict[str, Any]:
    if ctx.supervisor is None:
        return _err("NO_SUPERVISOR", "monitor supervisor unavailable")
    return runtime_svc.stop_runtime(ctx.cfg, ctx.supervisor)


def m2t_post_process_run(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    limit = int(params.get("limit") or 10)
    notify = NotifyService(ctx.cfg)
    results = drain_pending_jobs(ctx.cfg, ctx.conn, notify=notify, limit=limit)
    return _ok({"processed": len(results), "results": results})


def m2t_pipeline_run(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = _resolve_creator(ctx, params)
    if not cid:
        return _err("MISSING_CREATOR", "未指定 creator_id")
    if not CreatorRepo(ctx.conn).get(cid):
        return _err("NOT_FOUND", "creator not found")
    repo = MonitorTaskRepo(ctx.conn)
    task_id = repo.enqueue(
        creator_id=cid,
        task_type="pipeline_run",
        dedupe_key=f"pipeline:{cid}",
        priority=5,
    )
    if not task_id:
        return _err("ALREADY_QUEUED", "pipeline already queued", creator_id=cid)
    return _ok({"job_id": task_id, "status": "queued", "creator_id": cid})


def m2t_read_transcript(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    from media2text.core.storage.repos import LiveSessionRepo

    session_id = params.get("session_id")
    if not session_id:
        return _err("MISSING_SESSION", "session_id required")
    row = LiveSessionRepo(ctx.conn).get(session_id)
    if not row:
        return _err("NOT_FOUND", "session not found")
    media = _media_path_for_session(row)
    if media is None:
        return _err("NO_MEDIA", "session has no media path")
    try:
        payload = read_transcript_payload(media)
    except OSError as exc:
        return _err("READ_FAILED", str(exc))
    return _ok(payload)


def m2t_read_summary(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    from media2text.core.storage.repos import LiveSessionRepo

    session_id = params.get("session_id")
    if not session_id:
        return _err("MISSING_SESSION", "session_id required")
    row = LiveSessionRepo(ctx.conn).get(session_id)
    if not row:
        return _err("NOT_FOUND", "session not found")
    media = _media_path_for_session(row)
    if media is None:
        return _err("NO_MEDIA", "session has no media path")
    try:
        text = read_summary_text(media)
    except OSError as exc:
        return _err("READ_FAILED", str(exc))
    if text is None:
        return _err("NOT_FOUND", "summary not found")
    return _ok({"markdown": text})


def m2t_read_manifest(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = _resolve_creator(ctx, params)
    if not cid:
        return _err("MISSING_CREATOR", "未指定 creator_id")
    row = CreatorRepo(ctx.conn).get(cid)
    if not row:
        return _err("NOT_FOUND", "creator not found")
    path = ctx.cfg.ensure_workspace() / "creators" / row.sec_uid / "agent-manifest.json"
    if not path.is_file():
        return _err("NOT_FOUND", "manifest not found")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _err("READ_FAILED", str(exc))
    return _ok({"creator_id": cid, "manifest": manifest})


def m2t_list_sessions(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    cid = _resolve_creator(ctx, params)
    if not cid:
        return _err("MISSING_CREATOR", "未指定 creator_id")
    limit = int(params.get("limit") or 20)
    result = list_creator_sessions(
        ctx.conn,
        workspace=ctx.cfg.ensure_workspace(),
        creator_id=cid,
        limit=limit,
    )
    if not result.get("ok"):
        return result
    return _ok(result)
