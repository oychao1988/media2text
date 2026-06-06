"""Workspace path guard for terminal / file tools (Hermes §24.2.3)."""

from __future__ import annotations

from pathlib import Path

from media2text.core.config import AppConfig


def terminal_cwd(cfg: AppConfig, *, creator_id: str | None, sandbox: Path) -> Path:
    """Resolve sandbox cwd: creator thread → creator dir; else workspace."""
    if creator_id and sandbox.is_dir():
        return sandbox.resolve()
    base = cfg.terminal.cwd
    if base:
        p = Path(base)
        if not p.is_absolute():
            p = cfg.ensure_workspace().parent / p if str(base).startswith(".") else cfg.ensure_workspace() / p
        return p.expanduser().resolve()
    return cfg.ensure_workspace().resolve()


def resolve_under_cwd(cwd: Path, ref: str) -> Path:
    target = (cwd / ref).resolve()
    root = cwd.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes sandbox: {ref}")
    return target


def is_under_cwd(cwd: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(cwd.resolve())
        return True
    except ValueError:
        return False
