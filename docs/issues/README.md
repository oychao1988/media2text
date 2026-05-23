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

### 转注 Work 桌面壳（OpenClaw + 发布里程碑）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| P0 | [#35](https://github.com/oychao1988/media2text/issues/35) | [#36](https://github.com/oychao1988/media2text/pull/36) | [zhuanzhu-electron-openclaw-chat.md](./zhuanzhu-electron-openclaw-chat.md) | `issue-35-zhuanzhu-electron-chat` ✅ |
| P1 | [#37](https://github.com/oychao1988/media2text/issues/37) | — | [zhuanzhu-p1-bundled-gateway.md](./zhuanzhu-p1-bundled-gateway.md) | `issue-37-zhuanzhu-p1-gateway` |
| P2 | [#38](https://github.com/oychao1988/media2text/issues/38) | — | [zhuanzhu-p2-installer.md](./zhuanzhu-p2-installer.md) | `issue-38-zhuanzhu-p2-installer` |
| P3 | [#39](https://github.com/oychao1988/media2text/issues/39) | [#42](https://github.com/oychao1988/media2text/pull/42) | [zhuanzhu-p3-media2text-sidecar.md](./zhuanzhu-p3-media2text-sidecar.md) | `issue-39-zhuanzhu-p3-m2t-sidecar` ✅ |

**合并顺序（P0–P3）**：#36 → #37 → #38 → #39 → #42。

### 转注 Work 产品化（P4–P8）

| 顺序 | GitHub | PR | 文件 | 分支 |
|------|--------|-----|------|------|
| P4 | [#43](https://github.com/oychao1988/media2text/issues/43) | — | [zhuanzhu-p4-ui-shell-migration.md](./zhuanzhu-p4-ui-shell-migration.md) | `issue-43-zhuanzhu-p4-ui-shell` 🚧 |
| P5 | [#44](https://github.com/oychao1988/media2text/issues/44) | [#49](https://github.com/oychao1988/media2text/pull/49) | [zhuanzhu-p5-chat-streaming.md](./zhuanzhu-p5-chat-streaming.md) | ✅ merged |
| P6 | [#45](https://github.com/oychao1988/media2text/issues/45) | [#50](https://github.com/oychao1988/media2text/pull/50) | [zhuanzhu-p6-agent-lens.md](./zhuanzhu-p6-agent-lens.md) | ✅ merged |
| P7 | [#46](https://github.com/oychao1988/media2text/issues/46) | [#51](https://github.com/oychao1988/media2text/pull/51) | [zhuanzhu-p7-bundle-runtime.md](./zhuanzhu-p7-bundle-runtime.md) | ✅ merged |
| P8 | [#47](https://github.com/oychao1988/media2text/issues/47) | [#52](https://github.com/oychao1988/media2text/pull/52) | [zhuanzhu-p8-distribution.md](./zhuanzhu-p8-distribution.md) | ✅ merged |
| P9 | [#53](https://github.com/oychao1988/media2text/issues/53) | [#54](https://github.com/oychao1988/media2text/pull/54) | [zhuanzhu-p9-bundle-redesign-accio.md](./zhuanzhu-p9-bundle-redesign-accio.md) | ✅ merged |

**合并顺序（P4–P9）**：#43 → #44 → #45；#46 → #47 → **#53** ✅（P9 已合并 main）。

### 转注 Work 聊天延迟优化（L1–L7，2026-05-24）

> 背景：OpenClaw 聊天 TTFT ~5s 根因分析；**不含**模型切换。Agent B 按 [issue-implementer](.claude/agents/issue-implementer.md) 一 Issue 一分支。

| 顺序 | GitHub | 文件 | 建议分支 | 说明 |
|------|--------|------|----------|------|
| L1 | [#56](https://github.com/oychao1988/media2text/issues/56) | [zhuanzhu-l1-chat-latency-benchmark.md](./zhuanzhu-l1-chat-latency-benchmark.md) | `issue-56-zhuanzhu-chat-latency-bench` | 基准脚本，后续 PR 必附 before/after |
| L2 | [#57](https://github.com/oychao1988/media2text/issues/57) | [zhuanzhu-l2-gateway-fail-fast.md](./zhuanzhu-l2-gateway-fail-fast.md) | `issue-57-zhuanzhu-gateway-fail-fast` | Gateway 秒退 fail-fast |
| L3 | [#58](https://github.com/oychao1988/media2text/issues/58) | [zhuanzhu-l3-chat-fast-config.md](./zhuanzhu-l3-chat-fast-config.md) | `issue-58-zhuanzhu-chat-fast-config` | fast 模式 UI/配置 |
| L4 | [#59](https://github.com/oychao1988/media2text/issues/59) | [zhuanzhu-l4-openclaw-config-hygiene.md](./zhuanzhu-l4-openclaw-config-hygiene.md) | `issue-59-zhuanzhu-openclaw-hygiene` | agents/skills doctor |
| L5 | [#60](https://github.com/oychao1988/media2text/issues/60) | [zhuanzhu-l5-chat-waiting-ux.md](./zhuanzhu-l5-chat-waiting-ux.md) | `issue-60-zhuanzhu-chat-waiting-ux` | TTFT 等待态 UX |
| L6 | [#61](https://github.com/oychao1988/media2text/issues/61) | [zhuanzhu-l6-dual-mode-chat.md](./zhuanzhu-l6-dual-mode-chat.md) | `issue-61-zhuanzhu-dual-mode-chat` | 快速 vs Agent |
| L7 | [#62](https://github.com/oychao1988/media2text/issues/62) | [zhuanzhu-l7-chat-websocket.md](./zhuanzhu-l7-chat-websocket.md) | `issue-62-zhuanzhu-chat-websocket` | WS chat.send（可选） |

**建议实施顺序**：#56 → #57 → #58 → #59 → #60 → #61 → #62（#56 为度量基线；#61/#62 依赖 Gateway 能力调研）。

**历史合并顺序**：#10 → #11 → #12 → #13 → #9（文档 PR 可最后合并，或基于已合并的 main 重开）。
