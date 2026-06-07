"""Context compression — preflight trim and post-turn fork."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from media2text.agent.auxiliary_client import summarize_compression
from media2text.agent.hermes_state import MessageRow, SessionDB
from media2text.core.config import AppConfig


@dataclass(frozen=True)
class CompressionPlan:
    summary_text: str
    protected_rows: list[Any]
    compressed_count: int


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough char/4 token estimate for compression thresholds."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += len(content)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            total += len(json.dumps(tool_calls, ensure_ascii=False))
    return max(1, total // 4)


def context_window_tokens(cfg: AppConfig) -> int:
    return max(1000, cfg.desktop.chat.max_context_chars // 4)


def preflight_trim_messages(
    messages: list[dict[str, Any]],
    *,
    max_tool_chars: int,
) -> list[dict[str, Any]]:
    """Light trim of tool outputs when approaching preflight threshold."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "tool":
            out.append(msg)
            continue
        content = msg.get("content") or ""
        if isinstance(content, str) and len(content) > max_tool_chars:
            trimmed = content[: max_tool_chars - 24] + "\n…[preflight-trimmed]"
            out.append({**msg, "content": trimmed})
        else:
            out.append(msg)
    return out


def build_compression_plan(
    db: SessionDB,
    session_id: str,
    cfg: AppConfig,
) -> CompressionPlan | None:
    comp = cfg.compression
    if not comp.enabled:
        return None

    rows = list(
        db.conn.execute(
            """
            SELECT * FROM messages
            WHERE session_id = ? AND message_kind = 'normal'
            ORDER BY seq
            """,
            (session_id,),
        ).fetchall()
    )
    protect = comp.protect_last_n
    if len(rows) <= protect + 1:
        return None

    middle = rows[:-protect]
    protected = rows[-protect:]
    if not middle:
        return None

    lines: list[str] = []
    for row in middle:
        role = row["role"]
        content = (row["content"] or "")[:500]
        if row["tool_name"]:
            lines.append(f"[{role}/{row['tool_name']}] {content}")
        else:
            lines.append(f"[{role}] {content}")

    summary = summarize_compression(cfg, messages_text="\n".join(lines), reason="compression")
    return CompressionPlan(
        summary_text=summary,
        protected_rows=protected,
        compressed_count=len(middle),
    )


def apply_fork_compression(
    db: SessionDB,
    *,
    display_thread_id: str,
    parent_session_id: str,
    plan: CompressionPlan,
    cfg: AppConfig,
) -> str:
    """Fork session with compression_summary + protected tail."""
    child_id = db.fork_session(parent_session_id, reason="compression")

    db.append_message(
        child_id,
        MessageRow(
            role="assistant",
            content=plan.summary_text,
            message_kind="compression_summary",
        ),
    )

    for row in plan.protected_rows:
        db.append_message(
            child_id,
            MessageRow(
                role=row["role"],
                content=row["content"],
                tool_call_id=row["tool_call_id"],
                tool_name=row["tool_name"],
                tool_calls_json=row["tool_calls_json"],
                thinking_text=row["thinking_text"],
                message_kind=row["message_kind"] or "normal",
            ),
        )

    tokens = estimate_tokens(db.get_messages_as_conversation(child_id))
    db.update_token_estimate(child_id, tokens)
    db.copy_agent_state(parent_session_id, child_id)
    return child_id


def maybe_preflight(
    messages: list[dict[str, Any]],
    cfg: AppConfig,
) -> list[dict[str, Any]]:
    comp = cfg.compression
    if not comp.enabled:
        return messages
    window = context_window_tokens(cfg)
    if estimate_tokens(messages) <= int(comp.preflight_ratio * window):
        return messages
    trim_limit = max(2000, cfg.desktop.agent.max_tool_output_chars // 2)
    return preflight_trim_messages(messages, max_tool_chars=trim_limit)


def maybe_post_turn_compress(
    db: SessionDB,
    *,
    display_thread_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
    cfg: AppConfig,
) -> str:
    """Post-turn hard compression; returns active session_id (may fork)."""
    comp = cfg.compression
    if not comp.enabled:
        db.update_token_estimate(session_id, estimate_tokens(messages))
        return session_id

    window = context_window_tokens(cfg)
    tokens = estimate_tokens(messages)
    db.update_token_estimate(session_id, tokens)

    if tokens <= int(comp.auto_ratio * window):
        return session_id

    plan = build_compression_plan(db, session_id, cfg)
    if plan is None:
        return session_id

    return apply_fork_compression(
        db,
        display_thread_id=display_thread_id,
        parent_session_id=session_id,
        plan=plan,
        cfg=cfg,
    )
