# Monitor / Live 架构精简重构

**日期:** 2026-07-06  
**状态:** Draft — 待 Eng Review  
**分支:** `refactor/monitor-live-simplify`  
**回退点:** tag `pre-monitor-live-simplify`（`5e81dde`）  
**前置:** [Live Pipeline v2](./2026-06-03-live-pipeline-v2-design.md)、[Monitor Daemon v3](./2026-06-05-monitor-daemon-observe-execute-design.md)、[WriteGateway + SessionSM](./2026-07-05-monitor-db-write-gateway-session-sm-design.md)、[HLS Segment Pipeline](./2026-06-09-live-segment-media-pipeline-design.md)  
**动机:** v1→v2→v3→MH-4 多层迁移叠加，直播链路存在 legacy/streaming 双轨、`reconcile`+`monitor_tasks` 间接调度、4 线程池、God file，维护成本高；个人 CLI 只需一条清晰路径。

---

## 0. 已锁定决策（本 spec 范围）

| # | 决策 | 理由 |
|---|------|------|
| D1 | **唯一推荐直播路径**：`streaming + hls + segment_pipeline + streaming_stt` | `config.example.yaml` 已推荐；doctor 对 legacy 警告 |
| D2 | **保留** `DbWriteGateway` + `SessionRuntime` | 解决真实 DB lock 事故（2026-07-03）；不回归 MH-3 |
| D3 | **保留** LiveTick 与重活隔离（G5） | post-process / Playwright 不得阻塞 probe |
| D4 | **直播不再经 `monitor_tasks` 间接调度** | `prepare`/`finalize`/`reconnect`/`stt` 在 `LiveLoop` 内联状态机决策 |
| D5 | **`monitor_tasks` 仅保留 content 慢任务** | sync_catalog / download / sync_dynamic |
| D6 | **三阶段交付**：减法 → 合并路径 → 架构收敛 | 可回退、可验收 |
| D7 | **旧 `live_sessions` legacy 场次只读收尾**，禁止新 legacy session | 数据迁移不阻塞代码删枝 |

未选方案（备查）：

- **Big-bang 重写 monitor** — 风险高，与 MH-4 刚交付冲突  
- **删 WriteGateway 回 open_db** — 会复现 DB lock  
- **单线程一切** — 违背 G5，post-process 会拖死 live poll  

---

## 1. 问题陈述

### 1.1 现状复杂度来源

```
维度叠乘：
  legacy | streaming  ×  flv | hls  ×  reconcile on/off  ×  gateway | with_db_lock_retry
```

| 组件 | 文件/规模 | 问题 |
|------|-----------|------|
| 调度 | `task_scheduler.py` + `task_reconciler.py` + `scheduler.py` | 观测→对账→入队→drain 四跳 |
| 录制 | `recording.py` ~1823 行 | legacy/streaming 双轨 + test re-export |
| 存储 | `repos.py` ~2750 行 | God file；`DesktopChatRepo` 依赖 agent |
| 平台 live | `douyin/live.py` `run_once` vs `run_probe_observe` | 双路径 |
| Agent | `packages/m2t-agent-sidecar` | M2 已迁 Python Hermes，Tauri 仅 spawn Python |

### 1.2 目标读者体验

维护者打开 `monitor watch` 相关代码时，应能沿 **一条主路径** 读完：

```
LiveLoop → LiveSession 状态机 → ffmpeg/HLS → finalize → post_process
```

---

## 2. 目标架构（精简后）

### 2.1 概念模型

```
┌─────────────────────────────────────────────────────────────┐
│                     MonitorDaemon (单进程)                      │
├─────────────────────────────────────────────────────────────┤
│  LiveLoop (~10s)                                            │
│    probe → snapshot → poll active → session.decide()        │
│    (开录/下播/重连 inline，不写 monitor_tasks)                 │
├─────────────────────────────────────────────────────────────┤
│  ContentLoop (动态间隔)                                        │
│    mark vod/archive/dynamic due → reconcile_content only    │
├─────────────────────────────────────────────────────────────┤
│  SchedulerTick (1s) — 变薄                                   │
│    drain HeavyPool + ContentPool + notify                   │
├─────────────────────────────────────────────────────────────┤
│  SegmentWatcher (1s, HLS only)                              │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   HeavyPool                      ContentPool
   finalize / segment_upload      sync / download / dynamic
   post_process (summarize…)      (Playwright 互斥)
```

