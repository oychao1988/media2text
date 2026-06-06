"""Named toolsets for agent turns."""

from __future__ import annotations

from media2text.agent.tools.registry import ALL_TOOLS, M2T_TOOLS

DEFAULT_TOOLSET = "m2t-core"

_M2T_NAMES = [t.name for t in M2T_TOOLS]
_HERMES_NAMES = ["memory", "session_search", "skills_list", "skill_view"]

TOOLSETS: dict[str, list[str]] = {
    DEFAULT_TOOLSET: _M2T_NAMES + _HERMES_NAMES,
}


def tool_names_for_set(name: str = DEFAULT_TOOLSET) -> list[str]:
    return list(TOOLSETS.get(name, TOOLSETS[DEFAULT_TOOLSET]))


def validate_toolset(name: str) -> bool:
    return name in TOOLSETS and all(n in ALL_TOOLS for n in TOOLSETS[name])
