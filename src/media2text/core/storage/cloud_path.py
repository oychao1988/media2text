"""Workspace-relative path matching for cloud_uploads.local_path."""

from __future__ import annotations

from pathlib import Path


def normalize_workspace_rel(workspace: Path, raw: str | None) -> str | None:
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(workspace.resolve())).replace("\\", "/")
        except ValueError:
            return raw.replace("\\", "/").lstrip("./")
    return raw.replace("\\", "/").lstrip("./")


def paths_match_workspace_rel(
    workspace: Path,
    raw: str | None,
    target_rel: str,
) -> bool:
    if not raw or not target_rel:
        return False
    rel = normalize_workspace_rel(workspace, raw)
    if rel == target_rel:
        return True
    norm_target = target_rel.replace("\\", "/").lstrip("./")
    norm_raw = raw.replace("\\", "/").lstrip("./")
    return (
        norm_raw == norm_target
        or norm_raw.endswith(f"/{norm_target}")
        or norm_raw.endswith(norm_target)
    )
