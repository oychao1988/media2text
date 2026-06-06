"""Deferred bootstrap promotion (§24.4.4.1)."""

from __future__ import annotations

import structlog

from media2text.agent.creator_distill.collect import collect_corpus
from media2text.agent.creator_distill.state_cache import refresh_distill_state_cache
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo

log = structlog.get_logger()


def maybe_promote_bootstrap(cfg: AppConfig, conn, *, creator_id: str) -> bool:
    """If deferred bootstrap exists and corpus is sufficient, promote to pending."""
    jobs = CreatorAgentJobRepo(conn)
    job = jobs.find_active_bootstrap(creator_id)
    if not job or job.status != "deferred":
        return False

    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return False

    distill_cfg = cfg.desktop.agent.distill
    corpus = collect_corpus(
        workspace=cfg.ensure_workspace(),
        sec_uid=creator.sec_uid,
        display_name=creator.display_name,
        platform=creator.platform,
        profile_url=creator.profile_url,
        max_input_chars=distill_cfg.max_input_chars,
    )
    if corpus.total_chars < distill_cfg.defer_until_min_chars:
        return False

    promoted = jobs.promote_deferred(job.id)
    if promoted:
        log.info(
            "creator_bootstrap_promoted",
            creator_id=creator_id,
            total_chars=corpus.total_chars,
        )
        try:
            from media2text.agent.profile_resolver import resolve_profile

            profile = resolve_profile(creator_id=creator_id, cfg=cfg)
            refresh_distill_state_cache(
                profile.memory_paths.profile_dir,
                creator_id=creator_id,
                latest_job=jobs.find_active_bootstrap(creator_id),
                extra={"bootstrap_status": "pending", "total_chars": corpus.total_chars},
            )
        except ValueError:
            pass
    return promoted


def tick_deferred_bootstrap(cfg: AppConfig, conn, *, limit: int = 20) -> int:
    """SlowTick: scan deferred bootstrap jobs and promote when corpus is ready."""
    jobs = CreatorAgentJobRepo(conn)
    promoted = 0
    for job in jobs.list_deferred_bootstrap(limit=limit):
        if maybe_promote_bootstrap(cfg, conn, creator_id=job.creator_id):
            promoted += 1
    return promoted
