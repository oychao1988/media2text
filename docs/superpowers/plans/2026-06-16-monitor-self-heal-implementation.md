# Monitor 自愈与可信锁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除「假锁 + 监控未跑 + 僵尸录制」复发：用 PID 命令行 + heartbeat 判定监控有效性，serve/health loop 自动修复，daemon 启动时恢复 orphan sessions。

**Architecture:** 抽出 `heartbeat.py` 打破循环依赖；`monitor_lock.py` 集中锁语义与 `monitor_effectively_running`（embedded 不掩盖 heartbeat_stale）；`build_runtime_status` / `build_live_status` / doctor 统一字段；`runtime_health_loop` 在 cooldown + 小时滑动窗口内 takeover（含 TOCTOU）；`_run_daemon_locked` 启动时 `recover_orphan_sessions`。三 PR 可独立合并。

**Eng Review 修订（2026-06-16）：** 已采纳 — SH6 滑动窗口、`thread_alive` 不强制 running、`live status` 增 `daemon_lock_valid`、JSON 写锁、`heartbeat_stale_sec=max(90,2×poll)`、`age>7200` mark_stale。

**Tech Stack:** Python 3.12+, FastAPI lifespan, threading MonitorSupervisor, SQLite, pytest, structlog。

**Spec:** [2026-06-16-monitor-self-heal-design.md](../specs/2026-06-16-monitor-self-heal-design.md)

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/media2text/core/runtime/heartbeat.py` | **新建** — `read/write_heartbeat`、`_age_sec`、`heartbeat_stale_sec`（从 `status.py` 抽出） |
| `src/media2text/core/runtime/monitor_lock.py` | **新建** — 锁读写、PID 校验、`monitor_effectively_running` |
| `src/media2text/core/process_lock.py` | 修改 — `clear_stale` 委托 `monitor_lock`；`.monitor-watch.lock` 写 JSON |
| `src/media2text/core/runtime/status.py` | 修改 — re-export heartbeat；`build_runtime_status` 用新判定 |
| `src/media2text/core/live/status.py` | 修改 — `build_live_status` 增 `daemon_lock_valid` / `daemon_lock_reason` |
| `src/media2text/core/runtime/supervisor.py` | 修改 — start/stop 用 `is_monitor_watch_pid` |
| `src/media2text/core/runtime/external_spawn.py` | 修改 — spawn 前校验假锁 |
| `src/media2text/core/archive/health.py` | 修改 — `monitor_lock_pid` 委托 `read_lock_pid`；`monitor_lock_valid` |
| `src/media2text/core/live/session_recovery.py` | **新建** — `recover_orphan_sessions`（含 7200s mark_stale） |
| `src/media2text/core/monitor/watcher.py` | 修改 — daemon 启动调 recovery |
| `src/media2text/api/app.py` | 修改 — lifespan 假锁清理后自启 |
| `src/media2text/api/services/monitor_self_heal.py` | **新建** — self-heal + cooldown + **小时滑动窗口** |
| `src/media2text/api/services/runtime_health_loop.py` | 修改 — 周期调用 self-heal |
| `src/media2text/api/services/work_queue.py` | 修改 — `recover_stale_work` 调 session recovery |
| `src/media2text/core/config.py` | 修改 — `DesktopConfig` 新字段 |
| `config.example.yaml` | 修改 — 文档化新配置 |
| `bin/monitor-watch-daemon.sh` | 修改 — 调 Python 清假锁 |
| `tests/unit/test_heartbeat.py` | **新建**（或断言合入 `test_runtime_status.py`） |
| `tests/unit/test_monitor_lock.py` | **新建** |
| `tests/unit/test_session_recovery.py` | **新建** |
| `tests/unit/test_monitor_self_heal.py` | **新建** |
| `tests/unit/test_api_sessions.py` | 修改 — `daemon_lock_valid` 形状 |

---

## PR 拆分

| PR | 范围 | 验收命令 |
|----|------|----------|
| **SH-1** | Task 0–4：`heartbeat` + `monitor_lock` + status/supervisor/process_lock + doctor/live status | `pytest tests/unit/test_heartbeat.py tests/unit/test_monitor_lock.py tests/unit/test_process_lock.py tests/unit/test_runtime_status.py tests/unit/test_monitor_supervisor.py tests/unit/test_api_sessions.py -v` |
| **SH-2** | session recovery + lifespan + self-heal loop | `pytest tests/unit/test_session_recovery.py tests/unit/test_monitor_self_heal.py tests/unit/test_api_runtime.py -v -m desktop` |
| **SH-3** | shell 脚本 + config.example + CLAUDE.md 摘录 | 手动 `bin/monitor-watch-daemon.sh` 冒烟 |

---

## SH-1 — 可信锁与运行态判定

### Task 0: 抽出 `heartbeat.py`（打破循环依赖）

**Files:**
- Create: `src/media2text/core/runtime/heartbeat.py`
- Modify: `src/media2text/core/runtime/status.py` — 从 `heartbeat` re-export，删除重复实现
- Test: `tests/unit/test_heartbeat.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_heartbeat.py
from media2text.core.runtime.heartbeat import heartbeat_stale_sec


