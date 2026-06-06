"""Dispatch Hermes core tools vs m2t domain tools."""

from __future__ import annotations

import json
from typing import Any

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
        if tool.kind == "hermes" and name == "memory":
            return _handle_memory(params)
        result = tool.handler(ctx, **params)
    except AgentToolError as exc:
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


# Module-level stub store for M1 memory tool (per-process; M3 replaces)
_MEMORY_STORE: dict[str, str] = {}


def _handle_memory(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action")
    key = str(params.get("key") or "default")
    if action == "read":
        return {"ok": True, "data": {"key": key, "value": _MEMORY_STORE.get(key, "")}}
    if action == "write":
        value = str(params.get("value") or "")
        _MEMORY_STORE[key] = value
        return {"ok": True, "data": {"key": key, "value": value, "stored": True}}
    return {"ok": False, "error": {"code": "INVALID_ACTION", "message": "action must be read or write"}}


def reset_memory_store() -> None:
    """Test helper."""
    _MEMORY_STORE.clear()
