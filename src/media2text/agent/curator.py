"""Hermes-style skill curator — stale/archive transitions + optional LLM review (M7c)."""

from __future__ import annotations

import json
import logging
import shutil
import tarfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media2text.agent.profile_resolver import AgentProfileContext, resolve_profile
from media2text.agent.skill_usage import (
    days_since_activity,
    list_curator_candidates,
    set_skill_state,
)
from media2text.agent.skills_index import default_skills_root, resolve_skills_roots
from media2text.core.config import AppConfig

logger = logging.getLogger(__name__)

STALE_DAYS = 30
ARCHIVE_DAYS = 90
CURATOR_MAX_ITERATIONS = 8

_STATE_FILENAME = ".curator_state.json"


@dataclass
class TransitionResult:
    stale: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _global_state_path(cfg: AppConfig) -> Path:
    return cfg.ensure_workspace() / ".agent" / _STATE_FILENAME


def load_global_state(cfg: AppConfig) -> dict[str, Any]:
    path = _global_state_path(cfg)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_global_state(cfg: AppConfig, data: dict[str, Any]) -> None:
    path = _global_state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_curator_state_if_missing(cfg: AppConfig) -> None:
    state = load_global_state(cfg)
    if state.get("last_run_at"):
        return
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_global_state(cfg, {"last_run_at": now, "seeded": True})


def _profile_skills_root(profile: AgentProfileContext) -> Path:
    for root in reversed(resolve_skills_roots(profile)):
        if root.resolve() != default_skills_root().resolve():
            return root
    root = profile.memory_paths.profile_dir / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _archive_dir(profile: AgentProfileContext) -> Path:
    d = _profile_skills_root(profile) / ".archive"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_dir(profile: AgentProfileContext) -> Path:
    d = _profile_skills_root(profile) / ".curator_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_backup(profile: AgentProfileContext, *, keep: int) -> Path | None:
    skills_root = _profile_skills_root(profile)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_dir = _backup_dir(profile) / ts
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / "skills.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(skills_root.iterdir()):
            if item.name.startswith("."):
                continue
            tar.add(item, arcname=item.name)
    backups = sorted(_backup_dir(profile).iterdir(), key=lambda p: p.name)
    while len(backups) > max(1, keep):
        old = backups.pop(0)
        shutil.rmtree(old, ignore_errors=True)
    return archive_path


def list_backups(profile: AgentProfileContext) -> list[Path]:
    root = _backup_dir(profile)
    if not root.is_dir():
        return []
    return sorted(root.iterdir(), key=lambda p: p.name, reverse=True)


def rollback_backup(profile: AgentProfileContext, backup_name: str) -> Path:
    backup_path = _backup_dir(profile) / backup_name
    archive = backup_path / "skills.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(f"backup not found: {backup_name}")
    skills_root = _profile_skills_root(profile)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(skills_root)
    return skills_root


def restore_archived_skill(profile: AgentProfileContext, name: str) -> Path:
    archived = _archive_dir(profile) / name
    if not archived.is_dir():
        raise FileNotFoundError(f"archived skill not found: {name}")
    dest = _profile_skills_root(profile) / name
    if dest.exists():
        raise FileExistsError(f"skill already exists: {name}")
    shutil.move(str(archived), str(dest))
    set_skill_state(profile, name, "active")
    return dest


def phase1_auto_transitions(
    profile: AgentProfileContext,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> TransitionResult:
    result = TransitionResult()
    skills_root = _profile_skills_root(profile)
    for name, entry in list_curator_candidates(profile).items():
        idle_days = days_since_activity(entry, now=now)
        if idle_days is None:
            result.skipped.append(name)
            continue
        state = str(entry.get("state") or "active")
        skill_dir = skills_root / name
        if idle_days >= ARCHIVE_DAYS and state != "archived":
            result.archived.append(name)
            if not dry_run and skill_dir.is_dir():
                dest = _archive_dir(profile) / name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(skill_dir), str(dest))
                set_skill_state(profile, name, "archived")
            continue
        if idle_days >= STALE_DAYS and state == "active":
            result.stale.append(name)
            if not dry_run:
                set_skill_state(profile, name, "stale")
    return result


