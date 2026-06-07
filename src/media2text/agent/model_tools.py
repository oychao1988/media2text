"""Dispatch Hermes core tools vs m2t domain tools."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from media2text.agent.hermes_state import SessionDB
from media2text.agent.memory_store import (
    MemorySafetyError,
    MemoryStore,
    MemoryTarget,
    read_file_for_profile,
    write_file_for_profile,
)
from media2text.agent.profile_resolver import AgentProfileContext, resolve_profile
from media2text.agent.skill_manage import SkillManageError, handle_skill_manage
from media2text.agent.skill_usage import record_view
from media2text.agent.skills_index import handle_skill_view, handle_skills_list
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.agent.tools.registry import get_tool


class AgentToolError(Exception):
    pass


def _parse_args(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = raw.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentToolError(f"invalid tool arguments JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentToolError("tool arguments must be a JSON object")
    return data


def handle_function_call(
    name: str,
    arguments: str | dict[str, Any] | None,
    ctx: ToolContext,
) -> dict[str, Any]:
    """Execute one tool; returns ToolResultPayload-shaped dict."""
    tool = get_tool(name)
    if tool is None:
        return {
            "ok": False,
            "error": {"code": "UNKNOWN_TOOL", "message": f"unknown tool: {name}"},
        }
    try:
        params = _parse_args(arguments)
        if ctx.allowed_tools is not None and name not in ctx.allowed_tools:
            return {
                "ok": False,
                "error": {
                    "code": "TOOL_DENIED",
                    "message": f"tool not allowed in review context: {name}",
                },
            }
        if tool.kind == "hermes" and name == "memory":
            return _handle_memory(params, ctx)
        if tool.kind == "hermes" and name == "session_search":
            return _handle_session_search(params, ctx)
        if tool.kind == "hermes" and name == "skills_list":
            profile = ctx.profile or resolve_profile(creator_id=ctx.creator_id, cfg=ctx.cfg)
            return handle_skills_list(profile)
        if tool.kind == "hermes" and name == "skill_view":
            profile = ctx.profile or resolve_profile(creator_id=ctx.creator_id, cfg=ctx.cfg)
            result = handle_skill_view(params, profile_ctx=profile)
            if result.get("ok") and isinstance(profile, AgentProfileContext):
                skill_name = str(params.get("name") or "").strip()
                if skill_name:
                    record_view(profile, skill_name)
            return result
        if tool.kind == "hermes" and name == "skill_manage":
            profile = _active_profile(ctx)
            try:
                return handle_skill_manage(params, profile)
            except SkillManageError as exc:
                return {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        result = tool.handler(ctx, **params)
    except AgentToolError as exc:
        return {"ok": False, "error": {"code": "INVALID_ARGS", "message": str(exc)}}
    except MemorySafetyError as exc:
        return {"ok": False, "error": {"code": "CONTENT_BLOCKED", "message": str(exc)}}
    except ValueError as exc:
        return {"ok": False, "error": {"code": "INVALID_ARGS", "message": str(exc)}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"code": "TOOL_ERROR", "message": str(exc)}}

    if isinstance(result, dict) and "ok" in result:
        if result.get("ok"):
            return {"ok": True, "data": result.get("data", result)}
        err = result.get("error")
        if isinstance(err, dict):
            return {"ok": False, "error": err}
        return {
            "ok": False,
            "error": {"code": "TOOL_FAILED", "message": str(result.get("error", result))},
        }
    return {"ok": True, "data": result}


def _resolve_target(params: dict[str, Any]) -> MemoryTarget:
    raw = str(params.get("target") or "memory").lower()
    if raw in ("memory", "user", "soul"):
        return raw  # type: ignore[return-value]
    raise AgentToolError("target must be memory, user, or soul")


def _active_profile(ctx: ToolContext) -> AgentProfileContext:
    if isinstance(ctx.profile, AgentProfileContext):
        return ctx.profile
    return resolve_profile(creator_id=ctx.creator_id, cfg=ctx.cfg)


def _handle_memory(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    action = str(params.get("action") or "").lower()
    target = _resolve_target(params)
    profile = _active_profile(ctx)
    store = MemoryStore(ctx.cfg, profile=profile)

    if action == "read":
        content = read_file_for_profile(profile, target)
        return {"ok": True, "data": {"target": target, "content": content}}

    if action == "add":
        text = str(params.get("content") or "")
        meta = store.add(target, text)
        return {
            "ok": True,
            "data": {**meta, "content": read_file_for_profile(profile, target)},
        }

    if action == "replace":
        meta = store.replace(
            target,
            old_text=str(params.get("old_text") or ""),
            content=str(params.get("content") or ""),
        )
        return {
            "ok": True,
            "data": {**meta, "content": read_file_for_profile(profile, target)},
        }

    if action == "remove":
        meta = store.remove(target, old_text=str(params.get("old_text") or ""))
        return {
            "ok": True,
            "data": {**meta, "content": read_file_for_profile(profile, target)},
        }

    if action in ("write", "append"):
        content = params.get("content")
        if content is None:
            content = params.get("value")
        if content is None and params.get("key"):
            key = str(params.get("key"))
            val = str(params.get("value") or "")
            content = f"- {key}: {val}\n"
        text = str(content or "")
        mode = "append" if action == "append" else "replace"
        meta = write_file_for_profile(ctx.cfg, profile, target, text, mode=mode)
        return {
            "ok": True,
            "data": {
                **meta,
                "content": read_file_for_profile(profile, target),
                "deprecated": True,
            },
        }

    raise AgentToolError("action must be read, add, replace, remove, write, or append")


def _handle_session_search(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        raise AgentToolError("query is required")

    limit_raw = params.get("limit")
    if limit_raw is None:
        limit = ctx.cfg.desktop.agent.session_search_default_limit
    else:
        limit = int(limit_raw)

    session_id = params.get("session_id") or ctx.session_id
    creator_id = params.get("creator_id")
    if creator_id is None and ctx.creator_id:
        creator_id = ctx.creator_id

    db = SessionDB(ctx.conn)
    hits = db.search_messages(
        query,
        session_id=session_id,
        creator_id=creator_id,
        limit=max(1, min(limit, 50)),
    )
    return {
        "ok": True,
        "data": {
            "query": query,
            "results": [asdict(h) for h in hits],
        },
    }


def reset_memory_store() -> None:
    """Test helper — no-op for file-backed memory."""
