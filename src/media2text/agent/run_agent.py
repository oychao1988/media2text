"""CLI helpers for agent debugging and curator."""

from __future__ import annotations

import json
import threading

import typer

from media2text.agent.ai_agent import AIAgent
from media2text.agent.curator import (
    curator_status,
    list_backups,
    restore_archived_skill,
    rollback_backup,
    run_curator,
    seed_curator_state_if_missing,
)
from media2text.agent.hermes_state import SessionDB
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.skill_usage import pin, unpin
from media2text.core.config import AppConfig
from media2text.core.workspace import open_db

agent_app = typer.Typer(no_args_is_help=True, help="Desktop agent debug commands")
curator_app = typer.Typer(no_args_is_help=True, help="Skill curator maintenance")
distill_app = typer.Typer(no_args_is_help=True, help="Creator distill job drain")
agent_app.add_typer(curator_app, name="curator")
agent_app.add_typer(distill_app, name="distill")


@agent_app.command("echo")
def echo_turn(
    thread_id: str,
    text: str = typer.Option("hello", "--text", "-t", help="User message text"),
) -> None:
    """Run one echo turn against an existing thread."""
    cfg = AppConfig.load()
    conn = open_db(cfg)
    try:
        db = SessionDB(conn)
        agent = AIAgent(db, cfg)
        reply = agent.run_conversation(display_thread_id=thread_id, user_text=text)
        typer.echo(reply)
    finally:
        conn.close()


@curator_app.command("status")
def curator_status_cmd() -> None:
    """Show curator configuration and last run metadata."""
    cfg = AppConfig.load()
    seed_curator_state_if_missing(cfg)
    typer.echo(json.dumps(curator_status(cfg), ensure_ascii=False, indent=2))


@curator_app.command("run")
def curator_run_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview transitions without writing"),
    background: bool = typer.Option(False, "--background", help="Run in a background thread"),
) -> None:
    """Run curator phase-1 transitions (and LLM review when not dry-run)."""
    cfg = AppConfig.load()

    def _execute() -> None:
        report = run_curator(cfg, dry_run=dry_run, run_llm=not dry_run)
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))

    if background:
        threading.Thread(target=_execute, daemon=True, name="curator-cli").start()
        typer.echo('{"ok": true, "background": true}')
        return
    _execute()


@curator_app.command("pin")
def curator_pin(skill: str) -> None:
    cfg = AppConfig.load()
    profile = resolve_profile(creator_id=None, cfg=cfg)
    pin(profile, skill)
    typer.echo(json.dumps({"ok": True, "pinned": skill}, ensure_ascii=False))


@curator_app.command("unpin")
def curator_unpin(skill: str) -> None:
    cfg = AppConfig.load()
    profile = resolve_profile(creator_id=None, cfg=cfg)
    unpin(profile, skill)
    typer.echo(json.dumps({"ok": True, "unpinned": skill}, ensure_ascii=False))


@curator_app.command("restore")
def curator_restore(skill: str) -> None:
    cfg = AppConfig.load()
    profile = resolve_profile(creator_id=None, cfg=cfg)
    path = restore_archived_skill(profile, skill)
    typer.echo(json.dumps({"ok": True, "restored": str(path)}, ensure_ascii=False))


@curator_app.command("rollback")
def curator_rollback(
    backup: str | None = typer.Argument(None, help="Backup folder name under .curator_backups"),
    list_backups_flag: bool = typer.Option(False, "--list", help="List available backups"),
) -> None:
    cfg = AppConfig.load()
    profile = resolve_profile(creator_id=None, cfg=cfg)
    if list_backups_flag or backup is None:
        names = [p.name for p in list_backups(profile)]
        typer.echo(json.dumps({"backups": names}, ensure_ascii=False, indent=2))
        return
    path = rollback_backup(profile, backup)
    typer.echo(json.dumps({"ok": True, "restored_to": str(path)}, ensure_ascii=False))


@distill_app.command("drain")
def distill_drain(
    limit: int = typer.Option(0, "--limit", "-n", help="Max jobs to claim (0 = config default)"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON result"),
) -> None:
    """Drain pending creator_agent_jobs (bootstrap / evolve); replaces SlowTick embed."""
    from media2text.agent.creator_distill.pool import CreatorAgentJobPool, resolve_distill_workers

    cfg = AppConfig.load()
    conn = open_db(cfg)
    pool = CreatorAgentJobPool(max_workers=resolve_distill_workers(cfg))
    try:
        max_jobs = limit if limit > 0 else resolve_distill_workers(cfg)
        claimed = pool.drain_pending(cfg, conn, limit=max_jobs)
        result = {"ok": True, "claimed": claimed}
        if json_out:
            typer.echo(json.dumps(result, ensure_ascii=False))
        else:
            typer.echo(f"claimed {claimed} creator distill job(s)")
    finally:
        pool.shutdown(wait=True)
        conn.close()
