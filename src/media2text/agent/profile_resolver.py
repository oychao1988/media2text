"""Profile resolution stub until M5a dual-track UI."""

from __future__ import annotations

from typing import Any

from media2text.core.config import AppConfig


def resolve_profile(cfg: AppConfig) -> dict[str, Any]:
    """M1: fixed workspace ``data/.agent/`` profile directory."""
    root = cfg.ensure_workspace() / ".agent"
    root.mkdir(parents=True, exist_ok=True)
    return {
        "profile_dir": str(root),
        "profile_id": "default",
        "source": "workspace_stub",
    }