def _write_curator_report(
    profile: AgentProfileContext,
    *,
    run_id: str,
    dry_run: bool,
    transitions: TransitionResult,
    llm_result: dict[str, Any] | None,
) -> Path:
    report_dir = profile.memory_paths.profile_dir / "logs" / "curator" / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Curator run {run_id}",
        "",
        f"- dry_run: {dry_run}",
        f"- profile: {profile.profile_id}",
        "",
        "## Phase 1 — auto transitions",
        f"- stale: {', '.join(transitions.stale) or '(none)'}",
        f"- archived: {', '.join(transitions.archived) or '(none)'}",
        f"- skipped: {', '.join(transitions.skipped) or '(none)'}",
        "",
        "## Phase 2 — LLM review",
    ]
    if llm_result is None:
        lines.append("- skipped")
    else:
        lines.append(f"- result: {json.dumps(llm_result, ensure_ascii=False)}")
    path = report_dir / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_phase2_llm_review(
    cfg: AppConfig,
    profile: AgentProfileContext,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "skipped": True, "reason": "dry_run"}
    stale = [
        n
        for n, e in list_curator_candidates(profile).items()
        if str(e.get("state") or "active") == "stale"
    ]
    if not stale:
        return {"ok": True, "skipped": True, "reason": "no_stale_skills"}

    from media2text.agent.ai_agent import AIAgent
    from media2text.agent.hermes_state import SessionDB
    from media2text.agent.runtime_provider import resolve_auxiliary_slot
    from media2text.agent.skill_provenance import BACKGROUND_REVIEW, write_origin_ctx
    from media2text.core.storage.db import connect

    curator_provider, curator_model = resolve_auxiliary_slot(
        cfg.auxiliary.curator,
        cfg=cfg,
    )

    prompt = (
        "You are the skill curator. Review stale agent-created skills and improve or "
        "archive them using skill_view and skill_manage only. Stale skills: "
        + ", ".join(stale)
    )
    conn = connect(cfg.ensure_workspace() / "media2text.db")
    try:
        db = SessionDB(conn)
        sid = db.create_session(display_thread_id="curator", title="curator")
        with write_origin_ctx(BACKGROUND_REVIEW):
            agent = AIAgent(db, cfg, toolset="review", quiet=True)
            agent.run_review_conversation(
                display_thread_id="curator",
                session_id=sid,
                user_text=prompt,
                conversation_history=[],
                binding={},
                creator_id=profile.creator_id,
                provider_name=curator_provider,
                model=curator_model,
                cached_volatile=None,
                max_iterations=CURATOR_MAX_ITERATIONS,
            )
    finally:
        conn.close()
    return {"ok": True, "reviewed": stale}


def run_curator(
    cfg: AppConfig,
    *,
    dry_run: bool = False,
    profile: AgentProfileContext | None = None,
    run_llm: bool = True,
) -> dict[str, Any]:
    profile = profile or resolve_profile(creator_id=None, cfg=cfg)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report: dict[str, Any] = {"dry_run": dry_run, "profiles": [], "run_id": run_id}

    if not dry_run:
        create_backup(profile, keep=cfg.curator.backup_keep)

    transitions = phase1_auto_transitions(profile, dry_run=dry_run)
    llm_result: dict[str, Any] | None = None
    profile_report: dict[str, Any] = {
        "profile_id": profile.profile_id,
        "stale": transitions.stale,
        "archived": transitions.archived,
        "skipped": transitions.skipped,
    }
    if run_llm and cfg.curator.enabled:
        llm_result = run_phase2_llm_review(cfg, profile, dry_run=dry_run)
        profile_report["llm"] = llm_result
    report_path = _write_curator_report(
        profile,
        run_id=run_id,
        dry_run=dry_run,
        transitions=transitions,
        llm_result=llm_result,
    )
    profile_report["report_path"] = str(report_path)
    report["profiles"].append(profile_report)

    if not dry_run:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        state = load_global_state(cfg)
        state["last_run_at"] = now
        save_global_state(cfg, state)

    return report


def curator_status(cfg: AppConfig) -> dict[str, Any]:
    profile = resolve_profile(creator_id=None, cfg=cfg)
    state = load_global_state(cfg)
    candidates = list_curator_candidates(profile)
    return {
        "enabled": cfg.curator.enabled,
        "interval_hours": cfg.curator.interval_hours,
        "min_idle_hours": cfg.curator.min_idle_hours,
        "last_run_at": state.get("last_run_at"),
        "agent_created_skills": len(candidates),
        "stale_skills": sum(
            1 for e in candidates.values() if str(e.get("state") or "active") == "stale"
        ),
        "backups": [p.name for p in list_backups(profile)],
    }


def should_run_curator_idle(cfg: AppConfig, *, active_turns: int) -> bool:
    if not cfg.curator.enabled:
        return False
    if active_turns > 0:
        return False
    idle_hours = _hours_since_agent_idle(cfg)
    if idle_hours is not None and idle_hours < float(cfg.curator.min_idle_hours):
        return False
    state = load_global_state(cfg)
    last_run = state.get("last_run_at")
    if not last_run:
        seed_curator_state_if_missing(cfg)
        return False
    try:
        last_dt = datetime.fromisoformat(str(last_run).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    hours_since = (now - last_dt).total_seconds() / 3600.0
    return hours_since >= float(cfg.curator.interval_hours)


def touch_agent_activity(cfg: AppConfig) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    state = load_global_state(cfg)
    state["last_agent_activity_at"] = now
    save_global_state(cfg, state)


def _hours_since_agent_idle(cfg: AppConfig) -> float | None:
    state = load_global_state(cfg)
    raw = state.get("last_agent_activity_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


_curator_lock = threading.Lock()
_curator_running = False


def maybe_run_curator_idle(cfg: AppConfig, *, active_turns: int) -> None:
    global _curator_running
    if not should_run_curator_idle(cfg, active_turns=active_turns):
        return
    if not _curator_lock.acquire(blocking=False):
        return
    if _curator_running:
        _curator_lock.release()
        return
    _curator_running = True

    def _run() -> None:
        global _curator_running
        try:
            logger.info("curator idle tick starting")
            run_curator(cfg, dry_run=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("curator idle tick failed: %s", exc)
        finally:
            _curator_running = False
            _curator_lock.release()

    threading.Thread(target=_run, daemon=True, name="curator-idle").start()