def test_heartbeat_stale_sec_floor_at_90() -> None:
    assert heartbeat_stale_sec(10) == 90.0
    assert heartbeat_stale_sec(60) == 120.0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_heartbeat.py -v`  
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `heartbeat.py`**

将 `status.py` 中 `read_heartbeat`、`write_heartbeat`、`_age_sec`、`_parse_iso` 移入新文件，并新增：

```python
def heartbeat_stale_sec(live_poll_sec: int) -> float:
    return max(90.0, 2 * live_poll_sec)
```

`status.py` 顶部改为：

```python
from media2text.core.runtime.heartbeat import (
    _age_sec,
    heartbeat_stale_sec,
    read_heartbeat,
    write_heartbeat,
)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_heartbeat.py tests/unit/test_runtime_status.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/runtime/heartbeat.py src/media2text/core/runtime/status.py tests/unit/test_heartbeat.py
git commit -m "refactor(runtime): extract heartbeat helpers to break monitor_lock cycle"
```

---

### Task 1: `monitor_lock` 模块与单元测试

**Files:**
- Create: `src/media2text/core/runtime/monitor_lock.py`
- Create: `tests/unit/test_monitor_lock.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_monitor_lock.py
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from media2text.core.runtime.monitor_lock import (
    clear_invalid_monitor_lock,
    is_monitor_watch_pid,
    monitor_effectively_running,
    read_lock_pid,
    write_lock_record,
)

pytestmark = pytest.mark.desktop


