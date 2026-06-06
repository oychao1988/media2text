"""Enqueue bootstrap / evolve jobs."""

from __future__ import annotations

from media2text.agent.creator_distill.state_cache import refresh_distill_state_cache
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo


def enqueue_bootstrap(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    trigger: str,
    force: bool = False,
) -> str | None:
    if not CreatorRepo(conn).get(creator_id):
        return None
    jobs = CreatorAgentJobRepo(conn)
    job_id = jobs.enqueue_bootstrap(creator_id=creator_id, trigger=trigger, force=force)
    if job_id:
        latest = jobs.find_active_bootstrap(creator_id)
        try:
            from media2text.agent.profile_resolver import resolve_profile

            profile = resolve_profile(creator_id=creator_id, cfg=cfg)
            refresh_distill_state_cache(
                profile.memory_paths.profile_dir,
                creator_id=creator_id,
                latest_job=latest,
            )
        except ValueError:
            pass
    return job_id


def enqueue_evolve(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    source_id: str,
    trigger: str,
) -> str | None:
    if not CreatorRepo(conn).get(creator_id):
        return None
    jobs = CreatorAgentJobRepo(conn)
    job_id = jobs.enqueue_evolve(
        creator_id=creator_id,
        source_id=source_id,
        trigger=trigger,
    )
    if job_id:
        try:
            from media2text.agent.profile_resolver import resolve_profile

            profile = resolve_profile(creator_id=creator_id, cfg=cfg)
            refresh_distill_state_cache(
                profile.memory_paths.profile_dir,
                creator_id=creator_id,
                latest_job=jobs.get(job_id),
            )
        except ValueError:
            pass
    return job_id


def maybe_enqueue_evolve(
    cfg: AppConfig,
    conn,
    *,
    creator_id: str,
    source_id: str,
    trigger: str,
) -> str | None:
    """Enqueue evolve when trigger is listed in distill.evolve_on."""
    allowed = cfg.desktop.agent.distill.evolve_on or []
    if trigger not in allowed:
        return None
    return enqueue_evolve(
        cfg,
        conn,
        creator_id=creator_id,
        source_id=source_id,
        trigger=trigger,
    )
