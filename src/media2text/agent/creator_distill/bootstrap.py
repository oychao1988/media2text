"""CreatorAgentBootstrap worker (Hermes §24.4.4)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import structlog
import yaml

from media2text.agent.creator_distill.atomic import atomic_write_text
from media2text.agent.creator_distill.collect import collect_corpus
from media2text.agent.creator_distill.distill_llm import distill_bootstrap_json
from media2text.agent.creator_distill.gate import evaluate_bootstrap_gate
from media2text.agent.creator_distill.locks import creator_distill_lock
from media2text.agent.creator_distill.merge_corpus import (
    local_chars_from_corpus,
    merge_corpus_for_distill,
)
from media2text.agent.creator_distill.render import (
    render_local_corpus_md,
    render_skill_md,
    render_soul_md,
)
from media2text.agent.creator_distill.slug import normalize_skill_slug
from media2text.agent.creator_distill.state_cache import refresh_distill_state_cache
from media2text.agent.creator_distill.tavily_client import resolve_tavily_api_key
from media2text.agent.creator_distill.web_research import run_six_channel_research
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo

log = structlog.get_logger()


def _web_enabled(distill_cfg) -> bool:
    return distill_cfg.bootstrap_web_research and distill_cfg.web_search_provider != "none"


def _gate_payload(
    *,
    gate,
    corpus,
    merged,
    web_result=None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "web_channels_ok": gate.web_channels_ok,
        "local_chars": gate.local_chars,
        "total_chars": corpus.total_chars,
        "truncated": merged.truncated,
    }
    if gate.deferred_reason:
        payload["deferred_reason"] = gate.deferred_reason
    if web_result is not None:
        payload["web_channel_status"] = web_result.channel_status
    if extra:
        payload.update(extra)
    return payload


def run_bootstrap_job(
    cfg: AppConfig,
    conn,
    *,
    job_id: str,
    llm_fn: Callable[..., dict[str, Any]] | None = None,
    write_skill_fn: Callable[[Path, str], None] | None = None,
    web_research_fn: Callable[..., Any] | None = None,
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
        display = creator.display_name or creator.sec_uid
        slug = normalize_skill_slug(display, creator_id=job.creator_id)
        skill_dir = profile_dir / "skills" / slug
        refs_dir = skill_dir / "references" / "research"
        refs_dir.mkdir(parents=True, exist_ok=True)

        web_on = _web_enabled(distill_cfg)
        if web_on and not resolve_tavily_api_key(env_key=distill_cfg.tavily_api_key_env):
            jobs.mark_failed(
                job_id,
                error="tavily_api_key_missing",
                payload={"error": "tavily_api_key_missing"},
            )
            refresh_distill_state_cache(
                profile_dir,
                creator_id=job.creator_id,
                latest_job=jobs.get(job_id),
                extra={"bootstrap_status": "failed", "error": "tavily_api_key_missing"},
            )
            _set_bootstrap_status(profile_dir, "failed")
            return {"ok": False, "error": "tavily_api_key_missing"}

        web_result = None
        research = web_research_fn or run_six_channel_research
        local_scan = distill_cfg.local_scan if distill_cfg.local_scan.enabled else None

        with ThreadPoolExecutor(max_workers=2) as pool:
            local_future = pool.submit(
                collect_corpus,
                workspace=ws,
                sec_uid=creator.sec_uid,
                display_name=creator.display_name,
                platform=creator.platform,
                profile_url=creator.profile_url,
                max_input_chars=distill_cfg.max_input_chars,
                local_scan=local_scan,
            )
            web_future = None
            if web_on:
                web_future = pool.submit(
                    research,
                    cfg=distill_cfg,
                    refs_dir=refs_dir,
                    display_name=display,
                    platform=creator.platform,
                    profile_url=creator.profile_url,
                )
            corpus = local_future.result()
            if web_future is not None:
                web_result = web_future.result()

        web_channels_ok = web_result.channels_ok if web_result is not None else 0
        local_chars = local_chars_from_corpus(corpus)
        gate = evaluate_bootstrap_gate(
            web_channels_ok=web_channels_ok,
            local_chars=local_chars,
            defer_until_min_chars=distill_cfg.defer_until_min_chars,
            bootstrap_web_research=web_on,
        )
        merged = merge_corpus_for_distill(
            local_corpus=corpus,
            refs_dir=refs_dir if web_on else None,
            max_input_chars=distill_cfg.max_input_chars,
        )

        if not gate.proceed:
            defer_payload = _gate_payload(
                gate=gate, corpus=corpus, merged=merged, web_result=web_result
            )
            jobs.mark_deferred(job_id, payload=defer_payload)
            refresh_distill_state_cache(
                profile_dir,
                creator_id=job.creator_id,
                latest_job=jobs.find_active_bootstrap(job.creator_id),
                extra={
                    "bootstrap_status": "deferred",
                    "web_channels_ok": gate.web_channels_ok,
                    "local_chars": gate.local_chars,
                    "total_chars": corpus.total_chars,
                },
            )
            _set_bootstrap_status(profile_dir, "deferred")
            return {
                "ok": True,
                "deferred": True,
                "web_channels_ok": gate.web_channels_ok,
                "local_chars": gate.local_chars,
                "total_chars": corpus.total_chars,
            }

        corpus_text = merged.text

        if llm_fn is not None:
            distill = llm_fn(cfg, display_name=display, corpus_text=corpus_text)
        else:
            distill = distill_bootstrap_json(
                cfg,
                display_name=display,
                corpus_text=corpus_text,
                max_input_chars=distill_cfg.max_input_chars,
            )

        skill_dir.mkdir(parents=True, exist_ok=True)

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

        done_payload = _gate_payload(
            gate=gate,
            corpus=corpus,
            merged=merged,
            web_result=web_result,
            extra={"skill_slug": slug},
        )
        jobs.mark_done(job_id, payload=done_payload)
        refresh_distill_state_cache(
            profile_dir,
            creator_id=job.creator_id,
            latest_job=jobs.get(job_id),
            extra={
                "bootstrap_status": "done",
                "skill_slug": slug,
                "default_skills": merged_yaml.get("default_skills"),
                "web_channels_ok": gate.web_channels_ok,
                "local_chars": gate.local_chars,
            },
        )
        log.info(
            "creator_bootstrap_done",
            creator_id=job.creator_id,
            skill_slug=slug,
            chars=corpus.total_chars,
            web_channels_ok=gate.web_channels_ok,
        )
        return {
            "ok": True,
            "skill_slug": slug,
            "deferred": False,
            "web_channels_ok": gate.web_channels_ok,
        }
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
