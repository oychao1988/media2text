"""File-backed curated memory (MEMORY.md / USER.md / SOUL.md)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

from media2text.core.config import AppConfig

logger = logging.getLogger(__name__)

MemoryTarget = Literal["memory", "user", "soul"]

_TARGET_FILES: dict[MemoryTarget, str] = {
    "memory": "MEMORY.md",
    "user": "USER.md",
    "soul": "SOUL.md",
}

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
]

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff\u2028\u2029]")


class MemorySafetyError(Exception):
    pass


def agent_dir(cfg: AppConfig) -> Path:
    root = cfg.ensure_workspace() / ".agent"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path_for(cfg: AppConfig, target: MemoryTarget) -> Path:
    return agent_dir(cfg) / _TARGET_FILES[target]


def _limit_for(cfg: AppConfig, target: MemoryTarget) -> int:
    if target == "user":
        return cfg.memory.user_max_chars
    return cfg.memory.max_chars


def scan_content(text: str) -> str | None:
    """Return block reason if unsafe, else None."""
    if _ZERO_WIDTH_RE.search(text):
        return "zero_width_characters"
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            return f"pattern:{pat.pattern}"
    return None


def read_file(cfg: AppConfig, target: MemoryTarget) -> str:
    path = _path_for(cfg, target)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def write_file(
    cfg: AppConfig,
    target: MemoryTarget,
    content: str,
    *,
    mode: str = "replace",
) -> dict[str, str | int | bool]:
    reason = scan_content(content)
    if reason:
        logger.warning("memory write blocked: %s target=%s", reason, target)
        raise MemorySafetyError(f"content blocked: {reason}")

    limit = _limit_for(cfg, target)
    if len(content) > limit:
        raise ValueError(f"content exceeds {limit} char limit for {target}")

    path = _path_for(cfg, target)
    if mode == "append" and path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        content = existing + content

    if len(content) > limit:
        raise ValueError(f"content exceeds {limit} char limit for {target}")

    path.write_text(content, encoding="utf-8")
    return {"target": target, "chars": len(content), "stored": True}


def load_volatile_snapshot(cfg: AppConfig) -> dict[str, str]:
    """Read MEMORY/USER/SOUL for volatile tier (workspace scope only in M3)."""
    return {
        "memory": read_file(cfg, "memory"),
        "user": read_file(cfg, "user"),
        "soul": read_file(cfg, "soul"),
    }


def format_memory_block(snapshot: dict[str, str]) -> str:
    parts: list[str] = []
    if snapshot.get("memory", "").strip():
        parts.append(f"## MEMORY\n{snapshot['memory'].strip()}")
    if snapshot.get("user", "").strip():
        parts.append(f"## USER\n{snapshot['user'].strip()}")
    if snapshot.get("soul", "").strip():
        parts.append(f"## SOUL\n{snapshot['soul'].strip()}")
    if not parts:
        return ""
    return "\n\n".join(parts)
