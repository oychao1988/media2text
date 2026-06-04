"""API path safety helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


def safe_workspace_path(workspace: Path, rel: str) -> Path:
    """Resolve a relative path under workspace; reject traversal escapes."""
    if not rel or not str(rel).strip():
        raise HTTPException(status_code=400, detail="path required")
    raw = str(rel).strip().replace("\\", "/")
    if raw.startswith("/") or ".." in Path(raw).parts:
        raise HTTPException(status_code=400, detail="path must stay under workspace")
    ws_root = workspace.resolve()
    target = (ws_root / raw).resolve()
    try:
        target.relative_to(ws_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path outside workspace") from exc
    return target


def workspace_rel(workspace: Path, path: str | Path | None) -> str | None:
    """Return workspace-relative posix path, or None if path is empty."""
    if not path:
        return None
    raw = Path(path)
    ws_root = workspace.resolve()
    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(ws_root).as_posix()
        except ValueError:
            return str(path).replace("\\", "/")
    return raw.as_posix().replace("\\", "/")