def test_read_lock_pid_legacy_integer(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("424242\n", encoding="utf-8")
    assert read_lock_pid(lock) == 424242


def test_read_lock_pid_json(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text(
        json.dumps({"pid": 12345, "mode": "external", "argv": "media2text monitor watch --daemon"}),
        encoding="utf-8",
    )
    assert read_lock_pid(lock) == 12345


def test_read_lock_pid_empty_file(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("", encoding="utf-8")
    assert read_lock_pid(lock) is None


def test_read_lock_pid_invalid_json(tmp_path: Path) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("{}", encoding="utf-8")
    assert read_lock_pid(lock) is None


def test_is_monitor_watch_pid_matches_cmdline(monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._process_commandline",
        lambda pid: "/path/.venv/bin/media2text monitor watch --daemon",
    )
    assert is_monitor_watch_pid(999) is True


def test_is_monitor_watch_pid_rejects_unrelated_process(monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock._process_commandline",
        lambda pid: "/usr/sbin/audioaccessoryd",
    )
    assert is_monitor_watch_pid(581) is False


def test_clear_invalid_monitor_lock_removes_mismatch(tmp_path: Path, monkeypatch) -> None:
    lock = tmp_path / ".monitor-watch.lock"
    lock.write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    assert clear_invalid_monitor_lock(lock) is True
    assert not lock.exists()


def test_monitor_effectively_running_requires_heartbeat(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from media2text.core.config import AppConfig, LiveConfig
    from media2text.core.runtime.heartbeat import write_heartbeat

    cfg = AppConfig(workspace=tmp_path, live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    lock = ws / ".monitor-watch.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: True,
    )
    running, reason = monitor_effectively_running(
        ws, cfg, supervisor_status={"managed_by": "none", "thread_alive": False}, live_poll_sec=10
    )
    assert running is False
    assert reason == "heartbeat_stale"


def test_monitor_effectively_running_rejects_fake_lock_regression_581(tmp_path: Path, monkeypatch) -> None:
    """Regression: PID 581 reused by audioaccessoryd must not count as running."""
    from media2text.core.config import AppConfig, LiveConfig

    cfg = AppConfig(workspace=tmp_path, live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    running, reason = monitor_effectively_running(
        ws, cfg, supervisor_status={"managed_by": "none", "thread_alive": False}, live_poll_sec=10
    )
    assert running is False
    assert reason == "lock_pid_mismatch"


def test_monitor_effectively_running_embedded_stale_heartbeat_not_masked(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from media2text.core.config import AppConfig, LiveConfig
    from media2text.core.runtime.heartbeat import write_heartbeat

    cfg = AppConfig(workspace=tmp_path, live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    lock = ws / ".monitor-watch.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: True,
    )
    running, reason = monitor_effectively_running(
        ws,
        cfg,
        supervisor_status={"managed_by": "embedded", "thread_alive": True},
        live_poll_sec=10,
    )
    assert running is False
    assert reason == "heartbeat_stale"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/unit/test_monitor_lock.py -v`  
Expected: FAIL — `ModuleNotFoundError: monitor_lock`

- [ ] **Step 3: Implement `monitor_lock.py`**

```python
# src/media2text/core/runtime/monitor_lock.py
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from media2text.core.runtime.heartbeat import _age_sec, heartbeat_stale_sec, read_heartbeat

LockReason = Literal[
    "lock_missing",
    "lock_pid_mismatch",
    "heartbeat_stale",
    "embedded_thread_dead",
]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _process_commandline(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    return line or None


def is_monitor_watch_pid(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if not _pid_alive(pid):
        return False
    cmd = _process_commandline(pid) or ""
    lowered = cmd.lower()
    if "media2text" not in lowered:
        return False
    return "monitor" in lowered and "watch" in lowered


def read_lock_pid(lock_path: Path) -> int | None:
    if not lock_path.is_file():
        return None
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            pid = int(data["pid"])
            return pid
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class LockRecord:
    pid: int
    mode: str = "external"
    argv: str = "media2text monitor watch --daemon"


def write_lock_record(lock_path: Path, *, pid: int, mode: str = "external") -> None:
    payload = LockRecord(pid=pid, mode=mode)
    lock_path.write_text(
        json.dumps({"pid": payload.pid, "mode": payload.mode, "argv": payload.argv}),
        encoding="utf-8",
    )


def clear_invalid_monitor_lock(lock_path: Path) -> bool:
    pid = read_lock_pid(lock_path)
    if pid is None:
        if lock_path.is_file():
            lock_path.unlink(missing_ok=True)
            return True
        return False
    if not _pid_alive(pid):
        lock_path.unlink(missing_ok=True)
        return True
    if not is_monitor_watch_pid(pid):
        lock_path.unlink(missing_ok=True)
        return True
    return False


def monitor_effectively_running(
    workspace: Path,
    cfg,
    *,
    supervisor_status: dict[str, Any] | None,
    live_poll_sec: int,
) -> tuple[bool, str | None]:
    sup = supervisor_status or {}
    lock_path = workspace / ".monitor-watch.lock"
    lock_pid = read_lock_pid(lock_path)
    stale_sec = heartbeat_stale_sec(live_poll_sec)

    if sup.get("thread_alive"):
        if lock_pid != os.getpid():
            return False, "embedded_thread_dead"
        heartbeat = read_heartbeat(workspace)
        last_tick = heartbeat.get("last_tick_at") if heartbeat else None
        tick_age = _age_sec(last_tick)
        if tick_age is None or tick_age > stale_sec:
            return False, "heartbeat_stale"
        return True, None

    if lock_pid is None:
        return False, "lock_missing"

    if not is_monitor_watch_pid(lock_pid):
        return False, "lock_pid_mismatch"

    heartbeat = read_heartbeat(workspace)
    last_tick = heartbeat.get("last_tick_at") if heartbeat else None
    tick_age = _age_sec(last_tick)
    if tick_age is None or tick_age > stale_sec:
        return False, "heartbeat_stale"

    return True, None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_monitor_lock.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/runtime/monitor_lock.py tests/unit/test_monitor_lock.py
git commit -m "feat(runtime): add monitor_lock PID cmdline validation"
```

**Depends on:** Task 0 (`heartbeat.py`)

---

### Task 2: 接入 `process_lock`（清假锁 + JSON 写锁）

**Files:**
- Modify: `src/media2text/core/process_lock.py`
- Modify: `tests/unit/test_process_lock.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/unit/test_process_lock.py
import json
import os
from pathlib import Path


def test_workspace_lock_clears_pid_reused_by_other_process(tmp_path: Path, monkeypatch) -> None:
    from media2text.core.process_lock import workspace_lock

    lock_path = tmp_path / "test.lock"
    lock_path.write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    with workspace_lock(lock_path):
        assert lock_path.read_text(encoding="utf-8") == str(os.getpid())


def test_acquire_monitor_watch_lock_writes_json(tmp_path: Path) -> None:
    from media2text.core.process_lock import acquire_workspace_lock, release_workspace_lock

    lock_path = tmp_path / ".monitor-watch.lock"
    fd = acquire_workspace_lock(lock_path)
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        assert "monitor" in data["argv"]
    finally:
        release_workspace_lock(lock_path, fd)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_process_lock.py::test_workspace_lock_clears_pid_reused_by_other_process tests/unit/test_process_lock.py::test_acquire_monitor_watch_lock_writes_json -v`

- [ ] **Step 3: Update `process_lock.py`**

```python
def clear_stale_workspace_lock(lock_path: Path) -> bool:
    from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock

    return clear_invalid_monitor_lock(lock_path)


def acquire_workspace_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    clear_stale_workspace_lock(lock_path)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LockError(f"lock already held: {lock_path}") from exc
    if lock_path.name == ".monitor-watch.lock":
        from media2text.core.runtime.monitor_lock import write_lock_record

        write_lock_record(lock_path, pid=os.getpid(), mode="embedded")
        os.close(fd)
        return fd
    os.write(fd, str(os.getpid()).encode())
    return fd
```

注意：`write_lock_record` 直接写文件时先 `os.close(fd)` 再写，或改为 `os.write(fd, json_bytes)` 后保留 fd — 实现时二选一，**测试须断言 JSON 内容**。

- [ ] **Step 4: Run all process_lock tests**

Run: `pytest tests/unit/test_process_lock.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/process_lock.py tests/unit/test_process_lock.py
git commit -m "fix(process_lock): clear fake lock and write JSON monitor lock"
```

---

### Task 3: `build_runtime_status`、`build_live_status` 与 doctor

**Files:**
- Modify: `src/media2text/core/runtime/status.py`
- Modify: `src/media2text/core/live/status.py`
- Modify: `src/media2text/core/archive/health.py`
- Modify: `tests/unit/test_runtime_status.py`
- Modify: `tests/unit/test_api_sessions.py`

- [ ] **Step 1: Failing tests**

```python
# append to tests/unit/test_runtime_status.py
def test_build_runtime_status_rejects_fake_lock_pid(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    conn = open_db(cfg)
    payload = build_runtime_status(cfg, conn=conn)
    assert payload["daemon"]["running"] is False
    assert payload["daemon"]["lock_valid"] is False
    assert payload["daemon"]["lock_reason"] == "lock_pid_mismatch"
    assert payload["health"] == "stopped"


def test_build_runtime_status_embedded_heartbeat_stale_health_degraded(tmp_path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from media2text.core.runtime.heartbeat import write_heartbeat

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    sup = {"managed_by": "embedded", "thread_alive": True, "running": True}
    payload = build_runtime_status(cfg, conn=open_db(cfg), supervisor_status=sup)
    assert payload["daemon"]["running"] is False
    assert payload["health"] == "degraded"


def test_build_runtime_status_embedded_heartbeat_stale_not_running(tmp_path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from media2text.core.runtime.heartbeat import write_heartbeat

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live=LiveConfig(live_poll_interval_sec=10))
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text(str(os.getpid()), encoding="utf-8")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    write_heartbeat(ws, last_tick_at=stale)
    sup = {"managed_by": "embedded", "thread_alive": True, "running": True}
    payload = build_runtime_status(cfg, conn=open_db(cfg), supervisor_status=sup)
    assert payload["daemon"]["running"] is False
    assert payload["daemon"]["lock_reason"] == "heartbeat_stale"
```

```python
# append to tests/unit/test_api_sessions.py — update test_build_live_status_shape
def test_build_live_status_includes_daemon_lock_valid(workspace, monkeypatch) -> None:
    cfg = AppConfig(workspace=workspace)
    (workspace / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    conn = open_db(cfg)
    payload = build_live_status(cfg, conn)
    assert payload["daemon_lock_valid"] is False
    assert payload["daemon_lock_reason"] == "lock_pid_mismatch"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_runtime_status.py::test_build_runtime_status_rejects_fake_lock_pid tests/unit/test_api_sessions.py -v -k daemon_lock`

- [ ] **Step 3: Patch status builders**

`read_daemon_pid()`：**改为委托** `read_lock_pid(lock_path)`，删除单独 `int(strip)` 逻辑，避免 live/runtime 读锁语义分叉。

`build_runtime_status`：

1. `from media2text.core.runtime.monitor_lock import monitor_effectively_running, read_lock_pid`
2. `from media2text.core.runtime.heartbeat import heartbeat_stale_sec`
3. 替换 running 判定为**仅** `monitor_effectively_running` 结果 — **删除** `if sup.get("thread_alive"): running = True`
4. `compute_health` 调用处传入 `live_poll_sec` 对应的 `heartbeat_stale_sec(live_poll_sec)` 作 stale 阈值（或让 `compute_health` 内部调用 `heartbeat_stale_sec`）；embedded + stale 时 `health=degraded`
5. `daemon` dict 增加 `"lock_valid": lock_reason is None and running`, `"lock_reason": lock_reason`

`build_live_status`：

```python
from media2text.core.runtime.monitor_lock import monitor_effectively_running, read_lock_pid
from media2text.core.runtime.status import _live_poll_interval_sec

lock_pid = read_lock_pid(ws / ".monitor-watch.lock")
running, lock_reason = monitor_effectively_running(
    ws, cfg, supervisor_status={"managed_by": "none", "thread_alive": False}, live_poll_sec=_live_poll_interval_sec(cfg)
)
# payload 增加:
"daemon_lock_valid": lock_reason is None and running,
"daemon_lock_reason": lock_reason,
```

`archive/health.py`：

```python
def monitor_lock_pid(workspace: Path) -> int | None:
    from media2text.core.runtime.monitor_lock import read_lock_pid
    return read_lock_pid(workspace / ".monitor-watch.lock")

def monitor_lock_valid(workspace: Path) -> bool:
    from media2text.core.runtime.monitor_lock import is_monitor_watch_pid, read_lock_pid
    pid = read_lock_pid(workspace / ".monitor-watch.lock")
    if pid is None:
        return True
    return is_monitor_watch_pid(pid)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_runtime_status.py tests/unit/test_api_sessions.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/runtime/status.py src/media2text/core/live/status.py src/media2text/core/archive/health.py src/media2text/core/doctor_checks.py tests/unit/test_runtime_status.py tests/unit/test_api_sessions.py
git commit -m "fix(runtime): unify lock validity in runtime and live status"
```

---

### Task 4: Supervisor / external_spawn 假锁处理

**Files:**
- Modify: `src/media2text/core/runtime/supervisor.py:69-101`
- Modify: `src/media2text/core/runtime/external_spawn.py:36-46`
- Modify: `tests/unit/test_monitor_supervisor.py`
- Modify: `tests/unit/test_external_spawn.py`

- [ ] **Step 1: Test — supervisor start clears fake external lock**

```python
# append to tests/unit/test_monitor_supervisor.py
def test_supervisor_start_clears_fake_external_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(tmp_path)
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    sup = MonitorSupervisor()
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    with patch.object(MonitorSupervisor, "_run_daemon_thread", lambda self: None):
        result = sup.start(cfg)
    assert result["ok"] is True
    assert not (ws / ".monitor-watch.lock").exists() or sup.status(cfg).thread_alive
```

- [ ] **Step 2: Implement — `supervisor.start` 开头**

```python
from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock, is_monitor_watch_pid, read_lock_pid

# In start(), before acquire_workspace_lock:
clear_invalid_monitor_lock(lock_path)
pid = read_lock_pid(lock_path)
if pid and is_monitor_watch_pid(pid) and not self._holds_embedded_lock(pid):
    return {"ok": False, "already_running_external": True, "pid": pid, ...}
```

`external_spawn.spawn_cli_monitor_daemon` 同样在检查 existing 前调用 `clear_invalid_monitor_lock(lock_path)`。

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_monitor_supervisor.py tests/unit/test_external_spawn.py -v`  
Expected: PASS（必要时更新 `test_supervisor_external_lock_blocks_start`：假锁应 start 成功）

- [ ] **Step 4: Commit**

```bash
git add src/media2text/core/runtime/supervisor.py src/media2text/core/runtime/external_spawn.py tests/unit/test_monitor_supervisor.py tests/unit/test_external_spawn.py
git commit -m "fix(supervisor): clear fake lock before embedded start"
```

---

## SH-2 — 孤儿场次恢复与 Self-heal Watchdog

### Task 5: `recover_orphan_sessions`

**Files:**
- Create: `src/media2text/core/live/session_recovery.py`
- Create: `tests/unit/test_session_recovery.py`
- Modify: `src/media2text/core/monitor/watcher.py:115-120`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_session_recovery.py
from datetime import datetime, timedelta, timezone

from media2text.core.config import AppConfig
from media2text.core.live.session_recovery import recover_orphan_sessions
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo
from media2text.core.workspace import open_db


def test_recover_orphan_sessions_enqueues_finalize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"offline_confirm_sec": 45})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAorphan",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    past = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    LiveSessionRepo(conn).set_offline_since(sid, past)
    conn.execute("UPDATE live_sessions SET obs_still_live = 0 WHERE id = ?", (sid,))
    conn.commit()

    count = recover_orphan_sessions(cfg, conn)
    assert count >= 1
    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{sid}")


def test_recover_orphan_sessions_marks_very_old_without_offline(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAold",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="1",
        temp_path=str(tmp_path / "live.flv"),
        ffmpeg_pid=999999999,
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    conn.execute(
        "UPDATE live_sessions SET started_at = ?, obs_ffmpeg_alive = 0 WHERE id = ?",
        (old, sid),
    )
    conn.commit()

    recover_orphan_sessions(cfg, conn)
    row = LiveSessionRepo(conn).get(sid)
    assert row.status == "failed"
    assert row.error == "stale_recording"
```

- [ ] **Step 2: Implement**

```python
# src/media2text/core/live/session_recovery.py
from __future__ import annotations

import os
from datetime import datetime, timezone

from media2text.core.config import AppConfig
from media2text.core.live.task_reconciler import reconcile_live
from media2text.core.storage.repos import LiveSessionRepo

_ORPHAN_MAX_AGE_SEC = 7200


def recover_orphan_sessions(cfg: AppConfig, conn) -> int:
    sessions = LiveSessionRepo(conn)
    touched = 0
    stale_marked = 0
    now = datetime.now(timezone.utc)
    for row in sessions.list_active():
        if row.status != "recording":
            continue
        ffmpeg_dead = False
        if row.ffmpeg_pid:
            try:
                os.kill(row.ffmpeg_pid, 0)
            except OSError:
                ffmpeg_dead = True
                conn.execute(
                    "UPDATE live_sessions SET obs_ffmpeg_alive = 0 WHERE id = ?",
                    (row.id,),
                )
                touched += 1
        if ffmpeg_dead and not row.offline_since_at:
            try:
                started = datetime.fromisoformat(row.started_at.replace("Z", "+00:00"))
            except ValueError:
                started = now
            if (now - started).total_seconds() > _ORPHAN_MAX_AGE_SEC:
                sessions.update_status(
                    row.id,
                    status="failed",
                    error="stale_recording",
                    ended=True,
                )
                stale_marked += 1
    conn.commit()
    ensured = reconcile_live(cfg, conn)
    return touched + stale_marked + ensured
```

- [ ] **Step 3: Wire in watcher**

```python
# watcher.py _run_daemon_locked — after bootstrap_streaming_stt
from media2text.core.live.session_recovery import recover_orphan_sessions
recovered = recover_orphan_sessions(self._cfg, self._conn)
if recovered:
    log.info("recover_orphan_sessions_on_daemon_start", recovered=recovered)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_session_recovery.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/live/session_recovery.py src/media2text/core/monitor/watcher.py tests/unit/test_session_recovery.py
git commit -m "feat(live): recover orphan sessions on daemon start"
```

---

### Task 6: `monitor_self_heal` 服务

**Files:**
- Create: `src/media2text/api/services/monitor_self_heal.py`
- Create: `tests/unit/test_monitor_self_heal.py`
- Modify: `src/media2text/core/config.py` — `DesktopConfig`
- Modify: `config.example.yaml`

- [ ] **Step 1: Add config fields**

```python
# DesktopConfig in config.py
monitor_self_heal: bool = True
monitor_self_heal_cooldown_sec: int = 120
monitor_self_heal_max_per_hour: int = 3
monitor_self_heal_check_every_sec: int = 30
```

`config.example.yaml` 同步四字段。

- [ ] **Step 2: Failing tests**

```python
# tests/unit/test_monitor_self_heal.py
import time
from unittest.mock import MagicMock, patch

import pytest

from media2text.core.config import AppConfig, DesktopConfig
from media2text.api.services import monitor_self_heal as msh
from media2text.api.services.monitor_self_heal import maybe_self_heal_monitor

pytestmark = pytest.mark.desktop


def test_maybe_self_heal_takeover_when_stopped(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=True),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "none", "thread_alive": False}
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "lock_pid_mismatch"),
    ):
        with patch.object(sup, "takeover", return_value={"ok": True, "start": {"ok": True}}) as takeover:
            result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["healed"] is True
    takeover.assert_called_once()


def test_maybe_self_heal_hourly_rate_limit(tmp_path, monkeypatch) -> None:
    msh._last_heal_at = 0.0
    msh._heal_timestamps.clear()
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(
            auto_start_monitor=True,
            monitor_self_heal=True,
            monitor_self_heal_max_per_hour=3,
            monitor_self_heal_cooldown_sec=0,
        ),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "none", "thread_alive": False}
    now = time.monotonic()
    msh._heal_timestamps.extend([now - 10, now - 20, now - 30])
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "heartbeat_stale"),
    ):
        result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["healed"] is False
    assert result["skipped"] == "hourly_limit"


def test_maybe_self_heal_skips_when_external_just_started(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True, monitor_self_heal=True),
    )
    sup = MagicMock()
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "lock_missing"),
    ):
        with patch(
            "media2text.api.services.monitor_self_heal.read_lock_pid",
            return_value=4242,
        ):
            with patch(
                "media2text.api.services.monitor_self_heal.is_monitor_watch_pid",
                return_value=True,
            ):
                with patch.object(sup, "takeover") as takeover:
                    result = maybe_self_heal_monitor(cfg, sup, force=True)
    assert result["skipped"] == "external_started"
    takeover.assert_not_called()


def test_maybe_self_heal_cooldown(tmp_path, monkeypatch) -> None:
    msh._last_heal_at = time.monotonic()
    cfg = AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(
            auto_start_monitor=True,
            monitor_self_heal=True,
            monitor_self_heal_cooldown_sec=120,
        ),
    )
    sup = MagicMock()
    sup.status_dict.return_value = {"managed_by": "none", "thread_alive": False}
    with patch(
        "media2text.api.services.monitor_self_heal.monitor_effectively_running",
        return_value=(False, "heartbeat_stale"),
    ):
        result = maybe_self_heal_monitor(cfg, sup, force=False)
    assert result["healed"] is False
    assert result["skipped"] == "cooldown"
