# Issue 工单索引（Agent B 执行）

本目录存放 **Issue 规格正文**（Agent A 产出），供 [issue-implementer](.claude/agents/issue-implementer.md) 按「一 Issue 一分支」实现。系列交付由 [issue-orchestrator](.claude/agents/issue-orchestrator.md) 编排；Epic 验收见 `docs/superpowers/verification/`。

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#5](https://github.com/oychao1988/media2text/issues/5) | [#10](https://github.com/oychao1988/media2text/pull/10) | [live-recording-transcribe-manifest.md](./live-recording-transcribe-manifest.md) | `issue-5-live-transcribe-manifest` |
| 2 | [#6](https://github.com/oychao1988/media2text/issues/6) | [#11](https://github.com/oychao1988/media2text/pull/11) | [transcribe-cloud-backend.md](./transcribe-cloud-backend.md) | `issue-6-transcribe-cloud-openai` |
| 3 | [#7](https://github.com/oychao1988/media2text/issues/7) | [#12](https://github.com/oychao1988/media2text/pull/12) | [transcribe-local-performance.md](./transcribe-local-performance.md) | `issue-7-transcribe-local-perf` |
| 4 | [#8](https://github.com/oychao1988/media2text/issues/8) | [#13](https://github.com/oychao1988/media2text/pull/13) | [adapter-cli-hardening.md](./adapter-cli-hardening.md) | `issue-8-adapter-cli-hardening` |
| 5 | [#9](https://github.com/oychao1988/media2text/issues/9) | （本 PR） | [design-spec-sync.md](./design-spec-sync.md) | `issue-9-design-spec-sync` |

### P0 财经直播情报档案（2026-05-22，已交付）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#18](https://github.com/oychao1988/media2text/issues/18)（已关闭） | — | [archive-index-foundation.md](./archive-index-foundation.md) | `issue-18-archive-index` |
| 2 | [#19](https://github.com/oychao1988/media2text/issues/19)（已关闭） | — | [archive-search-compliance.md](./archive-search-compliance.md) | `issue-19-archive-search-compliance` |
| 3 | [#20](https://github.com/oychao1988/media2text/issues/20)（已关闭） | — | [archive-timeline-pricing.md](./archive-timeline-pricing.md) | `issue-20-archive-timeline-pricing` |

**合并顺序**：#18 → #19 → #20（已完成）。

**本地 WIP 备份**：分支 `wip/notify-20260522`（notify/飞书扩展快照，与 P0 archive 分开）。

**已交付（勿重复开单）**：[`creator-monitor-and-profile.md`](./creator-monitor-and-profile.md) 中 P1–P3 已在代码实现并勾选完成。

### 阿里云盘备份（已交付）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#65](https://github.com/oychao1988/media2text/issues/65)（已关闭） | [#66](https://github.com/oychao1988/media2text/pull/66) | [aliyundrive-cloud-foundation.md](./aliyundrive-cloud-foundation.md) | `issue-65-aliyundrive-cloud-foundation` |
| 2 | [#67](https://github.com/oychao1988/media2text/issues/67)（已关闭） | [#68](https://github.com/oychao1988/media2text/pull/68) | [aliyundrive-live-upload.md](./aliyundrive-live-upload.md) | `issue-67-aliyundrive-live-upload` |

### LLM 转写摘要（summarize）

| 阶段 | GitHub | PR | 说明 |
|------|--------|-----|------|
| P1–P3 | [#72](https://github.com/oychao1988/media2text/issues/72)（已关闭） | [#74](https://github.com/oychao1988/media2text/pull/74) | `summarize run` / `merge`、`suggested_groups`；规格见 [summarize-design](../superpowers/specs/2026-06-01-summarize-design.md) |
| P4 | [#71](https://github.com/oychao1988/media2text/issues/71)（已关闭） | [#75](https://github.com/oychao1988/media2text/pull/75) | `on_transcribe_complete` 钩子 + 云盘 summary sidecar |
| P5 | — | — | 通知、archive FTS（已在后处理/索引落地；v2 增强见 #96） |

### Live Pipeline v2（2026-06-03，P0–P3 已交付）

| 阶段 | GitHub | 说明 |
|------|--------|------|
| P0 | [#81](https://github.com/oychao1988/media2text/issues/81)（已关闭） | 三线程隔离 |
| P1 | [#83](https://github.com/oychao1988/media2text/issues/83)（已关闭） | 墙钟 offline + `live_ended` |
| P2 | [#85](https://github.com/oychao1988/media2text/issues/85)（已关闭） | pipeline events + `live` CLI |
| P3 | [#87](https://github.com/oychao1988/media2text/issues/87)（已关闭） | `scan_concurrency` + adaptive workers |

规格：[live-pipeline-v2-design](../superpowers/specs/2026-06-03-live-pipeline-v2-design.md)

### Live Pipeline v2 收尾（2026-06-03）

| GitHub | 规格正文 | 状态 |
|--------|----------|------|
| [#94](https://github.com/oychao1988/media2text/issues/94) | [wrap-config-docs](../superpowers/issues/2026-06-03-live-pipeline-v2-wrap-config-docs-issue-body.md) | 已实现（默认 poll 10s + 文档） |
| [#93](https://github.com/oychao1988/media2text/issues/93) | [wrap-events](../superpowers/issues/2026-06-03-live-pipeline-v2-wrap-events-issue-body.md) | 已实现 |
| [#92](https://github.com/oychao1988/media2text/issues/92) | [wrap-retry](../superpowers/issues/2026-06-03-live-pipeline-v2-wrap-retry-issue-body.md) | 已实现 |
| [#95](https://github.com/oychao1988/media2text/issues/95) | [wrap-acceptance](../superpowers/issues/2026-06-03-live-pipeline-v2-wrap-acceptance-issue-body.md) | 已实现 |

验收记录：[verification/2026-06-03-live-pipeline-v2-acceptance.md](../superpowers/verification/2026-06-03-live-pipeline-v2-acceptance.md)

**并行、非阻塞主线**：

| GitHub | 规格正文 | 说明 |
|--------|----------|------|
| [#96](https://github.com/oychao1988/media2text/issues/96) | [summarize-v2-deferred](../superpowers/issues/2026-06-03-summarize-v2-deferred-issue-body.md) | Summarize v2 延期项 |
| [#97](https://github.com/oychao1988/media2text/issues/97) | [live-streaming-stt-p0](../superpowers/issues/2026-06-03-live-streaming-transcribe-spike-issue-body.md) | v3 流式 STT P0 → PR [#100](https://github.com/oychao1988/media2text/pull/100) |

**Streaming STT P1/P2（#97 合并后）**：

| GitHub | 规格正文 | 说明 |
|--------|----------|------|
| [#101](https://github.com/oychao1988/media2text/issues/101) | [p1-offset-merge](../superpowers/issues/2026-06-03-live-streaming-stt-p1-offset-merge-issue-body.md) | 断流 transcript offset merge |
| [#102](https://github.com/oychao1988/media2text/issues/102) | [p1-bilibili](../superpowers/issues/2026-06-03-live-streaming-stt-p1-bilibili-issue-body.md) | B 站 streaming STT |
| [#103](https://github.com/oychao1988/media2text/issues/103) | [p1-db-snapshot](../superpowers/issues/2026-06-03-live-streaming-stt-p1-db-snapshot-issue-body.md) | `pipeline_mode` 快照 + DB 别名 |
| [#104](https://github.com/oychao1988/media2text/issues/104) | [p2-observability](../superpowers/issues/2026-06-03-live-streaming-stt-p2-observability-issue-body.md) | partial 通知、metrics、`live stats` |

规格：[live-streaming-stt-design](../superpowers/specs/2026-06-03-live-streaming-stt-design.md)

### 直播录制管道 v1（2026-06-02，已交付）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#73](https://github.com/oychao1988/media2text/issues/73)（已关闭） | [#77](https://github.com/oychao1988/media2text/pull/77) | [live-recording-pipeline.md](./live-recording-pipeline.md) | `issue-73-live-recording-pipeline` |
| 2 | [#78](https://github.com/oychao1988/media2text/issues/78)（已关闭） | — | [live-stale-poll-order.md](./live-stale-poll-order.md) | `issue-78-live-stale-poll-order` |

工程评审 D1–D4：1A / 2A / 3A / 4A。实现计划含 Task 4b `scan_and_start`。

**历史合并顺序**：#10 → #11 → #12 → #13 → #9（文档 PR 可最后合并，或基于已合并的 main 重开）。

### m2t-desktop 桌面端（2026-06-04，待实现）

规格：[m2t-desktop-design](../superpowers/specs/2026-06-04-m2t-desktop-design.md) · 计划：[m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md) · UI：[finalized.html](../superpowers/designs/m2t-desktop/finalized.html)

**建议合并顺序**（串行 API 轨；Tauri/布局可与 API 部分并行）：

| 顺序 | GitHub | 规格正文 | 分支 |
|------|--------|----------|------|
| 1 | [#125](https://github.com/oychao1988/media2text/issues/125) | [m2t-desktop-p0-core-prerequisites.md](./m2t-desktop-p0-core-prerequisites.md) | `issue-125-m2t-desktop-p0-core` |
| 2 | [#126](https://github.com/oychao1988/media2text/issues/126) | [m2t-desktop-p1-api-foundation.md](./m2t-desktop-p1-api-foundation.md) | `issue-126-m2t-desktop-p1-api-foundation` |
| 3 | [#127](https://github.com/oychao1988/media2text/issues/127) | [m2t-desktop-p2-api-sessions-flv.md](./m2t-desktop-p2-api-sessions-flv.md) | `issue-127-m2t-desktop-p2-api-sessions-flv` |
| 4 | [#128](https://github.com/oychao1988/media2text/issues/128) | [m2t-desktop-p3-api-recording-events.md](./m2t-desktop-p3-api-recording-events.md) | `issue-128-m2t-desktop-p3-api-recording-events` |
| 5 | [#129](https://github.com/oychao1988/media2text/issues/129) | [m2t-desktop-p4-tauri-python-sidecar.md](./m2t-desktop-p4-tauri-python-sidecar.md) | `issue-129-m2t-desktop-p4-tauri-shell` |
| 6 | [#130](https://github.com/oychao1988/media2text/issues/130) | [m2t-desktop-p5-react-layout-shell.md](./m2t-desktop-p5-react-layout-shell.md) | `issue-130-m2t-desktop-p5-layout-shell` |
| 7 | [#131](https://github.com/oychao1988/media2text/issues/131) | [m2t-desktop-p6-react-feature-panels.md](./m2t-desktop-p6-react-feature-panels.md) | `issue-131-m2t-desktop-p6-feature-panels` |
| 8 | [#132](https://github.com/oychao1988/media2text/issues/132) | [m2t-desktop-p7-agent-sidecar-ui.md](./m2t-desktop-p7-agent-sidecar-ui.md) | `issue-132-m2t-desktop-p7-agent` |
| 9 | [#133](https://github.com/oychao1988/media2text/issues/133) | [m2t-desktop-p8-smoke-docs-a11y.md](./m2t-desktop-p8-smoke-docs-a11y.md) | `issue-133-m2t-desktop-p8-smoke` |
| 10 | [#143](https://github.com/oychao1988/media2text/issues/143) | [m2t-desktop-p9-ui-parity-finalized.md](./m2t-desktop-p9-ui-parity-finalized.md) | `issue-143-m2t-desktop-p9-ui-parity` |

### m2t-desktop 监控管理 & 侧栏 UX（2026-06-05）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#154](https://github.com/oychao1988/media2text/issues/154) | [#155](https://github.com/oychao1988/media2text/pull/155) | [m2t-desktop-manage-creator-ux.md](./m2t-desktop-manage-creator-ux.md) | `issue-154-m2t-desktop-manage-creator-ux` |

### m2t-desktop 系统配置 AI Provider（2026-06-05）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#156](https://github.com/oychao1988/media2text/issues/156) | （本 PR） | [m2t-desktop-config-ai-provider.md](./m2t-desktop-config-ai-provider.md) | `issue-156-m2t-desktop-config-ai-provider` |

**并行提示**：#127 与 #128 可并行；#129/#130 可在 #126 后 mock API 并行；#132 建议在 #131 前或同 PR 联调；**#143** 建议在 #131/#132 合并后、#133 冒烟前完成 Phase A–D。

### Desktop Runtime — 内嵌监控 + 统一状态（2026-06-05，已交付）

规格：[desktop-runtime-design](../superpowers/specs/2026-06-05-desktop-runtime-design.md)

| 顺序 | GitHub | PR | 规格正文 | 分支 |
|------|--------|-----|----------|------|
| 1–4 | [#158](https://github.com/oychao1988/media2text/issues/158)–[#161](https://github.com/oychao1988/media2text/issues/161)（已关闭） | [#162](https://github.com/oychao1988/media2text/pull/162) | [pr1](./desktop-runtime-pr1-supervisor-api.md) · [pr2](./desktop-runtime-pr2-ws-frontend.md) · [pr3](./desktop-runtime-pr3-daemon-ui.md) · [pr4](./desktop-runtime-pr4-pipeline-api.md) | `issue-159-desktop-runtime-pr2` |

### m2t-desktop 历史列表媒体与云盘（2026-06-06）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#164](https://github.com/oychao1988/media2text/issues/164) | （本 PR） | [m2t-desktop-history-media-ops.md](./m2t-desktop-history-media-ops.md) | `issue-164-desktop-history-media-ops` |

### m2t-desktop 历史手动摘要/重试 + Runtime 接管（2026-06-06）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#166](https://github.com/oychao1988/media2text/issues/166) | [#167](https://github.com/oychao1988/media2text/pull/167) | [m2t-desktop-history-ops-runtime-takeover.md](./m2t-desktop-history-ops-runtime-takeover.md) | `issue-166-desktop-history-ops-runtime` |

### 抖音图文下载 + Desktop 作品下载 UX（2026-06-06）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#168](https://github.com/oychao1988/media2text/issues/168) | [#169](https://github.com/oychao1988/media2text/pull/169) | [douyin-gallery-desktop-vod-ux.md](./douyin-gallery-desktop-vod-ux.md) | `issue-168-douyin-gallery-desktop-vod` |

### m2t-desktop Agent Pane + 布局预设（2026-06-06）

规格：[2026-06-06-m2t-desktop-agent-pane-design.md](../superpowers/specs/2026-06-06-m2t-desktop-agent-pane-design.md) · 计划：[2026-06-06-m2t-desktop-agent-pane.md](../superpowers/plans/2026-06-06-m2t-desktop-agent-pane.md)

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#170](https://github.com/oychao1988/media2text/issues/170) | [#174](https://github.com/oychao1988/media2text/pull/174) | [m2t-desktop-agent-pane-pr1-history-api.md](./m2t-desktop-agent-pane-pr1-history-api.md) | `issue-170-desktop-history-api` |
| 2 | [#171](https://github.com/oychao1988/media2text/issues/171) | [#175](https://github.com/oychao1988/media2text/pull/175) | [m2t-desktop-agent-pane-pr2-sidecar-context.md](./m2t-desktop-agent-pane-pr2-sidecar-context.md) | `issue-171-agent-sidecar-context` |
| 3 | [#172](https://github.com/oychao1988/media2text/issues/172) | [#176](https://github.com/oychao1988/media2text/pull/176) | [m2t-desktop-agent-pane-pr3-layout-presets.md](./m2t-desktop-agent-pane-pr3-layout-presets.md) | `issue-172-desktop-layout-presets` |
| 4 | [#173](https://github.com/oychao1988/media2text/issues/173) | [#177](https://github.com/oychao1988/media2text/pull/177) | [m2t-desktop-agent-pane-pr4-agent-ui.md](./m2t-desktop-agent-pane-pr4-agent-ui.md) | `issue-173-agent-multi-thread-ui` |

**合并顺序**：#170 → #171 / #172（可并行）→ #173（**已交付**，Epic 验收：[agent-pane-acceptance](../superpowers/verification/2026-06-06-m2t-desktop-agent-pane-acceptance.md)）。

### m2t-desktop Agent Pane UI 细化（2026-06-07）

规格：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md) · 原型：[finalized.html](../superpowers/designs/m2t-desktop/finalized.html)

| 顺序 | GitHub | 文件 | 分支 |
|------|--------|------|------|
| 1 | [#199](https://github.com/oychao1988/media2text/issues/199) | [pr1-accio-messages](./m2t-desktop-agent-pane-ui-refinements-pr1-accio-messages.md) | `issue-199-agent-accio-messages` |
| 2 | [#200](https://github.com/oychao1988/media2text/issues/200) | [pr2-agent-history](./m2t-desktop-agent-pane-ui-refinements-pr2-agent-history.md) | `issue-200-agent-history-groups` |
| 3 | [#201](https://github.com/oychao1988/media2text/issues/201) | [pr3-draft-thread](./m2t-desktop-agent-pane-ui-refinements-pr3-draft-thread.md) | `issue-201-agent-draft-thread` |
| 4 | [#202](https://github.com/oychao1988/media2text/issues/202) | [pr4-tab-avatars](./m2t-desktop-agent-pane-ui-refinements-pr4-tab-avatars.md) | `issue-202-agent-tab-avatars` |
| 5 | [#203](https://github.com/oychao1988/media2text/issues/203) | [pr5-layout-chatonly](./m2t-desktop-agent-pane-ui-refinements-pr5-layout-chatonly.md) | `issue-203-agent-layout-chatonly` |
| 6 | [#204](https://github.com/oychao1988/media2text/issues/204) | [pr6-composer](./m2t-desktop-agent-pane-ui-refinements-pr6-composer.md) | `issue-204-agent-composer` |

**合并顺序**：#199 / #200 可并行 → #201 → #202 → #203 / #204（可并行）→ 系列验收 A1–A10（规格 §11）。**零后端变更**。

### m2t-desktop 转写场次 + 监控弹窗 UX（2026-06-06）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#178](https://github.com/oychao1988/media2text/issues/178) | [#179](https://github.com/oychao1988/media2text/pull/179) | [m2t-desktop-transcript-session-monitor-ux.md](./m2t-desktop-transcript-session-monitor-ux.md) | `issue-178-m2t-desktop-transcript-session-monitor-ux` |

### m2t-desktop Agent 上下文与多文档附件（2026-06-09）

规格：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| P0 | [#254](https://github.com/oychao1988/media2text/issues/254) | [#260](https://github.com/oychao1988/media2text/pull/260) | [p0-creator-draft-link](./m2t-desktop-agent-context-p0-creator-draft-link.md) | `issue-254-agent-context-p0-creator-draft` |
| P1 | [#255](https://github.com/oychao1988/media2text/issues/255) | [#261](https://github.com/oychao1988/media2text/pull/261) | [p1-attachments-chips](./m2t-desktop-agent-context-p1-attachments-chips-binding.md) | `issue-255-agent-context-p1-attachments` |
| P1b | [#256](https://github.com/oychao1988/media2text/issues/256) | [#262](https://github.com/oychao1988/media2text/pull/262) | [p1b-context-mode-tab](./m2t-desktop-agent-context-p1b-context-mode-tab.md) | `issue-256-agent-context-p1b-context-mode` |
| P2 | [#257](https://github.com/oychao1988/media2text/issues/257) | [#263](https://github.com/oychao1988/media2text/pull/263) | [p2-mention-popover](./m2t-desktop-agent-context-p2-mention-popover.md) | `issue-257-agent-context-p2-mention-popover` |
| sidecar | [#258](https://github.com/oychao1988/media2text/issues/258) | [#264](https://github.com/oychao1988/media2text/pull/264) | [p2-sidecar-sync](./m2t-desktop-agent-context-p2-sidecar-sync.md) | `issue-258-agent-context-sidecar-sync` |
| P2c | [#259](https://github.com/oychao1988/media2text/issues/259) | （本 PR） | [p2c-epic-acceptance](./m2t-desktop-agent-context-p2c-epic-acceptance.md) | `issue-259-agent-context-epic-acceptance` |

**合并顺序**：#254 → #255 → #256 → #257 → Epic 验收 #259；#258 非闸门（sidecar 过渡）。Epic 验收：[agent-context-attachments-acceptance](../superpowers/verification/2026-06-09-m2t-desktop-agent-context-attachments-acceptance.md) · `python scripts/epic_verify.py agent-context-attachments`

### Monitor Daemon v3 — 观测/执行拆分（2026-06-05，待实现）

规格：[monitor-daemon-observe-execute-design](../superpowers/specs/2026-06-05-monitor-daemon-observe-execute-design.md) · 计划：[monitor-daemon-v3](../superpowers/plans/2026-06-05-monitor-daemon-v3.md)

| 顺序 | GitHub | 规格正文 | 分支 |
|------|--------|----------|------|
| 1 | [#145](https://github.com/oychao1988/media2text/issues/145) | [monitor-daemon-v3-phase1.md](./monitor-daemon-v3-phase1.md) | `issue-145-monitor-daemon-v3-phase1` |
| 2 | （待开单） | [monitor-daemon-v3-phase2.md](./monitor-daemon-v3-phase2.md) | `issue-*-monitor-daemon-v3-phase2` |
