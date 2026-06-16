from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from issue_verify import (  # noqa: E402
    extract_verify_block,
    is_blocking_command,
    split_commands,
)


@pytest.mark.parametrize(
    "cmd",
    [
        "bin/monitor-watch-daemon.sh",
        ".venv/bin/media2text monitor watch --daemon --json",
        "media2text serve --port 8765",
        "pnpm --filter m2t-desktop tauri dev",
        "nohup media2text monitor watch --daemon >> log 2>&1 &",
    ],
)
def test_is_blocking_command_daemon_patterns(cmd: str) -> None:
    assert is_blocking_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "pytest tests/unit/test_monitor_lock.py -v",
        "python scripts/verify_monitor_watch_daemon_smoke.py",
        "ruff check src/",
    ],
)
def test_is_blocking_command_allows_ci_commands(cmd: str) -> None:
    assert not is_blocking_command(cmd)


def test_sh3_verify_block_excludes_shell_daemon(tmp_path) -> None:
    md = ROOT / "docs/issues/monitor-self-heal-sh3-ops-docs.md"
    block = extract_verify_block(md)
    commands = split_commands(block)
    assert "bin/monitor-watch-daemon.sh" not in commands
    assert any("verify_monitor_watch_daemon_smoke" in c for c in commands)