```

- [ ] **Step 3: Implement `maybe_self_heal_monitor`**

```python
# src/media2text/api/services/monitor_self_heal.py
from __future__ import annotations

import time
from typing import Any

import structlog

from media2text.core.config import AppConfig
from media2text.core.runtime.monitor_lock import (
    clear_invalid_monitor_lock,
    is_monitor_watch_pid,
    monitor_effectively_running,
    read_lock_pid,
)
from media2text.core.runtime.status import _live_poll_interval_sec
from media2text.core.runtime.supervisor import MonitorSupervisor
from media2text.api.services.work_queue import recover_stale_work

log = structlog.get_logger()
_last_heal_at: float = 0.0
_heal_timestamps: list[float] = []
_HOURLY_WINDOW_SEC = 3600.0


def _hourly_limit_reached(desktop, now: float) -> bool:
    max_per_hour = desktop.monitor_self_heal_max_per_hour
    _heal_timestamps[:] = [t for t in _heal_timestamps if now - t < _HOURLY_WINDOW_SEC]
    return len(_heal_timestamps) >= max_per_hour


def maybe_self_heal_monitor(
    cfg: AppConfig,
    supervisor: MonitorSupervisor,
    *,
    force: bool = False,
) -> dict[str, Any]:
    global _last_heal_at
    desktop = cfg.desktop
    if not desktop.auto_start_monitor or not desktop.monitor_self_heal:
        return {"ok": True, "healed": False, "skipped": "disabled"}

    ws = cfg.ensure_workspace()
    lock_path = ws / ".monitor-watch.lock"
    live_poll = _live_poll_interval_sec(cfg)
    running, reason = monitor_effectively_running(
        ws, cfg, supervisor_status=supervisor.status_dict(cfg), live_poll_sec=live_poll
    )
    if running:
        return {"ok": True, "healed": False, "running": True}

    now = time.monotonic()
    if not force and (now - _last_heal_at) < desktop.monitor_self_heal_cooldown_sec:
        return {"ok": True, "healed": False, "skipped": "cooldown", "reason": reason}
    if _hourly_limit_reached(desktop, now):
        log.warning("monitor_self_heal_gave_up", reason=reason)
        return {"ok": True, "healed": False, "skipped": "hourly_limit", "reason": reason}

    clear_invalid_monitor_lock(lock_path)
    pid = read_lock_pid(lock_path)
    if pid and is_monitor_watch_pid(pid):
        return {"ok": True, "healed": False, "skipped": "external_started", "pid": pid, "reason": reason}

    result = supervisor.takeover(cfg)
    if not result.get("ok") and reason == "lock_pid_mismatch":
        clear_invalid_monitor_lock(lock_path)
        result = supervisor.takeover(cfg)

    if result.get("ok"):
        recover_stale_work(cfg, older_than_sec=cfg.monitor.stale_running_sec)
        _last_heal_at = now
        _heal_timestamps.append(now)
        log.info("monitor_self_heal_ok", reason=reason)
        return {"ok": True, "healed": True, "reason": reason, "takeover": result}

    log.warning("monitor_self_heal_failed", reason=reason, detail=result)
    return {"ok": False, "healed": False, "reason": reason, "takeover": result}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_monitor_self_heal.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/services/monitor_self_heal.py src/media2text/core/config.py config.example.yaml tests/unit/test_monitor_self_heal.py
