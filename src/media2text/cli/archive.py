import typer

from media2text.core.archive.indexer import index_all
from media2text.core.archive.pricing import append_pricing_log
from media2text.core.archive.search import search_archive
from media2text.core.archive.timeline import timeline_archive
from media2text.core.compliance import is_compliance_accepted
from media2text.core.config import AppConfig
from media2text.core.exit_codes import EXIT_AUTH, EXIT_GENERAL, EXIT_OK
from media2text.core.json_out import emit
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

app = typer.Typer(help="Transcript archive index and search")


@app.command("index")
def index_cmd(
    creator_id: str | None = typer.Option(None, "--creator", help="Limit to one creator"),
    rebuild: bool = typer.Option(False, "--rebuild", help="Clear index and rebuild from transcripts"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    if creator_id and not CreatorRepo(conn).get(creator_id):
        emit(
            {
                "ok": False,
                "command": "archive index",
                "error": "creator not found",
                "creator_id": creator_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(EXIT_GENERAL)

    stats = index_all(
        conn,
        cfg.ensure_workspace(),
        creator_id=creator_id,
        rebuild=rebuild,
    )
    ok = not stats.errors
    emit(
        {
            "ok": ok,
            "command": "archive index",
            "rebuild": rebuild,
            "indexed_files": stats.indexed_files,
            "indexed_segments": stats.indexed_segments,
            "skipped": stats.skipped,
            "errors": stats.errors,
        },
        as_json=json_out,
    )
    raise typer.Exit(EXIT_OK if ok else EXIT_GENERAL)


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search keywords (FTS)"),
    creator_id: str | None = typer.Option(None, "--creator", help="Limit to one creator"),
    limit: int = typer.Option(20, "--limit", min=1, max=200),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    if not is_compliance_accepted(ws):
        emit(
            {
                "ok": False,
                "command": "archive search",
                "compliance_required": True,
                "error": "compliance disclaimer not accepted; run: media2text compliance accept",
            },
            as_json=json_out,
        )
        raise typer.Exit(EXIT_AUTH)

    conn = open_db(cfg)
    if creator_id and not CreatorRepo(conn).get(creator_id):
        emit(
            {
                "ok": False,
                "command": "archive search",
                "error": "creator not found",
                "creator_id": creator_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(EXIT_GENERAL)

    result = search_archive(conn, query, creator_id=creator_id, limit=limit)
    payload = {"command": "archive search", **result.to_dict()}
    emit(payload, as_json=json_out)
    raise typer.Exit(EXIT_OK if result.ok else EXIT_GENERAL)


@app.command("timeline")
def timeline_cmd(
    creator_id: str = typer.Option(..., "--creator", help="Creator id (required)"),
    keyword: str = typer.Option(..., "--keyword", help="Keyword to trace across sessions"),
    days: int = typer.Option(30, "--days", min=1, max=365, help="Only sessions within N days"),
    limit: int = typer.Option(500, "--limit", min=1, max=2000),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Keyword timeline for one creator (oldest session first)."""
    cfg = AppConfig.load()
    ws = cfg.ensure_workspace()
    if not is_compliance_accepted(ws):
        emit(
            {
                "ok": False,
                "command": "archive timeline",
                "compliance_required": True,
                "error": "compliance disclaimer not accepted; run: media2text compliance accept",
            },
            as_json=json_out,
        )
        raise typer.Exit(EXIT_AUTH)

    conn = open_db(cfg)
    if not CreatorRepo(conn).get(creator_id):
        emit(
            {
                "ok": False,
                "command": "archive timeline",
                "error": "creator not found",
                "creator_id": creator_id,
            },
            as_json=json_out,
        )
        raise typer.Exit(EXIT_GENERAL)

    result = timeline_archive(
        conn, keyword, creator_id=creator_id, days=days, limit=limit
    )
    emit({"command": "archive timeline", **result.to_dict()}, as_json=json_out)
    raise typer.Exit(EXIT_OK if result.ok else EXIT_GENERAL)


@app.command("pricing-log")
def pricing_log_cmd(
    yes: bool = typer.Option(False, "--yes", help="Would pay ¥99/month"),
    no: bool = typer.Option(False, "--no", help="Would not pay ¥99/month"),
    note: str | None = typer.Option(None, "--note"),
    creator_id: str | None = typer.Option(None, "--creator"),
    session_id: str | None = typer.Option(None, "--session"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    if yes == no:
        emit(
            {
                "ok": False,
                "command": "archive pricing-log",
                "error": "specify exactly one of --yes or --no",
            },
            as_json=json_out,
        )
        raise typer.Exit(EXIT_GENERAL)

    cfg = AppConfig.load()
    entry = append_pricing_log(
        cfg.ensure_workspace(),
        would_pay_99_cny=yes and not no,
        note=note,
        creator_id=creator_id,
        session_id=session_id,
    )
    emit(
        {
            "ok": True,
            "command": "archive pricing-log",
            "path": str(cfg.ensure_workspace() / "pricing-experiment.jsonl"),
            "entry": entry.to_dict(),
        },
        as_json=json_out,
    )
    raise typer.Exit(EXIT_OK)
