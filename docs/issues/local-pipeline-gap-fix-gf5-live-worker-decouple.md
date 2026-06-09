---
issue: 266
epic: local-pipeline-spec-gap-fix
github: 266
branch: issue-266-local-pipeline-gap-fix-gf5
depends_on: [249]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md
---

# Local Pipeline Gap Fix GF-5：Live Worker 开录解耦（开播通知 + 下播收尾）

## 背景

2026-06-09 生产事故（博主「超越主升老王-容维证券」，session `341b8d64-…`）：

| 现象 | 数据 |
|------|------|
| 飞书「开播」通知晚 ~1h14m | `live_sessions.started_at` = 02:15 UTC；`notify_events.live_started.created_at` = 03:29 UTC |
| 直播已结束，Desktop 仍显示「录制中」 | `creator_live_snapshots.is_live=0`，但 `obs_still_live=1`、`offline_since_at` 空；ffmpeg 仍存活、FLV 不再增长 |

**根因（架构层已分离，Worker 内仍同步耦合）：**

1. **通知阻塞**：`LW-01` / `_start_recording_after_session` 在 streaming 模式下顺序为 `spawn ffmpeg → stt.start()（同步，可阻塞数十分钟）→ emit LIVE_STARTED`。Outbox（R4）只保证 emit 之后不 sync 调飞书，**不能**解决 emit 本身被推迟。
2. **下播 stuck**：`offline_trust_recording_signals=true` 时，profile 已 offline 仍可能因 **reflow 仍报 live** 或 **ffmpeg 僵尸进程** 长期保持 `obs_still_live=1`，Reconciler 无法 enqueue `finalize`。

规格意图（§I.0–I.1）：Probe 只传感、Worker 只执行、通知走 outbox、Reconciler 读 `obs_*` 编排任务——**层间已分离**；本 Issue 补齐 **Worker 开录 handler 内部** 与 **LP-02 离线信任策略** 的 gap。

**参考**

- [local-pipeline-refactor-design §I.0–I.1、LP-02、LW-01](../superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md)
- [gap-fix plan](../superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md)（GF-1–4 已交付 #246–#249）

**依赖**：#249（GF-4）已合并。

## 验收标准

### Task 1 — 开播通知不等待 STT（P0）

- [ ] `_start_recording_after_session`：`ffmpeg` 通过 `FFMPEG_STARTUP_GRACE_SEC` 存活检查后 **立即**：
  - 写 `live_pipeline_events` `recording|started`
  - `NotifyService.emit(LIVE_STARTED)`（含 `creator_id`、`session_id`）
- [ ] `streaming_stt.start()` **移至** 上述通知之后；STT 阻塞不得推迟 `LIVE_STARTED`
- [ ] 新增单测 `test_live_started_emitted_before_streaming_stt_blocks`：mock `stt.start()` 阻塞/慢返回，断言 `notify.emit(LIVE_STARTED)` 在 `stt.start()` 之前被调用
- [ ] 回归：`pytest tests/unit/test_live_recording_core.py` 通过

### Task 2 — STT 启动失败不杀整段录制（P0）

- [ ] streaming 模式下：`LIVE_STARTED` 已发出后，若 `stt.start()` 失败 → **不得** stop ffmpeg / 不得把 session 标 `failed`
- [ ] 改为 `_mark_streaming_degraded`（或等价路径），session 保持 `recording`，Reconciler 可 ensure `start_streaming_stt` / `reconnect_streaming_stt`
- [ ] 发出 `LIVE_START_FAILED` **仅** 当 ffmpeg 早退；STT 失败单独 log + 可选 `TRANSCRIBE_*` 通知（非阻塞开录）
- [ ] 单测覆盖「ffmpeg 已录 + STT fail → status 仍为 recording」

### Task 3 — 下播 FLV stall 收尾（P0）

- [ ] 新增配置 `live.offline_flv_stall_polls`（默认 `3`），写入 `config.py` + `config.example.yaml`
- [ ] `_infer_live_from_recording`：profile offline 且 FLV **连续 N 次** obs poll 不增长 → 返回 `False`（即使 reflow 仍报 live 或 ffmpeg 进程仍存活）
- [ ] FLV 恢复增长时清零 stall 计数
- [ ] `test_profile_offline_after_flv_stall_ignores_reflow` 通过（reflow live + 3 轮无增长 → `LIVE_ENDED`）
- [ ] 回归：`tests/unit/test_offline_recording_signals.py` 全绿

### Task 4 — 文档（P1）

- [ ] `config.example.yaml` 注释说明 `offline_flv_stall_polls` 与 `offline_trust_recording_signals` 的关系
- [ ] 在 `docs/superpowers/verification/2026-06-09-m2t-local-pipeline-refactor-acceptance.md`（或 gap-fix 验收表）增加 GF-5 行

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_offline_recording_signals.py tests/unit/test_live_recording_core.py -v
pytest tests/unit/test_streaming_stt_resilience.py -v -k "start or degraded" 2>/dev/null || true
ruff check src/media2text/core/live/recording.py src/media2text/core/config.py
```

## 非目标范围

- **LW-01 完全 task 化**（ffmpeg 与 STT 拆成两个 monitor_task、Reconciler 驱动 `live_started` 通知）—— 规格正确方向，留后续 Issue
- 修改飞书 webhook 消息格式
- 调整 `offline_confirm_sec` 默认值
- B 站 adapter reflow 语义重写
- 清理历史 `monitor_tasks` stuck `running`（运维 `POST /api/runtime/recover-stale`，非本单）

## 待确认问题

- [ ] STT 启动失败时是否仍需用户可见通知（除 log 外）？默认：**仅 degraded + Reconciler 重试**，不重复发「开播失败」

## 依赖与顺序

- **依赖**：#249
- **建议分支**：`issue-266-local-pipeline-gap-fix-gf5`
- **Epic**：`local-pipeline-spec-gap-fix` manifest 可增 GF-5 行（implementer 合并前更新）

## GitHub

- Issue: [#266](https://github.com/oychao1988/media2text/issues/266)
