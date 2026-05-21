import typer

from media2text.core.archive.indexer import index_all
from media2text.core.archive.search import search_archive
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
