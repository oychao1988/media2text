---
issue: 369
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/369
branch: issue-369-monitor-session-sm-mh4a
depends_on: [dl4b]
---

# MH-4a：`SessionStateMachine` + Registry + recovery 规则

GitHub Issue: [#369](https://github.com/oychao1988/media2text/issues/369)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§5  
系列：DL-4b → **MH-4a** → MH-4b

## 背景

7/3 僵尸 session：`offline_since_at` 已设 + ffmpeg 死，但 `mark_stale` 因 `obs_ffmpeg_alive=0` 跳过，finalize 永不入队。用户决策：**全量 SessionStateMachine**，副作用仅留 `SessionRuntime`。

本 Issue 引入状态机 + recovery，**尚未**删除 `watcher._conn`（→ MH-4b）。

## 验收标准

### Task 1 — 核心类型

- [x] 新增 `src/media2text/core/live/session_state.py`：`SessionHandle`、`SessionStateMachine`、`SessionStateMachineRegistry`
- [x] 状态：`starting` / `recording` / `offline_pending` / `finalizing` / `completed` / `failed`（DB migration v9 若需新 status 值）
- [x] 所有 DB 迁移经 `gateway.write`；ffmpeg/STT 仅 `SessionRuntime`

### Task 2 — Recovery（修 #78 + 7/3）

- [x] `recover_all()` on daemon start：`offline_since_at` + dead ffmpeg → enqueue `finalize` priority 0（**不等** 2h）
- [x] 删除 `mark_stale_recordings_failed` 对 `obs_ffmpeg_alive==0` 的 skip
- [x] `recover_orphan_sessions` 委托 registry / 或合并进 `recover_all`

### Task 3 — poll_observation（与现有 core 并存）

- [x] `SessionStateMachine.poll_observation`：`write_obs` + still_live 检测接口
- [x] `LiveRecordingCore.poll_active_recordings` 可委托 registry（双路径过渡 OK）

### Task 4 — 测试

- [x] `tests/unit/test_session_state_machine.py`：状态迁移 offline_pending → finalizing
- [x] `tests/unit/test_session_recovery_offline_finalize.py`：**CRITICAL** 7/3 回归（offline + dead ffmpeg → finalize task）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_session_state_machine.py tests/unit/test_session_recovery_offline_finalize.py tests/unit/test_live_stale_poll_order.py -v
ruff check src/media2text/core/live/session_state.py src/media2text/core/live/session_recovery.py
```

## 非目标范围

- 删除 `MonitorWatcher._conn`（→ MH-4b）
- Worker 去 MH-3（→ MH-4c）
- `recording.py` 大删（→ MH-4d）

## 依赖与顺序

- **依赖 DL-4b**（gateway + P0 repos）；阻塞 MH-4b
