# Monitor / Live 架构精简 — Epic 验收

规格：[2026-07-06-monitor-live-simplify-refactor-design.md](../specs/2026-07-06-monitor-live-simplify-refactor-design.md)  
Epic manifest：[monitor-live-simplify-2026-07-06.yaml](../../issues/epic-manifests/monitor-live-simplify-2026-07-06.yaml)  
分支：`refactor/monitor-live-simplify` · 回退 tag：`pre-monitor-live-simplify`

> MLS-1 … MLS-11 已全部 squash merge（#398–#408）。本表在 Epic 合入 `main` 前填写。

## 规格验收（§7 S1–S6）

| ID | 验收项 | 命令/证据 | 状态 |
|----|--------|-----------|------|
| S1 | 主路径可读：`loop.py` + `session.py` | `loop.py` 166 行、`session.py` 281 行；`heavy_pool.py` 62 行 | [x] |
| S2 | G1 不退化（P95 检测→开录 ≤30s） | `pytest tests/unit/test_g1_recording_latency.py -v` | [x] |
| S3 | G5 保持（post-process 不拖 LiveTick） | `test_live_tick_not_blocked_by_slow_finalize`、`test_live_tick_not_blocked_by_finalize_drain` | [x] |
| S4 | 单元测试 + DB lock stress | `pytest tests/unit -m "not live"`：**938 passed / 31 failed**（见下方 Gap）；`test_db_lock_stress_smoke` | [ ] 部分 |
| S5 | `repos` 拆分；`recording.py` 变薄 | `repos/*.py` 均 <800 行；`recording.py` 1618 行（MLS-7 已抽 `session.py`，未删尽） | [x] 部分 |
| S6 | `core/monitor`/`core/live` 无 `import media2text.agent` | `! rg 'from media2text\.agent' src/media2text/core/monitor src/media2text/core/live` | [x] |

## Issue 闸门（MLS-1 … MLS-11）

```bash
for i in 387 388 389 390 391 392 393 394 395 397; do
  python scripts/issue_verify.py --issue $i
done
python scripts/issue_verify.py --issue 396  # 见 S4 Gap：全量 unit 有遗留失败
```

| Issue | PR | issue_verify |
|-------|-----|--------------|
| MLS-1 #387 | [#398](https://github.com/oychao1988/media2text/pull/398) | [x] |
| MLS-2 #388 | [#400](https://github.com/oychao1988/media2text/pull/400) | [x] |
| MLS-3 #389 | [#399](https://github.com/oychao1988/media2text/pull/399) | [x] |
| MLS-4 #390 | [#401](https://github.com/oychao1988/media2text/pull/401) | [x] |
| MLS-5 #391 | [#402](https://github.com/oychao1988/media2text/pull/402) | [x] |
| MLS-6 #392 | [#403](https://github.com/oychao1988/media2text/pull/403) | [x] |
| MLS-7 #393 | [#404](https://github.com/oychao1988/media2text/pull/404) | [x] |
| MLS-8 #394 | [#405](https://github.com/oychao1988/media2text/pull/405) | [x] |
| MLS-9 #395 | [#406](https://github.com/oychao1988/media2text/pull/406) | [x] |
| MLS-10 #396 | [#408](https://github.com/oychao1988/media2text/pull/408) | [ ] 全量 unit |
| MLS-11 #397 | [#407](https://github.com/oychao1988/media2text/pull/407) | [x] |

## Epic verify

```bash
python scripts/epic_verify.py monitor-live-simplify-2026-07-06
```

## S4 Gap（跟进 Issue MLS-12）

31 个 `tests/unit` 失败主要为 **MLS 前即存在的陈旧 mock**（如 `run_once`、`_emit_pipeline_notifications`）及 **legacy finalize/ffmpeg 夹具**，非 MLS issue 闸门回归。跟进：[mls12-stale-unit-tests](./monitor-live-simplify-mls12-stale-unit-tests.md) · [#410](https://github.com/oychao1988/media2text/issues/410)。

```bash
pytest tests/unit/test_task_scheduler.py tests/unit/test_probe_guard.py \
  tests/unit/test_live_loop_inline_prepare.py tests/unit/test_heavy_pool.py \
  tests/unit/test_g1_recording_latency.py tests/stress/test_db_lock_stress.py::test_db_lock_stress_smoke -v
```

## 灰度开关

- `live.inline_decisions: false`（默认）— 仍经 `reconcile_live` + `monitor_tasks`
- 启用内联：`live.inline_decisions: true`（MLS-8）

## 运维变更

- **creator_distill**：不再由 `SlowTickLoop` 自动 drain；使用 `media2text agent distill drain`（MLS-11）
- **Node sidecar**：已删除；Desktop agent 走 Python `/api/agent/*`（MLS-3/6）
