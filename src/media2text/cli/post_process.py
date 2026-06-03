import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.live.post_process import drain_pending_jobs
from media2text.core.notify import NotifyService
from media2text.core.storage.repos import PostProcessJobRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Live recording post-process queue (transcribe / summarize / cloud)")


@app.command("run")
def run_cmd(
    limit: int = typer.Option(10, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    notify = NotifyService(cfg)
    results = drain_pending_jobs(cfg, conn, notify=notify, limit=limit)
    emit(
        {
            "ok": True,
            "command": "post-process run",
            "processed": len(results),
            "results": results,
        },
        as_json=json_out,
    )


@app.command("retry")
def retry_cmd(
    job_id: str = typer.Argument(..., help="Failed post-process job id"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    repo = PostProcessJobRepo(conn)
    job = repo.get(job_id)
    if not job:
        emit(
            {
                "ok": False,
                "command": "post-process retry",
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
                "command": "post-process retry",
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
                "command": "post-process retry",
                "error": "retry_failed",
                "job_id": job_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(1)
    emit(
        {
            "ok": True,
            "command": "post-process retry",
            "job_id": job_id,
            "previous_status": "failed",
            "new_status": "pending",
        },
        as_json=json_out,
    )