git commit -m "feat(desktop): add monitor self-heal with cooldown"
```

---

### Task 7: Lifespan 与 health loop 接入

**Files:**
- Modify: `src/media2text/api/app.py:56-62`
- Modify: `src/media2text/api/services/runtime_health_loop.py`
- Modify: `tests/unit/test_api_runtime.py`

- [ ] **Step 1: Failing API test — lifespan heals fake lock**

```python
# test_api_runtime.py
def test_lifespan_auto_start_clears_fake_lock(api_client, workspace, monkeypatch) -> None:
    (workspace / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )
    # Re-create client to trigger lifespan — use existing api_client fixture pattern
    # Assert GET /api/runtime shows embedded running OR lock cleared
    r = api_client.get("/api/runtime")
    body = r.json()
    assert body["daemon"]["lock_reason"] is None or body["daemon"]["running"] is True
```

（若 fixture 不便重跑 lifespan，改为 unit test `test_app_lifespan_auto_start` 单独测 `lifespan` 函数。）

- [ ] **Step 2: Update `api/app.py` lifespan**

```python
from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock, is_monitor_watch_pid, read_lock_pid

if cfg.desktop.auto_start_monitor:
    lock_path = cfg.ensure_workspace() / ".monitor-watch.lock"
    pid = read_lock_pid(lock_path)
    if pid and not is_monitor_watch_pid(pid):
        clear_invalid_monitor_lock(lock_path)
        start_result = supervisor.start(cfg)
    elif pid and is_monitor_watch_pid(pid):
        log.info("monitor_auto_start_deferred_external", pid=pid)
    else:
        start_result = supervisor.start(cfg)
