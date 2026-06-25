---
issue: 348
epic: monitor-hardening-2026-06-26
github: 348
branch: issue-348-monitor-hardening-mh4
depends_on: [345, 346, 347]
---

# MH-4：daemon 守卫 + run_once 对齐 + 集成测 + G1 benchmark

GitHub Issue: [#348](https://github.com/oychao1988/media2text/issues/348)  
Epic：**Monitor Hardening**（2026-06-26）  
系列：MH-1 → MH-2 → MH-3 → **MH-4**（Epic 验收闸门）

## 背景

- `reconciler_enabled=false` 时 daemon 仅 warning 继续跑，但 legacy enqueue 已移除 → **静默不失效**
- `MonitorWatcher.run_once`（非 `--daemon`）仍 inline `_drain_monitor_tasks_sync(max_rounds=100)`，与四线程 daemon 语义分叉，调试「单次 OK、daemon 不行」困难
- 缺跨线程集成测；G1（自动开录 P95 ≤30s）在纯异步 TaskScheduler 路径下需数据证明（eng review D4B + benchmark 本 PR）

**参考**

- Spec §5.2 G1；eng review D7、D8、D9
- Prior GF-3：`run_once` debug-only 张力 — 本 Issue 明确「对齐 observe+reconcile+p0，不恢复 sync 开录」

## 验收标准

### Task 1 — `reconciler_enabled=false` 拒绝启动

- [x] `MonitorScheduler.start` 或 `MonitorWatcher.run_daemon`：若 `not cfg.monitor.reconciler_enabled` → 抛清晰错误或 CLI exit 1，消息含 `set monitor.reconciler_enabled=true`
- [x] `reconciler_log_only=true` 且 `reconciler_enabled=true` 仍允许（shadow 模式）
- [x] `test_monitor_scheduler` 或 CLI 测覆盖 refuse 路径

### Task 2 — `run_once` 对齐 daemon

- [x] 非 daemon `run_once`：live 路径与 daemon 一致（probe 语义 + reconcile 可调用或等价标记 due）；**移除** 100 轮全 priority sync drain
- [x] 可选保留：单次 CLI 下 inline drain **仅** priority=0（finalize），用于调试
- [x] 文档/CLI help 一句说明：`monitor watch` 无 `--daemon` 为单轮调试，生产用 `--daemon`

### Task 3 — `test_monitor_daemon_integration.py`

- [x] 启动 `MonitorScheduler` 数秒（mock `run_live_probe_tick` 写 `is_live=1`）
- [x] 断言 `reconcile_live` 入队 `prepare_live_recording` 且 live pool claim/submit 被调用
- [x] 断言 MH-2：A 在录时 B 的 content task 仍可 drain（若 MH-2 已合并）
- [x] 使用短 `scheduler_interval_sec` / `live_poll_interval_sec`，避免 flaky

### Task 4 — G1 benchmark

- [x] 脚本或 pytest（`-m live` 可选）：从 `live_pipeline_events` 或 mock timeline 度量 `detected_live` → `recording_started` P95
- [x] 输出 JSON 摘要写入测试 log 或 `docs/superpowers/verification/` 附录；**门槛** P95 ≤ 30s（mock 环境可放宽并注明）
- [x] README 或 spec 脚注：纯异步路径（无 LiveTick inline drain）的实测值

### Task 5 — 手动 smoke 清单（TODOS）

- [x] 在 `TODOS.md`（新建若不存在）追加 MP Epic 手动项 4 条（见 [2026-06-25-monitor-db-contention-acceptance.md](../superpowers/verification/2026-06-25-monitor-db-contention-acceptance.md) §手动）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_monitor_daemon_integration.py tests/unit/test_g1_recording_latency.py tests/unit/test_monitor_cli_reconciler.py tests/unit/test_live_scheduler.py tests/unit/test_task_scheduler.py tests/unit/test_monitor_watcher.py -v
python scripts/issue_verify.py --issue 348
ruff check src/media2text/cli/monitor.py src/media2text/core/monitor/watcher.py src/media2text/core/live/scheduler.py
```

## 非目标范围

- LiveTick inline drain priority≤1（eng review D4 已拒绝）
- `open_db()` migration 单次化（MH-5）
- 新 Desktop 功能

## 依赖与顺序

- **依赖**：MH-1、MH-2、MH-3 合并后开 PR
- Epic 验收：`python scripts/epic_verify.py monitor-hardening-2026-06-26`
