"""Agent profile resolution — workspace vs creator dual-track (Hermes §24.1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from media2text.agent.skills_index import default_skills_root
from media2text.agent.tools.toolsets import DEFAULT_TOOLSET
from media2text.core.config import AppConfig

_PROFILE_FILENAME = "profile.yaml"


@dataclass(frozen=True)
class MemoryPaths:
    profile_dir: Path
    memory: Path
    user: Path
    soul: Path


@dataclass(frozen=True)
class AgentProfileContext:
    profile_id: str
    creator_id: str | None
    memory_paths: MemoryPaths
    profile_yaml: dict[str, Any]
    enabled_toolsets: list[str]
    disabled_tools: frozenset[str]
    default_skills: list[str]
    skills_roots: list[Path]
    terminal_cwd: Path


def _default_profile_yaml(*, display_name: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "version": 1,
        "enabled_toolsets": [DEFAULT_TOOLSET],
        "disabled_tools": [],
        "default_skills": [],
    }
    if display_name:
        data["display_name"] = display_name
    return data


def _load_profile_yaml(path: Path, *, display_name: str | None = None) -> dict[str, Any]:
    defaults = _default_profile_yaml(display_name=display_name)
    if not path.is_file():
        return defaults
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    merged = {**defaults, **raw}
    if not merged.get("enabled_toolsets"):
        merged["enabled_toolsets"] = [DEFAULT_TOOLSET]
    if merged.get("disabled_tools") is None:
        merged["disabled_tools"] = []
    if merged.get("default_skills") is None:
        merged["default_skills"] = []
    return merged


def _write_profile_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _ensure_workspace_profile(cfg: AppConfig) -> tuple[Path, dict[str, Any]]:
    profile_dir = cfg.ensure_workspace() / ".agent"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "skills").mkdir(exist_ok=True)
    yaml_path = profile_dir / _PROFILE_FILENAME
    if not yaml_path.is_file():
        _write_profile_yaml(yaml_path, _default_profile_yaml())
    profile_yaml = _load_profile_yaml(yaml_path)
    return profile_dir, profile_yaml


def _ensure_creator_profile(
    cfg: AppConfig,
    *,
    creator_id: str,
    sec_uid: str,
    display_name: str | None,
) -> tuple[Path, dict[str, Any]]:
    profile_dir = cfg.ensure_workspace() / "creators" / sec_uid / ".agent"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "skills").mkdir(exist_ok=True)
    yaml_path = profile_dir / _PROFILE_FILENAME
    if not yaml_path.is_file():
        _write_profile_yaml(
            yaml_path,
            _default_profile_yaml(display_name=display_name),
        )
    profile_yaml = _load_profile_yaml(yaml_path, display_name=display_name)
    if display_name and not profile_yaml.get("display_name"):
        profile_yaml = {**profile_yaml, "display_name": display_name}
    return profile_dir, profile_yaml


def _memory_paths(profile_dir: Path) -> MemoryPaths:
    return MemoryPaths(
        profile_dir=profile_dir,
        memory=profile_dir / "MEMORY.md",
        user=profile_dir / "USER.md",
        soul=profile_dir / "SOUL.md",
    )


def _parse_tool_config(profile_yaml: dict[str, Any]) -> tuple[list[str], frozenset[str]]:
    enabled = profile_yaml.get("enabled_toolsets") or [DEFAULT_TOOLSET]
    if not isinstance(enabled, list):
        enabled = [DEFAULT_TOOLSET]
    enabled_toolsets = [str(x) for x in enabled if x]
    if not enabled_toolsets:
        enabled_toolsets = [DEFAULT_TOOLSET]

    disabled_raw = profile_yaml.get("disabled_tools") or []
    disabled_tools: set[str] = set()
    if isinstance(disabled_raw, list):
        disabled_tools = {str(x) for x in disabled_raw if x}
    return enabled_toolsets, frozenset(disabled_tools)


def _default_skills(profile_yaml: dict[str, Any]) -> list[str]:
    raw = profile_yaml.get("default_skills") or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if x]


def resolve_profile(*, creator_id: str | None, cfg: AppConfig) -> AgentProfileContext:
    """Resolve active profile for a thread scope (workspace or creator)."""
    global_root = default_skills_root()

    if creator_id is None:
        profile_dir, profile_yaml = _ensure_workspace_profile(cfg)
        memory_paths = _memory_paths(profile_dir)
        enabled_toolsets, disabled_tools = _parse_tool_config(profile_yaml)
        skills_roots = [global_root, profile_dir / "skills"]
        return AgentProfileContext(
            profile_id="workspace",
            creator_id=None,
            memory_paths=memory_paths,
            profile_yaml=profile_yaml,
            enabled_toolsets=enabled_toolsets,
            disabled_tools=disabled_tools,
            default_skills=_default_skills(profile_yaml),
            skills_roots=skills_roots,
            terminal_cwd=cfg.ensure_workspace(),
        )

    from media2text.core.workspace import open_db
    from media2text.core.storage.repos import CreatorRepo

    conn = open_db(cfg)
    try:
        row = CreatorRepo(conn).get(creator_id)
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"creator not found: {creator_id}")

    profile_dir, profile_yaml = _ensure_creator_profile(
        cfg,
        creator_id=creator_id,
        sec_uid=row.sec_uid,
        display_name=row.display_name,
    )
    memory_paths = _memory_paths(profile_dir)
    enabled_toolsets, disabled_tools = _parse_tool_config(profile_yaml)
    creator_skills = profile_dir / "skills"
    skills_roots = [global_root, creator_skills]
    terminal_cwd = cfg.ensure_workspace() / "creators" / row.sec_uid

    return AgentProfileContext(
        profile_id=row.sec_uid,
        creator_id=creator_id,
        memory_paths=memory_paths,
        profile_yaml=profile_yaml,
        enabled_toolsets=enabled_toolsets,
        disabled_tools=disabled_tools,
        default_skills=_default_skills(profile_yaml),
        skills_roots=skills_roots,
        terminal_cwd=terminal_cwd,
    )


def save_profile_yaml(profile: AgentProfileContext, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge *updates* into on-disk profile.yaml and return the merged dict."""
    merged = {**profile.profile_yaml, **updates}
    yaml_path = profile.memory_paths.profile_dir / _PROFILE_FILENAME
    _write_profile_yaml(yaml_path, merged)
    return merged
