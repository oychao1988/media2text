from pathlib import Path

import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.summarize.errors import SummarizeConfigError, SummarizeError
from media2text.core.summarize.factory import create_summarize_backend, summarize_engine_available
from media2text.core.summarize.runner import backfill_batch, merge_batch, run_batch
from media2text.core.workspace import open_db

app = typer.Typer(help="LLM transcript summarize")


def _parse_sessions(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [s.strip() for s in value.split(",") if s.strip()]


def _parse_paths(value: str | None) -> list[Path] | None:
    if not value:
        return None
    return [Path(p.strip()) for p in value.split(",") if p.strip()]


@app.command("run")
def run_cmd(
    path: Path | None = typer.Argument(None, help="Media file, transcript, or directory"),
    creator: str | None = typer.Option(None, "--creator"),
    profile: str | None = typer.Option(None, "--profile"),
    force: bool = typer.Option(False, "--force"),
    limit: int | None = typer.Option(None, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    ok, reason = summarize_engine_available(cfg)
    if not ok:
        payload = {
            "ok": False,
            "command": "summarize run",
            "summarized": 0,
            "errors": [{"error": reason}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1)

    try:
        backend = create_summarize_backend(cfg)
    except SummarizeConfigError as exc:
        payload = {
            "ok": False,
            "command": "summarize run",
            "summarized": 0,
            "errors": [{"error": str(exc)}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1) from exc

    if not path and not creator:
        typer.echo("Provide a path or --creator", err=True)
        raise typer.Exit(1)

    conn = open_db(cfg)
    paths = [path] if path else None
    try:
        payload = run_batch(
            cfg,
            conn,
            backend,
            paths=paths,
            creator_id=creator,
            profile=profile,
            force=force,
            limit=limit,
        )
    except SummarizeError as exc:
        payload = {
            "ok": False,
            "command": "summarize run",
            "summarized": 0,
            "errors": [{"error": str(exc)}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1) from exc

    emit(payload, as_json=json_out)
    if payload.get("errors"):
        raise typer.Exit(4)


@app.command("backfill")
def backfill_cmd(
    creator: str | None = typer.Option(None, "--creator", help="Limit to one creator"),
    profile: str | None = typer.Option(None, "--profile"),
    force: bool = typer.Option(False, "--force", help="Re-summarize even if .summary.md exists"),
    limit: int | None = typer.Option(None, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Summarize all workspace transcripts that lack a .summary.md sidecar."""
    cfg = AppConfig.load()
    ok, reason = summarize_engine_available(cfg)
    if not ok:
        payload = {
            "ok": False,
            "command": "summarize backfill",
            "pending": 0,
            "summarized": 0,
            "errors": [{"error": reason}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1)

    try:
        backend = create_summarize_backend(cfg)
    except SummarizeConfigError as exc:
        payload = {
            "ok": False,
            "command": "summarize backfill",
            "pending": 0,
            "summarized": 0,
            "errors": [{"error": str(exc)}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1) from exc

    conn = open_db(cfg)
    try:
        payload = backfill_batch(
            cfg,
            conn,
            backend,
            creator_id=creator,
            profile=profile,
            force=force,
            limit=limit,
        )
    except SummarizeError as exc:
        payload = {
            "ok": False,
            "command": "summarize backfill",
            "pending": 0,
            "summarized": 0,
            "errors": [{"error": str(exc)}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1) from exc

    emit(payload, as_json=json_out)
    if payload.get("errors"):
        raise typer.Exit(4)


@app.command("merge")
def merge_cmd(
    sessions: str | None = typer.Option(None, "--sessions"),
    paths: str | None = typer.Option(None, "--paths"),
    creator: str | None = typer.Option(None, "--creator"),
    date: str | None = typer.Option(None, "--date", help="YYYY-MM-DD"),
    group_index: int | None = typer.Option(None, "--group-index"),
    profile: str | None = typer.Option(None, "--profile"),
    force: bool = typer.Option(False, "--force"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    ok, reason = summarize_engine_available(cfg)
    if not ok:
        payload = {
            "ok": False,
            "command": "summarize merge",
            "errors": [{"error": reason}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1)

    try:
        backend = create_summarize_backend(cfg)
    except SummarizeConfigError as exc:
        payload = {
            "ok": False,
            "command": "summarize merge",
            "errors": [{"error": str(exc)}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1) from exc

    conn = open_db(cfg)
    try:
        payload = merge_batch(
            cfg,
            conn,
            backend,
            session_ids=_parse_sessions(sessions),
            path_list=_parse_paths(paths),
            creator_id=creator,
            date=date,
            group_index=group_index,
            profile=profile,
            force=force,
        )
    except SummarizeError as exc:
        payload = {
            "ok": False,
            "command": "summarize merge",
            "errors": [{"error": str(exc)}],
        }
        emit(payload, as_json=json_out)
        raise typer.Exit(1) from exc

    emit(payload, as_json=json_out)
