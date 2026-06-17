---
issue: 326
epic: live-recording-stability-2026-06-17
github: 326
branch: issue-326-lr2-probe-concurrency
depends_on: [325]
spec: docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md
---

# LR-2：Live probe 并发与 tick 预算（Playwright 锁争用）

## 背景

2026-06-17 监控无法开录：10 位 `monitor_enabled` 博主、`probe_parallelism: 4`，但 Playwright 全局信号量仅 **2** 槽、默认锁等待 **30s**。单 tick 内 4 路并行抢锁 → 大量 `failed to acquire Playwright exclusive lock within 30.0s`，整轮 live poll 超时，桌面端显示无直播。

**参考**：`src/media2text/core/live/probe.py`、`src/media2text/core/playwright_env.py`

## 复现步骤

1. `config.yaml` 设 `monitor.probe_parallelism: 4`（或默认 4），登记 ≥8 位抖音监控博主。
2. 启动 `monitor watch --daemon`，观察 `data/monitor-watch.log`。
3. 出现 Playwright lock timeout，当轮无 `live_recording_started`。

## 验收标准

### Task 1 — Worker 上限

- [ ] `probe_workers` 上限为 Playwright 槽位数（当前 2），`probe_parallelism` 再大也不超过槽位
- [ ] `run_live_probe_tick` 传入监控博主数量 `n_targets`，用于动态预算

### Task 2 — Tick 预算

- [ ] `probe_budget_sec` 随 `n_targets` 缩放（避免 10 博主 × 4 并行在固定 40s 内必然超时）
- [ ] 单元测试覆盖 worker cap 逻辑

### Task 3 — Probe 期间锁等待

- [ ] `ProbeExecutionGuard.is_active()` 时 Playwright 锁超时延长至 **90s**（仅 probe tick 内）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_task_scheduler.py -v -k probe
ruff check src/media2text/core/live/probe.py src/media2text/core/playwright_env.py
```

## 非目标范围

- 抖音解析 / HTTP / Playwright 匿名回退（见 LR-1 #325）
- HLS stall / reconnect（见 LR-3 #327）
- 修改 Playwright 槽位数配置项（保持代码常量 2）
- Desktop UI 展示

## 依赖与顺序

- **依赖**：#325（探测逻辑正确后再调并发）
- **建议分支**：`issue-326-lr2-probe-concurrency`

## GitHub

- Issue: [#326](https://github.com/oychao1988/media2text/issues/326)
