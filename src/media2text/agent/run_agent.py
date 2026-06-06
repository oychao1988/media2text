"""CLI helpers for agent debugging."""

from __future__ import annotations

import typer

from media2text.agent.ai_agent import AIAgent
from media2text.agent.hermes_state import SessionDB
from media2text.core.config import AppConfig
from media2text.core.workspace import open_db

agent_app = typer.Typer(no_args_is_help=True, help="Desktop agent debug commands")


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
