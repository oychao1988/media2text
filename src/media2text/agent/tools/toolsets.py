"""Named toolsets for agent turns."""

from __future__ import annotations

from typing import TYPE_CHECKING

from media2text.agent.tools.registry import ALL_TOOLS, DELEGATION_TOOLS, M2T_TOOLS, TERMINAL_TOOLS

if TYPE_CHECKING:
    from media2text.agent.profile_resolver import AgentProfileContext
    from media2text.core.config import AppConfig

DEFAULT_TOOLSET = "m2t-core"
REVIEW_TOOLSET = "review"

_M2T_NAMES = [t.name for t in M2T_TOOLS]
_HERMES_NAMES = ["memory", "session_search", "skills_list", "skill_view", "skill_manage"]
_REVIEW_NAMES = ["memory", "skills_list", "skill_view", "skill_manage"]
_TERMINAL_NAMES = [t.name for t in TERMINAL_TOOLS]
_DELEGATION_NAMES = [t.name for t in DELEGATION_TOOLS]

TOOLSETS: dict[str, list[str]] = {
    DEFAULT_TOOLSET: _M2T_NAMES + _HERMES_NAMES,
    REVIEW_TOOLSET: _REVIEW_NAMES,
    "m2t-terminal": _TERMINAL_NAMES,
    "m2t-delegation": _DELEGATION_NAMES,
}


def tool_names_for_set(name: str = DEFAULT_TOOLSET) -> list[str]:
    return list(TOOLSETS.get(name, TOOLSETS[DEFAULT_TOOLSET]))


def resolve_tool_names(profile: AgentProfileContext, cfg: AppConfig | None = None) -> list[str]:
    """Union enabled toolsets minus disabled_tools (Hermes §24.1.4)."""
    allowed_sets: set[str] | None = None
    if cfg is not None:
        allowed_sets = set(cfg.desktop.agent.allow_toolsets or [])
    names: list[str] = []
    seen: set[str] = set()
    for toolset in profile.enabled_toolsets:
        if allowed_sets is not None and toolset not in allowed_sets:
            continue
        for name in TOOLSETS.get(toolset, []):
            if name in profile.disabled_tools or name in seen:
                continue
            if name in ALL_TOOLS:
                names.append(name)
                seen.add(name)
    if names:
        return names
    return tool_names_for_set(DEFAULT_TOOLSET)


def validate_toolset(name: str) -> bool:
    return name in TOOLSETS and all(n in ALL_TOOLS for n in TOOLSETS[name])
