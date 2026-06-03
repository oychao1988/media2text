# Live Pipeline v2 — 及时、隔离、可回溯

**日期:** 2026-06-03  
**状态:** P0–P3 已交付（#81–#87）；收尾见 #92–#95  
**前置:** [2026-06-02-live-recording-pipeline plan](../plans/2026-06-02-live-recording-pipeline.md)（v1）

**实现与验收:** P0–P3 按本 spec 编码；收尾工单 [#92](https://github.com/oychao1988/media2text/issues/92)–[#95](https://github.com/oychao1988/media2text/issues/95)；手动验收见 [verification](../verification/2026-06-03-live-pipeline-v2-acceptance.md)

---

## 0. 已锁定决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 架构方案 | **进程内三线程**（LiveTick / SlowTick / PostProcessPool） | 改动小、满足隔离目标、延续 v1 `LiveRecordingCore` |
| 下播确认策略 | **A — 墙钟 45s**（`offline_confirm_sec: 45`） | 首次 offline 立即 `live_ended`；满 45s 仍 offline 才 finalize；平衡误停与延迟 |
| 检测间隔 | LiveTick **10s** | 配合 G1（检测→开录 P95 ≤30s） |
| SQLite 连接（D1） | **每线程 / 每 job 独立 `open_db()`** | WAL 已启用；PostProcessPool worker 不得共享 LiveTick 的 connection |
| PostProcessPool DB 边界（D2） | **可写 transcribe/upload 列；禁止改录制中状态** | 不得改 `status=recording`、`ffmpeg_pid`、offline 相关列 |
| G3 语义（D3） | **首次「检测到」offline 后 ≤5s 发 `live_ended`** | 受 LiveTick 10s 间隔约束；非平台真实下播时刻 |
| P0 独立发布（D4） | **允许** | P0 仅解锁 G5 + G1 基础；G3/G4 需 P1，release note 须说明 |
| VOD 限流默认（D5） | **`max_creators_per_vod_tick: 2`** | `config.example.yaml` 与文档默认；0 仍表示不限制 |
| 实现范围 | **spec 已批准，按 plan 编码** | 本文档为唯一设计源；实现按 plan 分 P0–P3 |

未选方案（记录备查）：

- **B** 30s 确认：更激进，API 抖动时误截断风险更高  
- **C** 首次 offline 即停录：最快，但尾段丢失不可接受

---

## 1. 问题陈述

当前 `monitor watch --daemon` 在**单线程**内顺序执行：

```
live poll → post-process drain（转写+摘要+云盘，可达 20+ min）
         → VOD Playwright sync（N 博主 × 30–60s）
         → archive / dynamic → sleep(live_poll)
```

实测（2026-06-03 生产日志）：名义 `live_poll_interval_sec: 20`，B 站状态检查有效间隔 **~10 分钟**；`offline_confirm_polls: 3` 按 **poll 次数** 计，停录与 `recording_completed` 通知被成倍放大。

根因：

1. **Live tick 与慢任务共线程** — post-process / VOD 阻塞 poll  
2. **offline 按次数而非时间** — poll 稀疏时 streak 极慢  
3. **无 pipeline 事件流** — 只有离散通知，无法量化各阶段耗时  
4. **后处理串行、与 live 耦合** — 多场直播互相拖累  

---

## 2. 目标（Success Criteria）

| ID | 指标 | 定义 | 目标值 | 验收方式 |
|----|------|------|--------|----------|
| G1 | 检测→开录 | `recording_started_at - first_seen_live_at` | P95 ≤ **30s** | `live timeline --json` / events 表 |
| G2 | 检测→提醒 | `live_started` 或 `live_start_failed` | 开录尝试后 **≤5s** | 通知 + `recording` event |
| G3 | 下播→提醒 | `live_ended` | 首次**检测到** offline 后 **≤5s** | 通知 + `offline_since_at` 写入 |
| G4 | 下播→停录 | `recording_completed` | offline 确认 + remux **≤60s** | 默认 45s confirm + remux 余量 |
| G5 | 隔离 | 单场 post-process / VOD | **不增加** LiveTick 周期 | 压测：drain 20min 时 live tick 仍 ~10s |
| G6 | 并行 | 多路后处理 | 可配置；默认 CPU 自适应 | `live status --json` 显示 pool |
| G7 | 可回溯 | 单场全链路 | 每阶段起止 + duration_ms + error | `live timeline <session_id>` |
| G8 | 可进化 | 聚合延迟 | P50/P95 按 stage | `live stats --days N` |

**代理指标说明：** 平台 API 通常无「真实开播/下播时刻」。G1 以 `first_seen_live_at`（首次 `is_live=true`）为基准；G3 以 LiveTick **首次 poll 到 offline** 为基准（最坏额外延迟 ≈ 一个 poll 间隔，默认 10s）。若 API 返回 `live_start_time` / `room_create_time` 则写入 `live_sessions.platform_live_started_at` 供事后对齐。

---

## 3. 非目标（v2 不做）

- 平台 Webhook / 推送式开播  
- Redis、Celery、多机调度  
- 录播中实时转写  
- 改动 VOD/archive/dynamic 业务逻辑（仅迁到 SlowTick，行为不变）  

---

## 4. 架构

### 4.1 选定方案：进程内三线程

```
┌──────────────────────┐
│   Main / run_daemon   │  持锁、信号、优雅退出
└──────────┬───────────┘
           │ spawns
     ┌─────┴─────┬─────────────┬──────────────────┐
     ▼           ▼             ▼                  ▼
 LiveTick    SlowTick    PostProcessPool
  ~10s        300s+       ThreadPoolExecutor
     │           │             │
     │  douyin/bilibili        │ run_post_process_job
     │  run_once only          │ (per job: open_db → work → close)
     │  claim jobs → submit    │
     └───────────┴─────────────┘
                    │
         SQLite WAL (每线程独立 connection)
    live_sessions | post_process_jobs | live_pipeline_events
```

| 组件 | 职责 | 禁止 |
|------|------|------|
| **LiveTickThread** | `poll_active` + `scan_and_start`；claim pending jobs 并 **submit** 到 pool（不 wait） | VOD、Playwright sync、阻塞式 drain |
| **SlowTickThread** | VOD / archive / dynamic，各自 `*_poll_interval_sec` | 阻塞 LiveTick |
| **PostProcessPool** | `run_post_process_job` 在线程池执行；**每个 worker 内 `open_db()`** | 修改 `recording` / `ffmpeg_pid` / offline 计时列；可更新 transcribe、upload 相关列 |

**锁与 DB：** 仍用 `data/.monitor-watch.lock` 单实例。**已锁定（D1）：** LiveTick、SlowTick、每个 post-process worker 各持独立 connection（`open_db()`）；底层已有 WAL + `check_same_thread=False`。要求短事务、claim 后立即 commit，避免 `database is locked`。

### 4.2 单场生命周期（时序）

```
时间轴 ──────────────────────────────────────────────────────────────►

[API live] first_seen_live_at
    ├─ event: detected_live
    ├─ event: stream_resolve (起)
    ├─ ffmpeg start → recording_started_at
    ├─ notify: live_started
    └─ event: recording (started)

[API offline] 第一次
    ├─ offline_since_at := now
    ├─ notify: live_ended          ◄── G3：立即
    └─ event: recording (offline_pending)

[API offline] 持续，now - offline_since >= 45s
    ├─ stop ffmpeg → remux
    ├─ event: remux (completed)
    ├─ notify: recording_completed ◄── G4：约 offline+45s + remux
    └─ enqueue post_process_jobs

[PostProcessPool] 异步
    ├─ transcribe → notify transcribe_completed
    ├─ summarize  → notify summarize_completed
    └─ cloud_upload → notify upload_completed | upload_failed
```

**API 恢复 live（offline 误报）：**

- 清空 `offline_since_at`  
- event: `recording` status `offline_cancelled`  
- **不**发用户通知（仅 debug log）；继续录制  

---

## 5. 下播确认（策略 A，已锁定）

### 5.1 行为

| 步骤 | 条件 | 动作 |
|------|------|------|
| 1 | 录制中，API `is_live=false`，且 `recording_age >= min_recording_sec_before_offline_end`（默认 45s） | 若 `offline_since_at` 为空 → 设为 now，发 `live_ended` |
| 2 | 同上，且 `now - offline_since_at >= offline_confirm_sec`（**45**）且仍 offline | `_finalize_recording` |
| 3 | API 恢复 `is_live=true` | 清空 `offline_since_at`，继续录 |

### 5.2 与 v1 差异

| v1 | v2 |
|----|-----|
| `offline_confirm_polls: 3` | **`offline_confirm_sec: 45`**（主） |
| 首次 offline 无通知 | **`live_ended` 立即通知** |
| streak 受 poll 间隔影响 | 墙钟，与 poll 间隔解耦（poll 只影响检测精度） |

### 5.3 配置迁移

```yaml
live:
  offline_confirm_sec: 45          # 新，主控项
  offline_confirm_polls: 3         # deprecated；仅当 offline_confirm_sec 未设置时：
                                   #   offline_confirm_sec = polls * live_poll_interval_sec
  min_recording_sec_before_offline_end: 45  # 开播后前 45s 忽略 offline（防闪断）
```

**G4 推导：** 45s confirm + remux 通常 &lt;15s → `recording_completed` 约在末次「真 offline」后 **45–60s**，满足目标。

---

## 6. 数据模型

### 6.1 `live_sessions` 新增列

| 列 | 类型 | 说明 |
|----|------|------|
| `first_seen_live_at` | TEXT ISO8601 | 本场首次 API 报 live |
| `recording_started_at` | TEXT | ffmpeg 成功启动 |
| `offline_since_at` | TEXT nullable | 当前 offline 确认窗口起点 |
| `platform_live_started_at` | TEXT nullable | API 若提供则写入 |

保留 v1：`offline_streak` 列可废弃不删（迁移兼容），逻辑不再读取。

### 6.2 `live_pipeline_events`（新表）

```sql
CREATE TABLE IF NOT EXISTS live_pipeline_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  job_id TEXT,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  duration_ms INTEGER,
  FOREIGN KEY (session_id) REFERENCES live_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_lpe_session ON live_pipeline_events(session_id, started_at);
CREATE INDEX IF NOT EXISTS idx_lpe_stage ON live_pipeline_events(stage, started_at);
```

**stage 枚举（封闭集合）：**

| stage | status 示例 | detail_json 示例 |
|-------|-------------|------------------|
| `detected_live` | completed | `{"room_id":"..."}` |
| `stream_resolve` | completed / failed | `{"error":"..."}` |
| `recording` | started / completed / failed / offline_pending / offline_cancelled | |
| `remux` | completed / failed | `{"sources":1,"bytes":...}` |
| `transcribe` | completed / failed / skipped | `{"engine":"deepgram"}` |
| `summarize` | completed / failed / skipped | `{"model":"..."}` |
| `cloud_upload` | completed / failed / skipped | `{"path":"..."}` |

写入规则：阶段开始 insert `status=started`；结束 update `ended_at` + `duration_ms`。失败时 `status=failed` + `detail_json.error`。

### 6.3 `post_process_jobs`

沿用 v1；`stage` 字段与 events 表同步更新（实现时双写，CLI 优先读 events）。

---

## 7. 通知

### 7.1 事件种类（新增 bold）

| kind | 触发 | 默认 enabled |
|------|------|--------------|
| `live_started` | ffmpeg 启动成功 | yes |
| **`live_start_failed`** | resolve/ffmpeg 失败 | yes |
| **`live_ended`** | 首次 API offline（确认窗口开始） | yes |
| `recording_completed` | remux 完成 | yes |
| `transcribe_completed` | 转写完成 | yes |
| **`summarize_completed`** | 摘要完成 | yes |
| `upload_completed` / `upload_failed` | 云盘 | yes |
| `live_resumed` | offline 误报后恢复 | **no**（仅 log） |

### 7.2 与 pipeline events 关系

- 通知 = 用户-facing 里程碑  
- events = 全量审计（含失败、skipped、重试）  
- 两者通过 `session_id` 关联，不要求一一对应  

---

## 8. 配置（`config.yaml` / `config.example.yaml`）

```yaml
live:
  # --- v2 检测 ---
  live_poll_interval_sec: 10       # 仅 LiveTick；原 monitor.live_poll_interval_sec 作回退
  scan_concurrency: 4              # 无 active session 的博主并行 get_live_room

  # --- v2 下播（策略 A）---
  offline_confirm_sec: 45
  min_recording_sec_before_offline_end: 45

  # --- v2 后处理隔离 ---
  post_process_poll_interval_sec: 10   # LiveTick 内 claim 间隔（只 submit，不 wait）
  post_process_max_parallel: 0         # 0 = auto: min(2, max(1, cpu_count // 2))
  post_process_queue_warn_depth: 5

  # --- deprecated v1 ---
  offline_confirm_polls: 3             # 见 §5.3 迁移

monitor:
  vod_poll_interval_sec: 300           # 建议用户酌情调大（如 900）减 SlowTick 负载
  max_creators_per_vod_tick: 2         # v2 建议默认 2，避免 9 博主一次 sync 卡 10min

notify:
  enabled: true
  events:                              # 可选细粒度开关（实现时支持）
    live_started: true
    live_start_failed: true
    live_ended: true
    recording_completed: true
    transcribe_completed: true
    summarize_completed: true
    upload_completed: true
    upload_failed: true
```

---

## 9. CLI（`--json` 优先）

| 命令 | 用途 |
|------|------|
| `media2text live status [--creator ID] --json` | 当前 recording、pending/running jobs、pool 状态 |
| `media2text live timeline <session_id> --json` | 单场 events 有序列表 + 各段 duration_ms |
| `media2text live stats [--days 7] --json` | 聚合 G1/G3/G4 等 P50/P95 |
| `media2text post-process status [--session ID] --json` | 队列深度、失败 job（v1 已有 run，v2 增 status） |
| `media2text post-process retry <job_id> --json` | 失败 job 重试（P2） |

**`live status` JSON 形状（规范）：**

```json
{
  "ok": true,
  "daemon_lock_pid": 70961,
  "live_tick": {"interval_sec": 10, "last_tick_at": "..."},
  "active_recordings": [{
    "session_id": "...",
    "creator_id": "...",
    "display_name": "...",
    "started_at": "...",
    "recording_age_sec": 3600,
    "offline_since_at": null,
    "ffmpeg_pid": 12345
  }],
  "post_process": {
    "max_workers": 2,
    "pending": 1,
    "running": 1,
    "jobs": [{"job_id": "...", "session_id": "...", "stage": "transcribe", "queued_sec": 120}]
  }
}
```

---

## 10. 错误处理与重试

| 场景 | 行为 |
|------|------|
| `stream_resolve` 失败 | event failed + `live_start_failed`；下轮 tick 重试（已有 room_id 可跳过 profile 检测） |
| ffmpeg 早退 | v1 重连逻辑不变；events 记录 |
| post-process 任阶段失败 | job `failed`；**不影响**其他 job 与 live tick；支持 `post-process retry` |
| LiveTick 未捕获异常 | log exception；下轮继续（不 exit daemon） |
| SQLite 忙 | 短重试；WAL 模式 |

---

## 11. 测试策略

| 层级 | 覆盖 |
|------|------|
| 单元 | offline 墙钟 45s、offline 取消、events repo、scheduler 不阻塞、parallel scan mock |
| 单元 | PostProcessPool submit 非阻塞 |
| 集成 | FakeAdapter 时间线：live→offline 50s→finalize；live→offline 10s→live 恢复 |
| 回归 | v1 `test_live_recording_core` / `test_monitor_watcher` 扩展 |
| 手动 | §12 验收清单 |

---

## 12. 验收清单（实现后）

- [x] 转写进行中 LiveTick 日志间隔仍 ~10s（grep `live_recording` / bilibili status）  
- [x] 首次 offline 5s 内收到 `live_ended`（最坏 +1× poll 间隔）  
- [x] 持续 offline ≥45s 后收到 `recording_completed`  
- [x] 两场重叠 live 互不影响 poll（三线程隔离）  
- [x] `live timeline` 含 detected_live → recording → remux → transcribe 全链（`stream_resolve` 见 #93）  
- [x] `live stats` 输出 stage P50/P95  

详见 [2026-06-03-live-pipeline-v2-acceptance.md](../verification/2026-06-03-live-pipeline-v2-acceptance.md)。

---

## 13. 分期交付

| 阶段 | 交付物 | 解锁目标 |
|------|--------|----------|
| **P0** | LiveTickThread + SlowTickThread + PostProcessPool | G5、G1 基础 |
| **P1** | offline_confirm_sec + live_ended + 新 notify | G3、G4 |
| **P2** | live_pipeline_events + live CLI | G7 |
| **P3** | scan_concurrency + adaptive workers + stats | G6、G8 |

每阶段独立可 merge；P0 为最小可感知改进。

**P0 单独 merge 时（D4）：** CHANGELOG / release note 须写明：下播通知与墙钟停录仍沿用 v1 行为（poll 次数 offline streak），**G3/G4 在 P1 才达标**；P0 主要修复 live poll 被 post-process / VOD 阻塞（G5）。

---

## 14. 附录

### A. v1 plan 缺口

| v1 计划 | 现状（2026-06-03 后） | v2 |
|---------|------|-----|
| background worker thread | PostProcessPool 已交付 | P0 |
| fast live poll | 三线程隔离；默认 10s（#94） | P0 + 收尾 |
| offline streak | 墙钟 45s | P1 |
| 可观测性 | events + `live` CLI | P2 |

### B. 参考日志（2026-06-03）

- 场次 `a9858d2b`：offline_streak=3 才 finalize；有效 poll ~10min → 停录严重滞后  
- post-process 同场：recording_completed 08:26 → upload 08:48（22min），期间 loop 阻塞  

### C. 文档同步（实现时）

- `CLAUDE.md`：daemon 三线程、新 CLI、配置项  
- `README.md`：用户可见通知时序  
- `config.example.yaml`：§8 字段  

---

**Spec 版本:** 1.2  
**最后更新:** 2026-06-03  
**批准:** 下播策略 A（45s）；/plan-eng-review D1–D5 已采纳；可以 P0 开工。
