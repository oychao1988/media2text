import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.live.segment_manifest import SegmentProcessJobRepo
from media2text.core.live.segment_process_pool import SegmentProcessExecutor
from media2text.core.notify import NotifyService
from media2text.core.workspace import open_db

app = typer.Typer(help="HLS segment upload queue (Tier-1)")


@app.command("run")
def run_cmd(
    limit: int = typer.Option(10, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    notify = NotifyService(cfg)
    pool = SegmentProcessExecutor(max_workers=1)
    try:
        pool.drain_pending(cfg, conn, notify=notify, limit=limit)
    finally:
        pool.shutdown(wait=True)
    emit(
        {
            "ok": True,
            "command": "segment-process run",
            "limit": limit,
        },
        as_json=json_out,
    )


@app.command("retry")
def retry_cmd(
    job_id: str = typer.Argument(..., help="Failed segment_process job id"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = SegmentProcessJobRepo(conn)
    job = repo.get(job_id)
    if not job:
        emit(
            {
                "ok": False,
                "command": "segment-process retry",
                "error": "job_not_found",
                "job_id": job_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(1)
    if job.status != "failed":
        emit(
            {
                "ok": False,
                "command": "segment-process retry",
                "error": "invalid_status",
                "job_id": job_id,
                "status": job.status,
            },
            as_json=json_out,
        )
        raise typer.Exit(1)
    if not repo.retry_failed(job_id):
        emit(
            {
                "ok": False,
                "command": "segment-process retry",
                "error": "retry_failed",
                "job_id": job_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(1)
    emit(
        {
            "ok": True,
            "command": "segment-process retry",
            "job_id": job_id,
            "previous_status": "failed",
            "new_status": "pending",
        },
        as_json=json_out,
    )
