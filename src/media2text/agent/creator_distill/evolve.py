"""CreatorAgentEvolve worker (Hermes §24.4.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import structlog

from media2text.agent.creator_distill.atomic import atomic_write_text
from media2text.agent.creator_distill.evolve_log import append_evolve_log
from media2text.agent.creator_distill.evolve_patch import (
    apply_memory_patch,
    apply_skill_patch,
    build_heuristic_patch,
    sections_patched,
)
from media2text.agent.creator_distill.locks import creator_distill_lock
from media2text.agent.creator_distill.source_content import resolve_source_content
from media2text.agent.creator_distill.state_cache import refresh_distill_state_cache
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo

log = structlog.get_logger()


def _source_ids(profile_yaml: dict[str, Any]) -> list[str]:
    distill = profile_yaml.get("distill") or {}
    raw = distill.get("source_session_ids") or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if x]


def _skill_md_path(profile_dir: Path, profile_yaml: dict[str, Any]) -> Path | None:
    distill = profile_yaml.get("distill") or {}
    slug = distill.get("skill_slug")
    if slug:
        p = profile_dir / "skills" / str(slug) / "SKILL.md"
        if p.is_file():
            return p
    defaults = profile_yaml.get("default_skills") or []
    for name in defaults:
        p = profile_dir / "skills" / str(name) / "SKILL.md"
        if p.is_file():
            return p
        p = profile_dir / "skills" / f"{name}" / "SKILL.md"
        if p.is_file():
            return p
    skills_dir = profile_dir / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            return skill_md
    return None


def run_evolve_job(
    cfg: AppConfig,
    conn,
    *,
    job_id: str,
    patch_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    jobs = CreatorAgentJobRepo(conn)
    job = jobs.get(job_id)
    if not job or job.kind != "evolve":
        return {"ok": False, "error": "job_not_found"}
    if not job.source_id:
        jobs.mark_failed(job_id, error="missing_source_id")
        return {"ok": False, "error": "missing_source_id"}

    creator = CreatorRepo(conn).get(job.creator_id)
    if not creator:
        jobs.mark_failed(job_id, error="creator_not_found")
        return {"ok": False, "error": "creator_not_found"}

    lock = creator_distill_lock(job.creator_id)
    if not lock.acquire(blocking=False):
        return {"ok": False, "error": "distill_busy"}

    try:
        from media2text.agent.profile_resolver import resolve_profile, save_profile_yaml

        profile = resolve_profile(creator_id=job.creator_id, cfg=cfg)
        profile_dir = profile.memory_paths.profile_dir
        source_id = job.source_id

        known = _source_ids(profile.profile_yaml)
        if source_id in known:
            jobs.mark_done(job_id, payload={"skipped": True, "reason": "already_evolved"})
            return {"ok": True, "skipped": True, "source_id": source_id}

        ws = cfg.ensure_workspace()
        content = resolve_source_content(
            workspace=ws,
            sec_uid=creator.sec_uid,
            source_id=source_id,
            conn=conn,
        )
        if content is None:
            jobs.mark_failed(job_id, error="source_content_not_found")
            return {"ok": False, "error": "source_content_not_found"}

        skill_path = _skill_md_path(profile_dir, profile.profile_yaml)
        if skill_path is None:
            jobs.mark_failed(job_id, error="skill_not_bootstrapped")
            return {"ok": False, "error": "skill_not_bootstrapped"}

        memory_path = profile.memory_paths.memory
        skill_md = skill_path.read_text(encoding="utf-8")
        memory_md = ""
        if memory_path.is_file():
            memory_md = memory_path.read_text(encoding="utf-8")

        if patch_fn is not None:
            patch = patch_fn(
                cfg,
                source_id=source_id,
                summary_text=content.text,
                skill_md=skill_md,
                memory_md=memory_md,
            )
        else:
            patch = build_heuristic_patch(source_id=source_id, summary_text=content.text)

        new_skill = apply_skill_patch(skill_md, patch)
        max_memory = cfg.memory.max_chars
        overrides = profile.profile_yaml.get("memory")
        if isinstance(overrides, dict):
            raw = overrides.get("memory_char_limit")
            if isinstance(raw, int) and raw > 0:
                max_memory = raw
        new_memory = apply_memory_patch(
            memory_md,
            patch,
            source_id=source_id,
            max_chars=max_memory,
        )

        atomic_write_text(skill_path, new_skill)
        atomic_write_text(memory_path, new_memory)

        patched = sections_patched(patch)
        append_evolve_log(
            profile_dir,
            {
                "kind": "evolve",
                "source_id": source_id,
                "trigger": job.trigger,
                "sections_patched": patched,
            },
        )

        distill = dict(profile.profile_yaml.get("distill") or {})
        ids = list(known)
        if source_id not in ids:
            ids.append(source_id)
        distill["source_session_ids"] = ids
        distill["last_evolve_at"] = datetime.now(timezone.utc).isoformat()
        save_profile_yaml(profile, {"distill": distill})

        jobs.mark_done(
            job_id,
            payload={"source_id": source_id, "sections_patched": patched},
        )
        refresh_distill_state_cache(
            profile_dir,
            creator_id=job.creator_id,
            latest_job=jobs.get(job_id),
            extra={"last_evolve_at": distill["last_evolve_at"]},
        )
        log.info(
            "creator_evolve_done",
            creator_id=job.creator_id,
            source_id=source_id,
            sections=patched,
        )
        return {"ok": True, "source_id": source_id, "sections_patched": patched}
    except Exception as exc:  # noqa: BLE001
        log.exception("creator_evolve_failed", job_id=job_id, error=str(exc))
        jobs.mark_failed(job_id, error=str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        lock.release()
