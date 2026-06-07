"""Agent tool registry and OpenAI function schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from media2text.agent.tools import m2t_handlers
from media2text.agent.tools import terminal_handlers
from media2text.agent.tools.delegate import delegate_task

ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    kind: str = "m2t"


def _obj(**props: Any) -> dict[str, Any]:
    return {"type": "object", "properties": props, "additionalProperties": False}


def _optional_string(desc: str) -> dict[str, Any]:
    return {"type": "string", "description": desc}


def _optional_bool(desc: str) -> dict[str, Any]:
    return {"type": "boolean", "description": desc}


def _optional_number(desc: str) -> dict[str, Any]:
    return {"type": "number", "description": desc}


M2T_TOOLS: list[ToolDef] = [
    ToolDef(
        name="m2t_get_live_status",
        description="查询直播/录制/后处理队列状态",
        parameters=_obj(creator_id=_optional_string("博主 id，默认当前上下文")),
        handler=m2t_handlers.m2t_get_live_status,
    ),
    ToolDef(
        name="m2t_list_creators",
        description="列出已登记或监控中的博主",
        parameters=_obj(all=_optional_bool("true=全部，false=仅监控")),
        handler=m2t_handlers.m2t_list_creators,
    ),
    ToolDef(
        name="m2t_get_creator",
        description="获取博主详情",
        parameters={"type": "object", "properties": {"creator_id": {"type": "string"}}, "required": ["creator_id"]},
        handler=m2t_handlers.m2t_get_creator,
    ),
    ToolDef(
        name="m2t_start_recording",
        description="对博主开始手动录制",
        parameters=_obj(creator_id=_optional_string("博主 id")),
        handler=m2t_handlers.m2t_start_recording,
    ),
    ToolDef(
        name="m2t_stop_recording",
        description="停止博主当前录制",
        parameters=_obj(creator_id=_optional_string("博主 id")),
        handler=m2t_handlers.m2t_stop_recording,
    ),
    ToolDef(
        name="m2t_daemon_start",
        description="启动 monitor watch 守护进程",
        parameters={"type": "object", "properties": {}},
        handler=m2t_handlers.m2t_daemon_start,
    ),
    ToolDef(
        name="m2t_daemon_stop",
        description="停止 monitor watch 守护进程",
        parameters={"type": "object", "properties": {}},
        handler=m2t_handlers.m2t_daemon_stop,
    ),
    ToolDef(
        name="m2t_post_process_run",
        description="消化直播后处理队列",
        parameters=_obj(limit=_optional_number("最多处理条数，默认 10")),
        handler=m2t_handlers.m2t_post_process_run,
    ),
    ToolDef(
        name="m2t_pipeline_run",
        description="异步入队博主作品 sync+download+transcribe 流水线",
        parameters=_obj(creator_id=_optional_string("博主 id")),
        handler=m2t_handlers.m2t_pipeline_run,
    ),
    ToolDef(
        name="m2t_read_transcript",
        description="读取场次转写",
        parameters={
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "live session id"}},
            "required": ["session_id"],
        },
        handler=m2t_handlers.m2t_read_transcript,
    ),
    ToolDef(
        name="m2t_read_summary",
        description="读取场次摘要 markdown",
        parameters={
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "live session id"}},
            "required": ["session_id"],
        },
        handler=m2t_handlers.m2t_read_summary,
    ),
    ToolDef(
        name="m2t_read_manifest",
        description="读取博主 agent-manifest.json",
        parameters=_obj(creator_id=_optional_string("博主 id")),
        handler=m2t_handlers.m2t_read_manifest,
    ),
    ToolDef(
        name="m2t_list_sessions",
        description="列出博主历史直播场次",
        parameters=_obj(
            creator_id=_optional_string("博主 id"),
            limit=_optional_number("默认 20"),
        ),
        handler=m2t_handlers.m2t_list_sessions,
    ),
]

TERMINAL_TOOLS: list[ToolDef] = [
    ToolDef(
        name="read_file",
        description="Read a UTF-8 file under the sandbox cwd",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        handler=terminal_handlers.read_file,
        kind="hermes",
    ),
    ToolDef(
        name="search_files",
        description="Glob files under sandbox cwd",
        parameters={
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
        },
        handler=terminal_handlers.search_files,
        kind="hermes",
    ),
    ToolDef(
        name="patch",
        description="Replace first occurrence of old_string in a file",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=terminal_handlers.patch,
        kind="hermes",
    ),
    ToolDef(
        name="terminal",
        description="Run a shell command in sandbox cwd (local backend)",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        handler=terminal_handlers.terminal,
        kind="hermes",
    ),
]

DELEGATION_TOOLS: list[ToolDef] = [
    ToolDef(
        name="delegate_task",
        description="Run a synchronous sub-agent on the same creator profile",
        parameters={
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
        handler=delegate_task,
        kind="hermes",
    ),
]

HERMES_STUB_TOOLS: list[ToolDef] = [
    ToolDef(
        name="memory",
        description="Read or write curated MEMORY.md / USER.md in workspace .agent/",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "add", "replace", "remove", "write", "append"],
                },
                "target": {"type": "string", "enum": ["memory", "user", "soul"]},
                "content": {"type": "string"},
                "old_text": {"type": "string"},
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["action"],
        },
        handler=lambda ctx, **params: {"ok": True, "stub": "memory", **params},
        kind="hermes",
    ),
    ToolDef(
        name="session_search",
        description="FTS search across prior session messages",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "session_id": {"type": "string"},
                "creator_id": {"type": "string"},
            },
            "required": ["query"],
        },
        handler=lambda ctx, **params: {
            "ok": True,
            "stub": "session_search",
            "results": [],
            **params,
        },
        kind="hermes",
    ),
    ToolDef(
        name="skills_list",
        description="List available skills (Level 0: name + description only)",
        parameters={"type": "object", "properties": {}},
        handler=lambda _ctx, **_params: {"ok": False, "error": "use model_tools dispatch"},
        kind="hermes",
    ),
    ToolDef(
        name="skill_view",
        description="Load full SKILL.md or a references/ file on demand",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill slug, e.g. media2text"},
                "path": {
                    "type": "string",
                    "description": "Optional path under references/, e.g. cli-cheatsheet.md",
                },
            },
            "required": ["name"],
        },
        handler=lambda _ctx, **_params: {"ok": False, "error": "use model_tools dispatch"},
        kind="hermes",
    ),
]

ALL_TOOLS: dict[str, ToolDef] = {
    t.name: t for t in M2T_TOOLS + TERMINAL_TOOLS + DELEGATION_TOOLS + HERMES_STUB_TOOLS
}


def get_tool(name: str) -> ToolDef | None:
    return ALL_TOOLS.get(name)


def openai_tools(tool_names: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in tool_names:
        tool = ALL_TOOLS.get(name)
        if not tool:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
        )
    return out
