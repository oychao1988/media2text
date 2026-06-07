"""Hermes skill_manage tool — create/patch/edit/delete skill files (M7b)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from media2text.agent.profile_resolver import AgentProfileContext
from media2text.agent.skill_provenance import BACKGROUND_REVIEW, get_current_write_origin
from media2text.agent.skill_usage import is_pinned, mark_agent_created, record_patch
from media2text.agent.skills_index import _find_skill, default_skills_root, resolve_skills_roots

_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*?)*$")
_PROTECTED_ERR = "PROTECTED_SKILL"


class SkillManageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _profile_skills_root(profile: AgentProfileContext) -> Path:
    for root in reversed(resolve_skills_roots(profile)):
        if root.resolve() != default_skills_root().resolve():
            return root
    root = profile.memory_paths.profile_dir / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_name(name: str) -> str:
    slug = name.strip().strip("/")
    if not slug or not _KEBAB_RE.match(slug):
        raise SkillManageError("INVALID_NAME", "skill name must be kebab-case")
    if ".." in slug.split("/"):
        raise SkillManageError("INVALID_NAME", "path traversal not allowed")
    return slug


def _is_bundled_path(path: Path) -> bool:
    bundled = default_skills_root().resolve()
    try:
        path.resolve().relative_to(bundled)
        return True
    except ValueError:
        return False


def _is_distill_skill(name: str, profile: AgentProfileContext) -> bool:
    distill = profile.profile_yaml.get("distill") or {}
    slug = distill.get("skill_slug")
    if isinstance(slug, str) and slug:
        return name == slug or name.endswith("-perspective")
    return name.endswith("-perspective")


def _read_frontmatter(skill_md: Path) -> tuple[dict[str, Any], str]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    body = parts[2]
    if body.startswith("\n"):
        body = body[1:]
    return meta, body


def _write_skill_md(skill_md: Path, meta: dict[str, Any], body: str) -> None:
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    skill_md.write_text(f"---\n{front}\n---\n{body}", encoding="utf-8")


def _guard_mutate(name: str, profile: AgentProfileContext, *, action: str) -> Path:
    slug = _validate_name(name)
    skill = _find_skill(slug, profile)
    if skill and _is_bundled_path(skill.skill_md_path):
        raise SkillManageError(_PROTECTED_ERR, "bundled skills are read-only")

    root = _profile_skills_root(profile)
    skill_dir = (root / slug).resolve()
    if not str(skill_dir).startswith(str(root.resolve())):
        raise SkillManageError("INVALID_NAME", "path traversal not allowed")
    skill_md = skill_dir / "SKILL.md"

    if action == "delete":
        if _is_distill_skill(slug, profile) or is_pinned(profile, slug):
            raise SkillManageError(_PROTECTED_ERR, "pinned or distill skills cannot be deleted")
    return skill_md


def handle_skill_manage(params: dict[str, Any], profile: AgentProfileContext) -> dict[str, Any]:
    action = str(params.get("action") or "").lower()
    name = str(params.get("name") or params.get("skill") or "").strip()
    if not name and action != "create":
        raise SkillManageError("INVALID_ARGS", "name is required")

    if action == "create":
        slug = _validate_name(str(params.get("name") or ""))
        content = str(params.get("content") or params.get("body") or "")
        description = str(params.get("description") or "Agent-created skill")
        root = _profile_skills_root(profile)
        skill_md = (root / slug / "SKILL.md").resolve()
        if skill_md.is_file():
            raise SkillManageError("ALREADY_EXISTS", f"skill already exists: {slug}")
        meta = {
            "name": slug.split("/")[-1],
            "description": description,
        }
        body = content if content.lstrip().startswith("#") else f"# {slug.split('/')[-1]}\n\n{content}"
        _write_skill_md(skill_md, meta, body)
        if get_current_write_origin() == BACKGROUND_REVIEW:
            mark_agent_created(profile, slug, write_origin=BACKGROUND_REVIEW)
        record_patch(profile, slug)
        return {"ok": True, "data": {"name": slug, "path": str(skill_md)}}

    skill_md = _guard_mutate(name, profile, action=action)
    slug = _validate_name(name)

    if action == "patch":
        old_string = str(params.get("old_string") or params.get("old_text") or "")
        new_string = str(params.get("new_string") or params.get("new_text") or params.get("content") or "")
        if not skill_md.is_file():
            raise SkillManageError("NOT_FOUND", f"skill not found: {slug}")
        text = skill_md.read_text(encoding="utf-8")
        if old_string not in text:
            raise SkillManageError("PATCH_FAILED", "old_string not found")
        if text.count(old_string) != 1:
            raise SkillManageError("PATCH_FAILED", "old_string must be unique")
        skill_md.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        record_patch(profile, slug)
        return {"ok": True, "data": {"name": slug, "patched": True}}

    if action == "edit":
        content = str(params.get("content") or params.get("body") or "")
        meta, _body = _read_frontmatter(skill_md) if skill_md.is_file() else ({}, "")
        if not meta:
            meta = {"name": slug.split("/")[-1], "description": "Agent skill"}
        body = content if content.lstrip().startswith("#") else f"# {slug.split('/')[-1]}\n\n{content}"
        _write_skill_md(skill_md, meta, body)
        record_patch(profile, slug)
        return {"ok": True, "data": {"name": slug, "edited": True}}

    if action == "delete":
        skill_dir = skill_md.parent
        if skill_dir.is_dir():
            for p in sorted(skill_dir.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink()
            skill_dir.rmdir()
        return {"ok": True, "data": {"name": slug, "deleted": True}}

    if action in ("write_file", "remove_file"):
        rel = str(params.get("path") or params.get("file") or "").strip().lstrip("/")
        if not rel or ".." in Path(rel).parts:
            raise SkillManageError("INVALID_PATH", "invalid file path")
        if _is_distill_skill(slug, profile) and rel.startswith("references/research/"):
            raise SkillManageError(_PROTECTED_ERR, "references/research is read-only for distill skills")
        skill_dir = skill_md.parent
        target = (skill_dir / rel).resolve()
        if not str(target).startswith(str(skill_dir.resolve())):
            raise SkillManageError("INVALID_PATH", "path traversal not allowed")
        if action == "write_file":
            content = str(params.get("content") or "")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            record_patch(profile, slug)
            return {"ok": True, "data": {"name": slug, "path": rel, "written": True}}
        if target.is_file():
            target.unlink()
        record_patch(profile, slug)
        return {"ok": True, "data": {"name": slug, "path": rel, "removed": True}}

    raise SkillManageError("INVALID_ARGS", f"unknown action: {action}")
