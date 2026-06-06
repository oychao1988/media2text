"""Auto-generate agent thread titles from conversation content."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from media2text.agent.runtime_provider import build_openai_client, resolve_model
from media2text.core.config import AppConfig

if TYPE_CHECKING:
    from media2text.agent.hermes_state import SessionDB
    from media2text.agent.runtime_provider import ChatClient

_PLACEHOLDER_TITLES = frozenset(
    {
        "",
        "agent",
        "全局 agent",
        "新对话",
    }
)


def is_placeholder_title(title: str | None) -> bool:
    if title is None:
        return True
    normalized = title.strip().casefold()
    if not normalized:
        return True
    return normalized in _PLACEHOLDER_TITLES


def _clean_generated_title(raw: str) -> str:
    title = raw.strip().strip('"\'「」《》[]')
    title = title.splitlines()[0].strip()
    title = re.sub(r"^(标题|会话标题|topic)\s*[:：]\s*", "", title, flags=re.I)
    title = title.strip()
    if len(title) > 40:
        title = title[:40].rstrip() + "…"
    return title


def fallback_title(user_text: str) -> str:
    line = user_text.strip().splitlines()[0].strip()
    if not line:
        return "新对话"
    if len(line) > 24:
        return line[:24].rstrip() + "…"
    return line


def suggest_thread_title(
    cfg: AppConfig,
    *,
    user_text: str,
    assistant_text: str,
) -> str:
    user_snip = user_text.strip()[:500]
    assistant_snip = assistant_text.strip()[:800]
    if not user_snip:
        return fallback_title(user_text)

    prompt = (
        "根据下面这段 Agent 对话，生成一个简短的中文会话标题。\n"
        "要求：6–18 字；概括用户意图；不要引号、标点或「标题：」前缀；只输出标题本身。\n\n"
        f"用户：{user_snip}\n"
        f"助手：{assistant_snip or '（无回复）'}"
    )

    try:
        client = build_openai_client(cfg)
        model = resolve_model(cfg, None)
        completion = client.complete(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            model=model,
        )
        title = _clean_generated_title(completion.content or "")
        if len(title) >= 2:
            return title
    except Exception:  # noqa: BLE001
        pass

    return fallback_title(user_text)


def maybe_auto_title_thread(
    db: SessionDB,
    cfg: AppConfig,
    display_thread_id: str,
    *,
    user_text: str,
    assistant_text: str,
) -> str | None:
    """Rename thread when title is still a placeholder. Returns new title or None."""
    row = db.get_thread_by_display_id(display_thread_id)
    if row is None or not is_placeholder_title(row["title"]):
        return None

    assistant = assistant_text.strip()
    if not user_text.strip() or not assistant:
        return None

    title = suggest_thread_title(cfg, user_text=user_text, assistant_text=assistant)
    if not title:
        return None
    if title.casefold() in _PLACEHOLDER_TITLES:
        title = fallback_title(user_text)

    db.update_session(display_thread_id, title=title)
    return title
