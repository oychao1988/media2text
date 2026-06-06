"""Read/write project `.env` for desktop-side secret updates."""

from __future__ import annotations

import os
import re
from pathlib import Path

from media2text.core.config import _project_root, load_dotenv_file


def _quote_env_value(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[\s#"\']', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def env_file_path() -> Path:
    return _project_root() / ".env"


def read_env_var(key: str, *, path: Path | None = None) -> str:
    """Read a single variable from ``.env`` without mutating ``os.environ``."""
    target = path or env_file_path()
    if not target.is_file():
        return ""
    prefix = f"{key}="
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if not value:
            return ""
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        return value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return ""


def upsert_env_var(key: str, value: str, *, path: Path | None = None) -> Path:
    """Insert or replace ``KEY=value`` in project ``.env``."""
    target = path or env_file_path()
    lines: list[str] = []
    if target.is_file():
        lines = target.read_text(encoding="utf-8").splitlines()

    new_line = f"{key}={_quote_env_value(value)}"
    found = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        name = line.split("=", 1)[0].strip()
        if name == key:
            out.append(new_line)
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(new_line)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    os.environ[key] = value
    return target


def reload_dotenv(*, override: bool = False) -> None:
    """Reload `.env` into os.environ."""
    if not override:
        load_dotenv_file()
        return
    env_path = env_file_path()
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=override)
