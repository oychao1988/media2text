"""agentskills.io progressive disclosure — Level 0 index, Level 1/2 on demand."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from media2text.core.config import _project_root

if TYPE_CHECKING:
    from media2text.agent.profile_resolver import AgentProfileContext

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    skill_md_path: Path
    base_dir: Path


def default_skills_root() -> Path:
    env = os.environ.get("M2T_SKILLS_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _project_root() / "packages" / "agent-skills"


def resolve_skills_roots(
    profile_ctx: AgentProfileContext | dict[str, Any] | None,
) -> list[Path]:
    """M4: global root; M5a merges creator ``.agent/skills/`` (later roots win)."""
    if profile_ctx is None:
        return [default_skills_root()]
    if hasattr(profile_ctx, "skills_roots"):
        return list(profile_ctx.skills_roots)  # type: ignore[union-attr]
    if profile_ctx.get("skills_roots"):
        return [Path(p).expanduser().resolve() for p in profile_ctx["skills_roots"]]
    return [default_skills_root()]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    body = text[match.end() :]
    return meta, body


def read_skill_description(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    desc = meta.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    title = re.search(r"^#\s+(.+)", body, re.MULTILINE)
    title_text = title.group(1).strip() if title else skill_md.parent.name
    first_para = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            first_para = stripped
            break
    if first_para:
        return f"{title_text} — {first_para}"
    return title_text


def _discover_skills_in_root(root: Path) -> dict[str, SkillMeta]:
    found: dict[str, SkillMeta] = {}
    if not root.is_dir():
        return found
    for skill_md in sorted(root.rglob("SKILL.md")):
        if not skill_md.is_file():
            continue
        rel = skill_md.parent.relative_to(root)
        name = rel.as_posix() if rel.parts else skill_md.parent.name
        if name in found:
            continue
        found[name] = SkillMeta(
            name=name,
            description=read_skill_description(skill_md),
            skill_md_path=skill_md.resolve(),
            base_dir=skill_md.parent.resolve(),
        )
    return found


def build_skills_index(
    profile_ctx: AgentProfileContext | dict[str, Any] | None = None,
) -> list[SkillMeta]:
    """Merge skills roots; later entries override same slug (M5a creator override)."""
    merged: dict[str, SkillMeta] = {}
    for root in resolve_skills_roots(profile_ctx):
        merged.update(_discover_skills_in_root(root))
    return sorted(merged.values(), key=lambda s: s.name)


def format_skills_index_block(skills: list[SkillMeta]) -> str:
    if not skills:
        return ""
    lines = [
        "## Skills (Level 0)",
        "Full documents load on demand via skills_list / skill_view — do not assume skill body is in context.",
    ]
    for skill in skills:
        lines.append(f"- **{skill.name}**: {skill.description}")
    return "\n".join(lines)


def _find_skill(
    name: str,
    profile_ctx: AgentProfileContext | dict[str, Any] | None,
) -> SkillMeta | None:
    slug = name.strip().strip("/")
    if not slug:
        return None
    for skill in build_skills_index(profile_ctx):
        if skill.name == slug:
            return skill
    return None


def read_skill_body(
    name: str,
    *,
    profile_ctx: AgentProfileContext | dict[str, Any] | None = None,
) -> str:
    skill = _find_skill(name, profile_ctx)
    if skill is None:
        raise ValueError(f"skill not found: {name}")
    return skill.skill_md_path.read_text(encoding="utf-8")


def read_skill_reference(
    name: str,
    path: str,
    *,
    profile_ctx: AgentProfileContext | dict[str, Any] | None = None,
) -> tuple[str, Path]:
    skill = _find_skill(name, profile_ctx)
    if skill is None:
        raise ValueError(f"skill not found: {name}")
    rel = path.strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise ValueError("invalid reference path")
    ref_root = (skill.base_dir / "references").resolve()
    target = (ref_root / rel).resolve()
    if not str(target).startswith(str(ref_root)) or not target.is_file():
        raise ValueError(f"reference not found: {path}")
    return target.read_text(encoding="utf-8"), target


def handle_skills_list(
    profile_ctx: AgentProfileContext | dict[str, Any] | None = None,
) -> dict[str, Any]:
    skills = build_skills_index(profile_ctx)
    return {
        "ok": True,
        "data": {
            "skills": [
                {"name": s.name, "description": s.description} for s in skills
            ],
        },
    }


def handle_skill_view(
    params: dict[str, Any],
    *,
    profile_ctx: AgentProfileContext | dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    ref_path = params.get("path")
    if ref_path is not None and str(ref_path).strip():
        content, resolved = read_skill_reference(name, str(ref_path), profile_ctx=profile_ctx)
        return {
            "ok": True,
            "data": {
                "name": name,
                "path": str(ref_path),
                "resolved_path": str(resolved),
                "content": content,
            },
        }
    content = read_skill_body(name, profile_ctx=profile_ctx)
    return {
        "ok": True,
        "data": {"name": name, "content": content},
    }