```

- [ ] **Step 3: Health loop — 每 30s 调 `maybe_self_heal_monitor`**

在 `run_runtime_health_loop` 内维护 `last_self_heal_check` monotonic 时间戳，超过 `cfg.desktop.monitor_self_heal_check_every_sec` 时调用。

- [ ] **Step 3b: Health loop 周期自愈单测**

```python
# tests/unit/test_api_runtime.py 或 test_runtime_health_loop.py
def test_health_loop_triggers_self_heal_after_interval(monkeypatch) -> None:
    """mock monotonic：推进时间后 maybe_self_heal_monitor 被调用一次。"""
    ...
```

- [ ] **Step 4: Run desktop tests**

Run: `pytest tests/unit/test_api_runtime.py tests/unit/test_monitor_self_heal.py -v -m desktop`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/app.py src/media2text/api/services/runtime_health_loop.py tests/unit/test_api_runtime.py
git commit -m "feat(api): self-heal monitor on serve start and health loop"
```

- [ ] **Step 6: CHANGELOG**

`CHANGELOG.md` 增加一句：`auto_start_monitor` 在假锁场景下清锁并自启 embedded monitor。

---

### Task 8: 扩展 `recover-stale` API

**Files:**
- Modify: `src/media2text/api/services/work_queue.py`
- Modify: `src/media2text/api/services/runtime.py`