### 2.2 LiveSession 状态机（合并 SessionSM + RecordingCore 核心）

```
                    ┌──────────┐
         probe      │  IDLE    │
        is_live ──►│(snapshot)│
                    └────┬─────┘
                         │ auto_record + start
                         ▼
                    ┌──────────┐
              ┌────►│ RECORDING│◄────┐
              │     └────┬─────┘     │ reconnect
              │          │ offline   │
              │          ▼ (45s)     │
              │     ┌──────────┐     │
              │     │ OFFLINE  │     │
              │     │ _PENDING │     │
              │     └────┬─────┘     │
              │          │ confirm   │
              │          ▼           │
              │     ┌──────────┐     │
              └─────│ FINALIZE │─────┘
                    │ (Heavy)  │
                    └────┬─────┘
                         ▼
                    ┌──────────┐
                    │ COMPLETE │
                    └──────────┘
```

### 2.3 与现状映射

| 现状 | 精简后 |
|------|--------|
| `TaskSchedulerLoop` + `reconcile_live` | `LiveLoop` 内 `LiveSession.decide()` |
| `monitor_tasks` live 类 | 删除；仅 content 任务 |
| 2× `MonitorExecutor` | `ContentPool`；live 重活进 `HeavyPool` |
| `SessionStateMachineRegistry` + `LiveRecordingCore` | `LiveSession`（分文件，非单类 1800 行） |
| `probe._run_live_probe_tick_legacy` | 删除 |
| `with_db_lock_retry` | 全走 `WriteGateway` |

---

## 3. 分阶段交付

### Phase 1 — 减法（低风险，~3 PR）

**目标：** 删死代码与废弃路径，不改变 daemon 主行为。

| 项 | 操作 | 验收 |
|----|------|------|
| P1-1 | 删 `run_poll_active_tick`（无调用方） | `pytest tests/unit/test_*probe*` |
| P1-2 | 删 `reconciler_log_only` 配置与分支 | 单测更新 |
| P1-3 | 强制 `reconciler_enabled=true`（删 false 分支与 `ReconcilerDisabledError` 对外语义保留一版 deprecated 日志） | `test_monitor_daemon_integration` |
| P1-4 | 删 `packages/m2t-agent-sidecar` + `start-sidecar.mjs` + bundle（保留 README 指向 Python agent） | Desktop `pnpm test` + agent turn |
| P1-5 | `config` + runtime：**新 session 拒绝 `pipeline_mode=legacy`**；旧场次只读 finalize | `test_live_legacy_pipeline` 收窄为 migration |
| P1-6 | 删 `offline_confirm_polls` 配置字段 | config 加载测试 |
| P1-7 | 删 `clear_snapshot_write_lock_for_tests` no-op | — |

**不删：** `_streaming_legacy_finalize`（STT 降级容错）、`WriteGateway`、`SegmentWatcher`。

### Phase 2 — 合并路径（中风险，~3 PR）

| 项 | 操作 | 验收 |
|----|------|------|
| P2-1 | `monitor watch`（无 `--daemon`）= 执行一轮 `LiveLoop` + 一轮 `SchedulerTick` | CLI 集成测试 |
| P2-2 | 平台 `LiveWatcher` 只保留 `run_probe_observe` + registry poll；删 `run_once` | 平台 live 单测 |
| P2-3 | `watcher._drain_priority_zero_tasks` 并入 scheduler 或删除（run_once 改后） | watcher 单测 |
| P2-4 | 去掉 `with_db_lock_retry`，`douyin/bilibili/live.py` 全走 gateway | `test_db_lock` / stress |
| P2-5 | Desktop `/api/chat/*` 调用迁 `/api/agent/*`，删 deprecated chat 路由 | desktop agent 测试 |

### Phase 3 — 架构收敛（较大，~4 PR）

