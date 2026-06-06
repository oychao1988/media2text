"""CreatorAgentJobPool worker thread pool."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import structlog

from media2text.agent.creator_distill.bootstrap import run_bootstrap_job
from media2text.agent.creator_distill.deferred import tick_deferred_bootstrap
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()


def resolve_distill_workers(cfg: AppConfig) -> int:
    n = cfg.desktop.agent.distill.max_concurrent_jobs
    if n > 0:
        return n
    return 1


class CreatorAgentJobPool:
    """Process creator_agent_jobs (bootstrap / evolve)."""

    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="creator-distill",
        )

    def submit_bootstrap(self, cfg: AppConfig, *, job_id: str) -> None:
        def _run() -> None:
            conn = open_db(cfg)
            try:
                run_bootstrap_job(cfg, conn, job_id=job_id)
            finally:
                conn.close()

        self._executor.submit(_run)

    def drain_pending(self, cfg: AppConfig, conn, *, limit: int | None = None) -> int:
        jobs = CreatorAgentJobRepo(conn)
        jobs.reset_stale_running(older_than_sec=3600)
        tick_deferred_bootstrap(cfg, conn)
        max_jobs = limit if limit is not None else resolve_distill_workers(cfg)
        claimed = jobs.claim_pending(limit=max_jobs)
        for job in claimed:
            if job.kind == "bootstrap":
                self.submit_bootstrap(cfg, job_id=job.id)
            else:
                log.warning("creator_agent_job_unhandled_kind", kind=job.kind, job_id=job.id)
        return len(claimed)

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