- [ ] **Step 1: `recover_stale_work` 调用 `recover_orphan_sessions`**

```python
from media2text.core.live.session_recovery import recover_orphan_sessions

def recover_stale_work(...):
    ...
    orphan = recover_orphan_sessions(cfg, conn)
    return {..., "orphan_sessions_recovered": orphan}
```

- [ ] **Step 2: Test via existing `POST /api/runtime/recover-stale`**

Run: `pytest tests/unit/test_api_runtime.py -v -k recover`（若无则加一条 assert `orphan_sessions_recovered` key）

- [ ] **Step 3: Commit**

```bash
git add src/media2text/api/services/work_queue.py
git commit -m "feat(api): recover-stale includes orphan live sessions"
```

---

## SH-3 — 脚本与文档

### Task 9: `monitor-watch-daemon.sh` 与文档

**Files:**
- Modify: `bin/monitor-watch-daemon.sh`
- Modify: `CLAUDE.md`（监控排错一节，3–5 行）
- Modify: `config.example.yaml`

- [ ] **Step 1: Replace shell stale check**

```bash
# bin/monitor-watch-daemon.sh — replace lines 14-20
.venv/bin/python -c "
from pathlib import Path
from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock
clear_invalid_monitor_lock(Path('data/.monitor-watch.lock'))
"
```

- [ ] **Step 2: Update CLAUDE.md** — 增加假锁症状与 `POST /api/runtime/takeover` / self-heal 配置说明

- [ ] **Step 3: Manual smoke**

