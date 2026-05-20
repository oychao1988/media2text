"""Map command result dicts to process exit codes."""

from __future__ import annotations

import typer

from media2text.core.exit_codes import (
    EXIT_AUTH,
    EXIT_OK,
    EXIT_PARSE,
    EXIT_PARTIAL,
)


def exit_for_result(result: dict) -> int:
    if result.get("platform_changed"):
        return EXIT_PARSE
    if result.get("auth_required"):
        return EXIT_AUTH
    if not result.get("ok", True):
        return EXIT_PARTIAL
    return EXIT_OK


def raise_for_result(result: dict) -> None:
    code = exit_for_result(result)
    if code != EXIT_OK:
        raise typer.Exit(code)
