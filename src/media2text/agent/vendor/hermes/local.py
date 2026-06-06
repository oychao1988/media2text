"""Local shell environment (Hermes tools/environments/local.py subset)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalRunResult:
    exit_code: int
    stdout: str
    stderr: str


def run_local_command(
    *,
    command: str,
    cwd: Path,
    shell: str = "bash",
    timeout_sec: float = 60.0,
) -> LocalRunResult:
    cwd.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        executable=shell if shell.startswith("/") else None,
    )
    return LocalRunResult(
        exit_code=int(proc.returncode),
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
