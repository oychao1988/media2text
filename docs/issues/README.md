# Issue 工单索引（Agent B 执行）

本目录存放 **Issue 规格正文**（Agent A 产出），供 [issue-implementer](.claude/agents/issue-implementer.md) 按「一 Issue 一分支」实现。

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#5](https://github.com/oychao1988/media2text/issues/5) | [#10](https://github.com/oychao1988/media2text/pull/10) | [live-recording-transcribe-manifest.md](./live-recording-transcribe-manifest.md) | `issue-5-live-transcribe-manifest` |
| 2 | [#6](https://github.com/oychao1988/media2text/issues/6) | [#11](https://github.com/oychao1988/media2text/pull/11) | [transcribe-cloud-backend.md](./transcribe-cloud-backend.md) | `issue-6-transcribe-cloud-openai` |
| 3 | [#7](https://github.com/oychao1988/media2text/issues/7) | [#12](https://github.com/oychao1988/media2text/pull/12) | [transcribe-local-performance.md](./transcribe-local-performance.md) | `issue-7-transcribe-local-perf` |
| 4 | [#8](https://github.com/oychao1988/media2text/issues/8) | [#13](https://github.com/oychao1988/media2text/pull/13) | [adapter-cli-hardening.md](./adapter-cli-hardening.md) | `issue-8-adapter-cli-hardening` |
| 5 | [#9](https://github.com/oychao1988/media2text/issues/9) | （本 PR） | [design-spec-sync.md](./design-spec-sync.md) | `issue-9-design-spec-sync` |

### P0 财经直播情报档案（2026-05-22，待开 PR）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#18](https://github.com/oychao1988/media2text/issues/18) | — | [archive-index-foundation.md](./archive-index-foundation.md) | `issue-18-archive-index` |
| 2 | [#19](https://github.com/oychao1988/media2text/issues/19) | — | [archive-search-compliance.md](./archive-search-compliance.md) | `issue-19-archive-search-compliance` |
| 3 | [#20](https://github.com/oychao1988/media2text/issues/20) | — | [archive-timeline-pricing.md](./archive-timeline-pricing.md) | `issue-20-archive-timeline-pricing` |

**合并顺序**：#18 → #19 → #20（#19、#20 依赖索引与 `Hit`/compliance）。

**本地 WIP 备份**：分支 `wip/notify-20260522`（notify/飞书扩展快照，与 P0 archive 分开）。

**已交付（勿重复开单）**：[`creator-monitor-and-profile.md`](./creator-monitor-and-profile.md) 中 P1–P3 已在代码实现并勾选完成。

### 阿里云盘备份（进行中）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#65](https://github.com/oychao1988/media2text/issues/65) | [#66](https://github.com/oychao1988/media2text/pull/66) | [aliyundrive-cloud-foundation.md](./aliyundrive-cloud-foundation.md) | `issue-65-aliyundrive-cloud-foundation` |
| 2 | [#67](https://github.com/oychao1988/media2text/issues/67) | [#68](https://github.com/oychao1988/media2text/pull/68) | [aliyundrive-live-upload.md](./aliyundrive-live-upload.md) | `issue-67-aliyundrive-live-upload` |

**合并顺序**：#66（阶段 A）→ 阶段 B PR。

### LLM 转写摘要（summarize）

| 阶段 | GitHub | PR | 说明 |
|------|--------|-----|------|
| P1–P3 | [#72](https://github.com/oychao1988/media2text/issues/72)（已关闭） | [#74](https://github.com/oychao1988/media2text/pull/74) | `summarize run` / `merge`、`suggested_groups`；规格见 [summarize-design](../superpowers/specs/2026-06-01-summarize-design.md) |
| P4 | [#71](https://github.com/oychao1988/media2text/issues/71)（已关闭） | [#75](https://github.com/oychao1988/media2text/pull/75) | `on_transcribe_complete` 钩子 + 云盘 summary sidecar |
| P5 | — | — | 通知、archive FTS（待开单） |

### 直播录制管道（2026-06-02）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| 1 | [#73](https://github.com/oychao1988/media2text/issues/73) | [#77](https://github.com/oychao1988/media2text/pull/77) | [live-recording-pipeline.md](./live-recording-pipeline.md) | `issue-73-live-recording-pipeline` |
| 2 | [#78](https://github.com/oychao1988/media2text/issues/78) | — | [live-stale-poll-order.md](./live-stale-poll-order.md) | `issue-78-live-stale-poll-order` |

工程评审 D1–D4：1A / 2A / 3A / 4A。实现计划含 Task 4b `scan_and_start`。

**历史合并顺序**：#10 → #11 → #12 → #13 → #9（文档 PR 可最后合并，或基于已合并的 main 重开）。
