"""Deferred bootstrap promotion (§24.4.4.1)."""

from __future__ import annotations

import json

import structlog

from media2text.agent.creator_distill.collect import collect_corpus
from media2text.agent.creator_distill.gate import evaluate_bootstrap_gate
from media2text.agent.creator_distill.merge_corpus import local_chars_from_corpus
from media2text.agent.creator_distill.state_cache import refresh_distill_state_cache
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo

log = structlog.get_logger()


def _payload_web_channels_ok(job) -> int:
    if not job.payload_json:
        return 0
    try:
        payload = json.loads(job.payload_json)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    raw = payload.get("web_channels_ok", payload.get("webChannelsOk", 0))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def maybe_promote_bootstrap(cfg: AppConfig, conn, *, creator_id: str) -> bool:
    """If deferred bootstrap exists and gate would proceed, promote to pending."""
    jobs = CreatorAgentJobRepo(conn)
    job = jobs.find_active_bootstrap(creator_id)
    if not job or job.status != "deferred":
        return False

    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return False

    distill_cfg = cfg.desktop.agent.distill
    web_on = distill_cfg.bootstrap_web_research and distill_cfg.web_search_provider != "none"
    local_scan = distill_cfg.local_scan if distill_cfg.local_scan.enabled else None
    corpus = collect_corpus(
        workspace=cfg.ensure_workspace(),
        sec_uid=creator.sec_uid,
        display_name=creator.display_name,
        platform=creator.platform,
        profile_url=creator.profile_url,
        max_input_chars=distill_cfg.max_input_chars,
        local_scan=local_scan,
    )
    local_chars = local_chars_from_corpus(corpus)
    web_channels_ok = _payload_web_channels_ok(job)
    gate = evaluate_bootstrap_gate(
        web_channels_ok=web_channels_ok,
        local_chars=local_chars,
        defer_until_min_chars=distill_cfg.defer_until_min_chars,
        bootstrap_web_research=web_on,
    )
    if not gate.proceed:
        return False

    promoted = jobs.promote_deferred(job.id)
    if promoted:
        log.info(
            "creator_bootstrap_promoted",
            creator_id=creator_id,
            local_chars=local_chars,
            web_channels_ok=web_channels_ok,
        )
        try:
            from media2text.agent.profile_resolver import resolve_profile

            profile = resolve_profile(creator_id=creator_id, cfg=cfg)
            refresh_distill_state_cache(
                profile.memory_paths.profile_dir,
                creator_id=creator_id,
                latest_job=jobs.find_active_bootstrap(creator_id),
                extra={
                    "bootstrap_status": "pending",
                    "local_chars": local_chars,
                    "web_channels_ok": web_channels_ok,
                },
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
