"""CreatorAgentBootstrap worker (Hermes §24.4.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import structlog
import yaml

from media2text.agent.creator_distill.atomic import atomic_write_text
from media2text.agent.creator_distill.collect import collect_corpus, corpus_plain_text
from media2text.agent.creator_distill.distill_llm import distill_bootstrap_json
from media2text.agent.creator_distill.locks import creator_distill_lock
from media2text.agent.creator_distill.render import (
    render_local_corpus_md,
    render_skill_md,
    render_soul_md,
)
from media2text.agent.creator_distill.slug import normalize_skill_slug
from media2text.agent.creator_distill.state_cache import refresh_distill_state_cache
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo

log = structlog.get_logger()


def run_bootstrap_job(
    cfg: AppConfig,
    conn,
    *,
    job_id: str,
    llm_fn: Callable[..., dict[str, Any]] | None = None,
    write_skill_fn: Callable[[Path, str], None] | None = None,
) -> dict[str, Any]:
    jobs = CreatorAgentJobRepo(conn)
    job = jobs.get(job_id)
    if not job or job.kind != "bootstrap":
        return {"ok": False, "error": "job_not_found"}

    creator = CreatorRepo(conn).get(job.creator_id)
    if not creator:
        jobs.mark_failed(job_id, error="creator_not_found")
        return {"ok": False, "error": "creator_not_found"}

    distill_cfg = cfg.desktop.agent.distill
    lock = creator_distill_lock(job.creator_id)
    if not lock.acquire(blocking=False):
        return {"ok": False, "error": "distill_busy"}

    try:
        from media2text.agent.profile_resolver import resolve_profile, save_profile_yaml

        profile = resolve_profile(creator_id=job.creator_id, cfg=cfg)
        profile_dir = profile.memory_paths.profile_dir
        ws = cfg.ensure_workspace()

        corpus = collect_corpus(
            workspace=ws,
            sec_uid=creator.sec_uid,
            display_name=creator.display_name,
            platform=creator.platform,
            profile_url=creator.profile_url,
            max_input_chars=distill_cfg.max_input_chars,
        )

        if corpus.total_chars < distill_cfg.defer_until_min_chars:
            jobs.mark_deferred(
                job_id,
                payload={
                    "total_chars": corpus.total_chars,
                    "defer_until_min_chars": distill_cfg.defer_until_min_chars,
                },
            )
            refresh_distill_state_cache(
                profile_dir,
                creator_id=job.creator_id,
                latest_job=jobs.find_active_bootstrap(job.creator_id),
                extra={"bootstrap_status": "deferred", "total_chars": corpus.total_chars},
            )
            _set_bootstrap_status(profile_dir, "deferred")
            return {
                "ok": True,
                "deferred": True,
                "total_chars": corpus.total_chars,
            }

        display = creator.display_name or creator.sec_uid
        slug = normalize_skill_slug(display, creator_id=job.creator_id)
        corpus_text = corpus_plain_text(corpus)

        if llm_fn is not None:
            distill = llm_fn(cfg, display_name=display, corpus_text=corpus_text)
        else:
            distill = distill_bootstrap_json(
                cfg, display_name=display, corpus_text=corpus_text
            )

        skill_dir = profile_dir / "skills" / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        refs_dir = skill_dir / "references" / "research"
        refs_dir.mkdir(parents=True, exist_ok=True)

        skill_md = render_skill_md(slug=slug, display_name=display, distill=distill)
        soul_md = render_soul_md(display_name=display, distill=distill)
        corpus_md = render_local_corpus_md(corpus_text)

        writer = write_skill_fn or atomic_write_text
        writer(skill_dir / "SKILL.md", skill_md)
        atomic_write_text(profile.memory_paths.soul, soul_md)
        atomic_write_text(refs_dir / "00-local-corpus.md", corpus_md)

        from media2text.agent.skill_usage import pin

        pin(profile, slug)

        skill_ref = slug
        merged_yaml = save_profile_yaml(
            profile,
            {
                "default_skills": [skill_ref],
                "distill": {
                    **(profile.profile_yaml.get("distill") or {}),
                    "last_bootstrap_at": datetime.now(timezone.utc).isoformat(),
                    "bootstrap_status": "done",
                    "skill_slug": slug,
                },
            },
        )

        jobs.mark_done(
            job_id,
            payload={
                "skill_slug": slug,
                "total_chars": corpus.total_chars,
            },
        )
        refresh_distill_state_cache(
            profile_dir,
            creator_id=job.creator_id,
            latest_job=jobs.get(job_id),
            extra={
                "bootstrap_status": "done",
                "skill_slug": slug,
                "default_skills": merged_yaml.get("default_skills"),
            },
        )
        log.info(
            "creator_bootstrap_done",
            creator_id=job.creator_id,
            skill_slug=slug,
            chars=corpus.total_chars,
        )
        return {"ok": True, "skill_slug": slug, "deferred": False}
    except Exception as exc:  # noqa: BLE001
        log.exception("creator_bootstrap_failed", job_id=job_id, error=str(exc))
        jobs.mark_failed(job_id, error=str(exc))
        try:
            from media2text.agent.profile_resolver import resolve_profile

            profile = resolve_profile(creator_id=job.creator_id, cfg=cfg)
            refresh_distill_state_cache(
                profile.memory_paths.profile_dir,
                creator_id=job.creator_id,
                latest_job=jobs.get(job_id),
                extra={"bootstrap_status": "failed"},
            )
            _set_bootstrap_status(profile.memory_paths.profile_dir, "failed")
        except ValueError:
            pass
        return {"ok": False, "error": str(exc)}
    finally:
        lock.release()


def _set_bootstrap_status(profile_dir: Path, status: str) -> None:
    yaml_path = profile_dir / "profile.yaml"
    if not yaml_path.is_file():
        return
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(data, dict):
        return
    distill = dict(data.get("distill") or {})
    distill["bootstrap_status"] = status
    data["distill"] = distill
    atomic_write_text(yaml_path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
