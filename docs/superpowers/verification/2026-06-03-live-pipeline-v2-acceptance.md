# Live Pipeline v2 — 最终验收报告

**日期:** 2026-06-03  
**基线:** `main` @ PR #82–#88（Issues #81–#87 CLOSED）  
**环境:** 本机 `config.yaml`，守护进程 PID 32298（`monitor watch --daemon --json`）  
**日志:** `data/monitor-watch-stdout.log` / `stderr.log`（非 `monitor-watch.log`）

## 总 verdict

| 类别 | 结论 |
|------|------|
| **代码与 CI** | **通过** — `pytest` 188 passed |
| **P0/P2/P3 运行时** | **通过** — 三线程调度、live tick 隔离、CLI、事件表 |
| **P1 下播时序（G3/G4）** | **延后** — 本场为守护重启收尾，非 API 自然下播 |
| **G1 检测→开录** | **延后** — 收尾场次 `first_seen_live_at` / `recording_started_at` 为空（旧进程开录） |
| **完整后处理 E2E** | **通过** — 两场均 remux→transcribe→summarize→cloud_upload 完成（见下） |

**签署建议:** v2 **验收通过**（代码 + 运行时 + 两场 E2E）。G3/G4/G1 仍建议下一场**自然下播**直播补验。

**E2E 完成时间（UTC）:** 老曹 cloud_upload `12:11:51`；满江宏 `12:30:23`；队列 `running=0` @ `12:30:34`。

---

## 自动化

```bash
pytest tests/ -q   # 2026-06-03: 188 passed in ~11s
```

相关单测：`test_live_scheduler`、`test_live_status_cli`、`test_pipeline_events`、`test_offline_wall_clock`、`test_post_process_pool` 等。

---

## 计划 § Verification checklist

### 1. Live tick 在转写期间仍 ~poll 间隔（G5）

| 项 | 结果 |
|----|------|
| 配置 `live_poll_interval_sec` | **20**（非计划示例 10，仍满足「不卡 10 分钟」） |
| 守护启动 | `2026-06-03T11:33:29Z`，`post_process_poll: 10` |
| B 站频控日志间隔（代理 live tick） | n=34，**p50≈22s**，min 21s / max 90s |
| 转写进行中 | `transcribe_completed` @ 11:37:22 后 B 站 check 仍 ~21–22s 一档 |

**结论:** **通过** — 后处理占用 worker 时 LiveTick 未退回 ~10min 周期。

### 2. 下播：`live_ended` ≤5s，`recording_completed` ≤ confirm+remux（G3/G4）

| 项 | 结果 |
|----|------|
| 本场结束方式 | 19:33 **重启守护**，ffmpeg 被收尾，非 poll 检测 offline |
| `live_ended` 通知 | 日志 **无** |
| `offline_since_at` | DB **空** |
| remux → `recording_completed` | 11:33:38 / 11:33:45（重启后 **&lt;10s**） |

**结论:** **未验**（场景不适用）。跟进：下一场自然下播 + `config.yaml` 增加 `offline_confirm_sec: 45`。

### 3. 双主播重叠 + 后处理不拖慢另一路 poll（G5 扩展）

| 项 | 结果 |
|----|------|
| 同时录制 | 老曹 10:09Z、满江宏 10:51Z 开播，各 ffmpeg 存活至重启 |
| 重启后并行 remux | 两场约 8s / 5s 完成 |
| 后处理 | `max_workers: 1`；一场 transcribe 时 live tick 仍 ~20s |

**结论:** **通过**（重叠录制与隔离）；并行 worker 数为配置选择，非缺陷。

### 4. `media2text live status --json`（G6/G7）

```json
{
  "daemon_lock_pid": 32298,
  "live_tick": { "interval_sec": 20 },
  "active_recordings": [],
  "post_process": {
    "max_workers": 1,
    "pending": 0,
    "running": 2,
    "jobs": [ "... remux/transcribe/summarize stages ..." ]
  }
}
```

**结论:** **通过** — 字段齐全；`running: 2` 表示两 job 已 claim，线程池 `max_workers: 1` 串行执行属预期。

### 5. `media2text live timeline <session_id> --json`（G7/G8）

**Session `5ca1d108`（老曹）**