```bash
echo 581 > data/.monitor-watch.lock
bin/monitor-watch-daemon.sh
# Expected: lock cleared or valid monitor started; pgrep -fl 'monitor watch'
```

- [ ] **Step 4: Commit**

```bash
git add bin/monitor-watch-daemon.sh CLAUDE.md config.example.yaml docs/superpowers/specs/2026-06-16-monitor-self-heal-design.md
git commit -m "docs: monitor self-heal ops and shell script fix"
```

---

## 全量验证

```bash
source .venv/bin/activate
pytest tests/unit/test_heartbeat.py tests/unit/test_monitor_lock.py tests/unit/test_process_lock.py \
  tests/unit/test_runtime_status.py tests/unit/test_monitor_supervisor.py \
  tests/unit/test_external_spawn.py tests/unit/test_session_recovery.py \
  tests/unit/test_monitor_self_heal.py tests/unit/test_api_runtime.py tests/unit/test_api_sessions.py -v -m desktop
ruff check src/media2text/core/runtime/heartbeat.py src/media2text/core/runtime/monitor_lock.py src/media2text/core/live/session_recovery.py
pyright src/media2text/core/runtime/monitor_lock.py src/media2text/api/services/monitor_self_heal.py
```

---

## Self-Review

| Spec 条目 | 对应 Task |
|-----------|-----------|
| SH1 假锁识别 | Task 0–1, 3, 4 |
| SH2 serve 自启 | Task 4, 7 |
| SH3 heartbeat（含 embedded 不掩盖） | Task 0, 1, 3 |
| SH4 孤儿场次 | Task 5, 8 |
| SH5 向后兼容 + JSON 写锁 | Task 1 `read_lock_pid`, Task 2 `acquire_workspace_lock` |
| SH6 冷却 + 小时滑动窗口 | Task 6 |
| `live status` `daemon_lock_valid` | Task 3 |
| `heartbeat_stale_sec` 下限 90s | Task 0 |
| TOCTOU `external_started` | Task 6 |

无 TBD / TODO 占位符。

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-16-monitor-self-heal-implementation.md`.**

设计规格（Eng Review 修订版）：`docs/superpowers/specs/2026-06-16-monitor-self-heal-design.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子 agent，Task 间做 review，迭代快  
2. **Inline Execution** — 本会话按 Task 顺序实现，每 PR 设检查点

你更倾向哪一种？确认后可以从 **SH-1 Task 0** 开始写代码。

---

## Eng Review（2026-06-16）

**结论：方向正确；计划已按推荐项修订，可进入实现。**  
**Step 0：** 范围接受（3 PR / 10 Task：新增 Task 0 `heartbeat.py`）  
**模式：** FULL_REVIEW | **commit:** `a8136b6` | **计划修订:** 2026-06-16

### 已采纳决策

| # | 议题 | 决议 | 计划落点 |
|---|------|------|----------|
| 1 | SH6 仅 cooldown vs 滑动窗口 | **采纳** — `monitor_self_heal_max_per_hour: 3` + `_heal_timestamps` | Task 6 |
| 2 | `thread_alive` 强制 `running=True` | **采纳否** — embedded heartbeat_stale 仍 `running=False` | Task 1, 3 |
| 3 | `live status --json` `daemon_lock_valid` | **采纳** — 本 Epic 一并交付 | Task 3 |

### 已修补计划缺口（相对初版）

| ID | 严重度 | 问题 | 修订 |
|----|--------|------|------|
| A1 | P1 | SH6 滑动窗口缺失 | Task 6 + spec §3.6 |
| A2 | P1 | `live status` 未覆盖 | Task 3 + `test_api_sessions.py` |
| A3 | P2 | JSON 写锁未接入 | Task 2 `acquire_workspace_lock` |
| A4 | P2 | `age>7200` mark_stale | Task 5 + 单测 |
| A5 | P2 | 循环依赖 | Task 0 `heartbeat.py` |
| A6 | P2 | embedded 掩盖 stale | Task 1/3 逻辑 + 单测 |
| — | P2 | `stale_sec` 边界抖动 | Task 0 `heartbeat_stale_sec(max(90,2×poll))` |
| — | P2 | TOCTOU | Task 6 `external_started` skip |
| — | **回归** | PID=581 假锁 | Task 1 `test_*_regression_581` |

### 仍明确 NOT in scope

- 纯 CLI 无 serve 的周期自愈（仅启动时 recovery + shell 脚本）
- Windows / Linux `ps` 行为专项验证
- DLQ 259 条 failed tasks 自动清理
- 磁盘 99% 与录制失败联动
- Desktop UI 横幅

### Completion summary（修订后）

| 项 | 结果 |
|----|------|
| Step 0 | 范围接受 |
| 待确认决策 | **3/3 已关闭** |
| Critical gaps | **已映射到 Task 0–6** |
| VERDICT | **CLEARED FOR IMPLEMENTATION** |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Runs | Status | Findings |
|--------|---------|------|--------|----------|
| Eng Review | `/plan-eng-review` | 1 | **plan_revised** | 8 issues → 已落 Task |
| CEO / Codex / Design / DX | — | 0 | — | Design N/A（无 UI） |

- **UNRESOLVED:** 0（实现方式 Subagent vs Inline 由用户选择）
- **VERDICT:** 计划已修订，可开始 SH-1 Task 0
