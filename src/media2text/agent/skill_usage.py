"""Per-profile skill usage telemetry (.usage.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media2text.agent.profile_resolver import AgentProfileContext
from media2text.agent.skills_index import default_skills_root, resolve_skills_roots


def _usage_path(profile: AgentProfileContext) -> Path:
    for root in reversed(resolve_skills_roots(profile)):
        if root.resolve() == default_skills_root().resolve():
            continue
        return root / ".usage.json"
    roots = resolve_skills_roots(profile)
    base = roots[-1] if roots else profile.memory_paths.profile_dir / "skills"
    base.mkdir(parents=True, exist_ok=True)
    return base / ".usage.json"


def _is_bundled_skill(profile: AgentProfileContext, name: str) -> bool:
    skill = None
    from media2text.agent.skills_index import _find_skill

    skill = _find_skill(name, profile)
    if skill is None:
        return False
    bundled = default_skills_root().resolve()
    try:
        skill.skill_md_path.resolve().relative_to(bundled)
        return True
    except ValueError:
        return False


def load_usage(profile: AgentProfileContext) -> dict[str, Any]:
    path = _usage_path(profile)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_usage(profile: AgentProfileContext, data: dict[str, Any]) -> None:
    if not data:
        return
    path = _usage_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_entry(data: dict[str, Any], name: str) -> dict[str, Any]:
    entry = data.get(name)
    if not isinstance(entry, dict):
        entry = {}
        data[name] = entry
    entry.setdefault("state", "active")
    entry.setdefault("pinned", False)
    entry.setdefault("agent_created", False)
    entry.setdefault("view_count", 0)
    entry.setdefault("use_count", 0)
    entry.setdefault("patch_count", 0)
    return entry


def record_view(profile: AgentProfileContext, name: str) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = _ensure_entry(data, name)
    entry["view_count"] = int(entry.get("view_count") or 0) + 1
    entry["last_viewed_at"] = _now_iso()
    save_usage(profile, data)


def record_use(profile: AgentProfileContext, name: str) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = _ensure_entry(data, name)
    entry["use_count"] = int(entry.get("use_count") or 0) + 1
    entry["last_used_at"] = _now_iso()
    save_usage(profile, data)


def record_patch(profile: AgentProfileContext, name: str) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = _ensure_entry(data, name)
    entry["patch_count"] = int(entry.get("patch_count") or 0) + 1
    entry["last_patched_at"] = _now_iso()
    save_usage(profile, data)


def pin(profile: AgentProfileContext, name: str, *, agent_created: bool = False) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = _ensure_entry(data, name)
    entry["pinned"] = True
    if agent_created:
        entry["agent_created"] = True
        entry["created_by"] = "agent"
    save_usage(profile, data)


def is_pinned(profile: AgentProfileContext, name: str) -> bool:
    data = load_usage(profile)
    entry = data.get(name)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("pinned"))


def unpin(profile: AgentProfileContext, name: str) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = data.get(name)
    if not isinstance(entry, dict):
        return
    entry["pinned"] = False
    save_usage(profile, data)


def is_agent_created(profile: AgentProfileContext, name: str) -> bool:
    data = load_usage(profile)
    entry = data.get(name)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("agent_created"))


def set_skill_state(profile: AgentProfileContext, name: str, state: str) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = _ensure_entry(data, name)
    entry["state"] = state
    save_usage(profile, data)


def list_curator_candidates(profile: AgentProfileContext) -> dict[str, dict[str, Any]]:
    """Usage entries eligible for curator auto transitions (agent_created, not pinned)."""
    data = load_usage(profile)
    out: dict[str, dict[str, Any]] = {}
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get("agent_created"):
            continue
        if entry.get("pinned"):
            continue
        if _is_bundled_skill(profile, name):
            continue
        out[name] = entry
    return out


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_since_activity(entry: dict[str, Any], *, now: datetime | None = None) -> float | None:
    now = now or datetime.now(timezone.utc)
    candidates = [
        _parse_iso(entry.get("last_used_at")),
        _parse_iso(entry.get("last_viewed_at")),
        _parse_iso(entry.get("last_patched_at")),
    ]
    stamps = [t for t in candidates if t is not None]
    if not stamps:
        return None
    latest = max(stamps)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return (now - latest).total_seconds() / 86400.0


def mark_agent_created(
    profile: AgentProfileContext,
    name: str,
    *,
    write_origin: str,
) -> None:
    if _is_bundled_skill(profile, name):
        return
    data = load_usage(profile)
    entry = _ensure_entry(data, name)
    entry["agent_created"] = True
    entry["created_by"] = "agent"
    entry["write_origin"] = write_origin
    save_usage(profile, data)