| stage | status | duration_ms |
|-------|--------|-------------|
| remux | completed | 8283 |
| transcribe | completed | 213213 |
| summarize | started | — |

**Session `1ee19302`（满江宏）**

| stage | status | duration_ms |
|-------|--------|-------------|
| remux | completed | 5163 |

**`live stats --days 1`:** remux×2 p50 6723ms；transcribe×1 p50 213213ms。

**结论:** **通过** — 两场全链路已完成（见 § E2E 收尾）。

### E2E 收尾（2026-06-03 续验）

| Session | remux | transcribe | summarize | cloud_upload |
|---------|-------|------------|-----------|--------------|
| 老曹 `5ca1d108` | 8.3s | 213s | 1627s | 442s |
| 满江宏 `1ee19302` | 5.2s | 129s | 796s | 185s |

串行 worker（`max_workers: 1`）：满江宏 transcribe 在 12:11:51 启动（老曹 upload 结束后），符合预期。

`live stats --days 1`（队列清空后）：remux×2、transcribe×2、summarize×2、cloud_upload×2，含 p50/p95。

---

## Spec 目标对照

| ID | 验收结论 | 证据摘要 |
|----|----------|----------|
| G5 隔离 | **通过** | stdout 日志 tick p50≈22s during post-process |
| G6 并行 | **通过** | `PostProcessExecutor` + status JSON |
| G7 可回溯 | **通过** | `live_pipeline_events` + timeline |
| G8 统计 | **通过** | `live stats --days 1` |
| G2 开录提醒 | **未单独计量** | 有 `live_started` notify（10:09/10:51） |
| G3/G4 下播 | **延后** | 重启收尾场景 |
| G1 30s 开录 | **延后** | 缺 `first_seen_live_at` 列数据 |

---

## 环境与风险

| 项 | 状态 |
|----|------|
| `doctor` | ffmpeg/会话 OK；`playwright_browser: false` |
| 重启旧进程 TypeError | `first_seen_live_at` 列 vs 旧代码；新守护 11:33 后正常 |
| B 站 `-799` 频控 | 预期内；不影响抖音 live tick |
| 本地 `config.yaml` | 仍 `offline_confirm_polls: 3`；代码默认 **已用** `offline_confirm_sec=45` |

---

## 跟进验收（下一场直播，约 15 分钟）

1. `config.yaml`：`live.offline_confirm_sec: 45`（可删或保留 deprecated `offline_confirm_polls`）。
2. 可选：`live_poll_interval_sec: 10`、`post_process_max_parallel: 0`。
3. 保持守护：`data/monitor-watch-stdout.log`。
4. 下播后检查：
   - `grep live_ended` / `notify_emitted.*live_ended`
   - `recording_completed` 在首次 offline 后 ≤60s
   - `live timeline` 含 `live_ended` 相关 stage/notify
5. 开录新场：`first_seen_live_at` 与 `recording_started_at` 差值 ≤30s。

---

## 本场收尾资产（验收完成）

| 博主 | MP4 | transcript | summary | 云备份 |
|------|-----|------------|---------|--------|
| 老曹 | `20260603T100954Z.mp4` | yes | yes | completed |
| 满江宏 | `20260603T105139Z.mp4` | yes | yes | completed |

---

## 收尾工单 #92–#95（代码补全）

| Issue | 交付 | 验证 |
|-------|------|------|
| [#94](https://github.com/oychao1988/media2text/issues/94) | `live.live_poll_interval_sec` 默认 **10**；文档同步 | `test_config` |
| [#93](https://github.com/oychao1988/media2text/issues/93) | `stream_resolve` pipeline event；`platform_live_started_at` 解析写入 | `test_start_recording_stream_resolve_event`、`test_parse_live_started` |
| [#92](https://github.com/oychao1988/media2text/issues/92) | `media2text post-process retry <job_id>` | `test_post_process_repo` |
| [#95](https://github.com/oychao1988/media2text/issues/95) | 本记录 + PR 合并后关闭 issue | `pytest tests/ -q`（197 passed @ 收尾分支） |

规格索引：[2026-06-03-live-pipeline-v2-design.md](../specs/2026-06-03-live-pipeline-v2-design.md)（§12 勾选已与收尾实现对齐）。
