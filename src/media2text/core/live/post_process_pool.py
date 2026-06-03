from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from media2text.core.config import AppConfig
from media2text.core.live.post_process import run_post_process_job
from media2text.core.notify import NotifyService
from media2text.core.storage.repos import PostProcessJobRepo
from media2text.core.workspace import open_db


class PostProcessExecutor:
    """Thread pool for live post-process jobs (transcribe / summarize / upload)."""

    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="postproc",
        )

    def submit(
        self,
        cfg: AppConfig,
        *,
        job_id: str,
        notify: NotifyService,
    ) -> None:
        """D1: worker opens its own DB connection — do not pass LiveTick conn."""

        def _run() -> None:
            conn = open_db(cfg)
            try:
                run_post_process_job(cfg, conn, job_id=job_id, notify=notify)
            finally:
                conn.close()

        self._executor.submit(_run)

    def drain_pending(
        self,
        cfg: AppConfig,
        conn,
        *,
        notify: NotifyService,
        limit: int,
    ) -> None:
        """Claim on caller conn; submit each job to pool (non-blocking)."""
        jobs = PostProcessJobRepo(conn)
        jobs.reset_stale_running(older_than_sec=cfg.live.post_process_stale_running_sec)
        claimed = jobs.claim_pending(limit=limit)
        for job in claimed:
            self.submit(cfg, job_id=job.id, notify=notify)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
