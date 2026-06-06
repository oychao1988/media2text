"""delegate_task — synchronous sub-agent (Hermes §24.2.4)."""

from __future__ import annotations

from typing import Any

from media2text.agent.hermes_state import SessionDB
from media2text.agent.tools.m2t_handlers import ToolContext, _err, _ok


def delegate_task(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    task = str(params.get("task") or params.get("prompt") or "").strip()
    if not task:
        return _err("MISSING_TASK", "task required")
    if ctx.display_thread_id is None:
        return _err("NO_THREAD", "delegate requires active thread context")

    db = SessionDB(ctx.conn)

    profile = ctx.profile
    if profile is None:
        from media2text.agent.profile_resolver import resolve_profile

        profile = resolve_profile(creator_id=ctx.creator_id, cfg=ctx.cfg)

    from media2text.agent.ai_agent import AIAgent
    from media2text.agent.tools.toolsets import resolve_tool_names

    allowed = resolve_tool_names(profile, ctx.cfg)
    child = AIAgent(db, ctx.cfg, supervisor=ctx.supervisor)
    summary = child.run_conversation(
        display_thread_id=ctx.display_thread_id,
        user_text=f"[delegate_task]\n{task}",
    )
    return _ok(
        {
            "summary": summary,
            "creator_id": ctx.creator_id,
            "allowed_tools": allowed,
        }
    )
