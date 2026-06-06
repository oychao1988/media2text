"""Hermes terminal + file tools (local backend)."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from media2text.agent.approval import ApprovalGate, shell_needs_approval
from media2text.agent.path_guard import resolve_under_cwd, terminal_cwd
from media2text.agent.profile_resolver import AgentProfileContext, resolve_profile
from media2text.agent.tools.m2t_handlers import ToolContext, _err, _ok
from media2text.agent.vendor.hermes.local import run_local_command


def _profile(ctx: ToolContext) -> AgentProfileContext:
    if ctx.profile is not None and not isinstance(ctx.profile, dict):
        return ctx.profile
    return resolve_profile(creator_id=ctx.creator_id, cfg=ctx.cfg)


def _gate(ctx: ToolContext) -> ApprovalGate:
    if ctx.approval_gate is not None:
        return ctx.approval_gate
    return ApprovalGate(ctx.cfg, auto_approve=True)


def _cwd(ctx: ToolContext) -> Path:
    profile = _profile(ctx)
    return terminal_cwd(
        ctx.cfg,
        creator_id=profile.creator_id,
        sandbox=profile.terminal_cwd,
    )


def read_file(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    path = str(params.get("path") or "").strip()
    if not path:
        return _err("MISSING_PATH", "path required")
    try:
        target = resolve_under_cwd(_cwd(ctx), path)
    except ValueError as exc:
        return _err("PATH_GUARD", str(exc))
    if not target.is_file():
        return _err("NOT_FOUND", "file not found")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _err("READ_FAILED", str(exc))
    return _ok({"path": path, "content": text})


def search_files(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    pattern = str(params.get("pattern") or "*").strip()
    root = _cwd(ctx)
    matches: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
            matches.append(rel)
        if len(matches) >= 100:
            break
    return _ok({"pattern": pattern, "matches": matches})


def patch(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    path = str(params.get("path") or "").strip()
    old = params.get("old_string")
    new = params.get("new_string")
    if not path or old is None or new is None:
        return _err("INVALID_ARGS", "path, old_string, new_string required")
    try:
        target = resolve_under_cwd(_cwd(ctx), path)
    except ValueError as exc:
        return _err("PATH_GUARD", str(exc))
    if not target.is_file():
        return _err("NOT_FOUND", "file not found")
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return _err("READ_FAILED", str(exc))
    if str(old) not in text:
        return _err("NOT_FOUND", "old_string not in file")
    gate = _gate(ctx)
    if not gate.ensure(
        action="patch",
        summary=f"Patch file {path}",
        detail={"path": path},
    ):
        return _err("DENIED", "approval denied")
    updated = text.replace(str(old), str(new), 1)
    target.write_text(updated, encoding="utf-8")
    return _ok({"path": path, "bytes": len(updated.encode())})


def terminal(ctx: ToolContext, **params: Any) -> dict[str, Any]:
    command = str(params.get("command") or "").strip()
    if not command:
        return _err("MISSING_COMMAND", "command required")
    cwd = _cwd(ctx)
    gate = _gate(ctx)
    if shell_needs_approval(command) or params.get("require_approval"):
        if not gate.ensure(
            action="terminal",
            summary=command[:200],
            detail={"command": command, "cwd": str(cwd)},
        ):
            return _err("DENIED", "approval denied")
    result = run_local_command(
        command=command,
        cwd=cwd,
        shell=ctx.cfg.terminal.default_shell,
        timeout_sec=float(ctx.cfg.terminal.timeout_sec),
    )
    return _ok(
        {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cwd": str(cwd),
        }
    )