| 项 | 操作 | 验收 |
|----|------|------|
| P3-1 | 引入 `core/live/session.py`（`LiveSession`），从 `recording.py` 迁 prepare/poll/offline | 录制单测不变绿 |
| P3-2 | `reconcile_live` 直播部分删除；`LiveLoop.decide()` 内联 | G1 指标不退化 |
| P3-3 | 合并 `HeavyPool`（finalize + segment + post_process claim） | `live stats` |
| P3-4 | 拆 `repos.py` → `repos/{creator,live,monitor,cloud}.py` | import 无环 |
| P3-5 | `creator_distill` 从 `SlowTickLoop` 抽出为可选 cron/CLI，断 core→agent 依赖 | monitor 单测无 agent import |

---

## 4. 模块目标结构

```
src/media2text/core/
  monitor/
    daemon.py          # 锁、信号、启动（原 watcher.run_daemon 变薄）
    content_loop.py    # 原 SlowTick 内容部分
  live/
    loop.py            # 原 LiveTick + reconcile_live 决策
    session.py         # 状态机 + 录制副作用边界
    finalize.py        # 仅 streaming+hls（legacy 在 P1 后删除）
    hls.py             # recorder + segment_watcher
    stt.py             # streaming STT
    heavy_pool.py      # finalize / segment / post_process submit
  jobs/
    content.py         # monitor_tasks content 专用
  storage/repos/       # 按域拆分
```

**删除或大幅变薄：**

- `task_reconciler.reconcile_live`（P3）
- `task_scheduler.py` 内 live claim 逻辑（P3）
- `recording.py` 主体（P3 迁至 session + hls + stt）
- `platform/*/live.py` 的 `run_once`

---

## 5. 配置契约（精简后）

```yaml
live:
  pipeline_mode: streaming          # legacy 新 session 拒绝
  media:
    format: hls                     # flv 路径 P1 后删除
  segment_pipeline:
    enabled: true
  streaming_stt:
    enabled: true
  transcribe_on_complete: false

monitor:
  scheduler_interval_sec: 1
  # reconciler_enabled / reconciler_log_only — P1 删除
```

---

## 6. 非目标

- 多进程 / Redis / 外部队列  
- 删 `WriteGateway` 或跨进程 Desktop 事件模型  
- B 站 / 抖音平台适配重写  
- Agent Hermes 内核重写  

---

## 7. 验收标准

| ID | 指标 | 目标 |
|----|------|------|
| S1 | 主路径文件数 | 维护者读 `loop.py` + `session.py` 可理解全流程 |
| S2 | G1 不退化 | P95 检测→开录 ≤ 30s |
| S3 | G5 保持 | post-process 20min 时 LiveLoop 仍 ~10s |
| S4 | 测试 | `pytest tests/unit -m "not live"` 全绿；`test_db_lock_stress` 通过 |
| S5 | 代码量 | Phase 3 后 `recording.py` 删除；`repos.py` < 800 行/文件 |
| S6 | 依赖 | `core/monitor` 与 `core/live` 无 `import media2text.agent` |

---

## 8. 回退策略

```bash
# 回退到重构前代码
git checkout main
# 或
git checkout pre-monitor-live-simplify

# 放弃 refactor 分支
git branch -D refactor/monitor-live-simplify
```

每 Phase 独立 PR；任一 Phase 验收失败可 revert 该 PR 而不回滚整个 Epic。

---

## 9. Issue 拆分建议

| Issue | Phase | 标题 |
|-------|-------|------|
| #TBD | P1 | monitor-live-simplify: delete dead code and legacy new-session guard |
| #TBD | P1 | remove m2t-agent-sidecar package |
| #TBD | P2 | unify monitor watch single-round with daemon tick |
| #TBD | P2 | gateway-only DB writes in platform live watchers |
| #TBD | P3 | LiveLoop inline session decisions (drop reconcile_live) |
| #TBD | P3 | split repos.py by domain |

---

## 10. 风险

| 风险 | 缓解 |
|------|------|
| Phase 3 改动面大 | Phase 1/2 先减枝；feature flag `live.inline_decisions` 灰度一周 |
| 旧 legacy 场次 finalize 失败 | P1 只禁新 session；旧数据走只读 finalize 至清空 |
| G1 回归 | 每 PR 跑 `test_g1_recording_latency` + 手动 smoke |
| Desktop agent 断链 | P1 sidecar 删除前确认 `useM2tAgent` 全走 `/api/agent` |
