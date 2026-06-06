# m2t-desktop Agent Pane PR3：布局预设 + 转写场次下拉（D4）

## 背景

实现三种桌面布局（`full` / `transcript-chat` / `chat-only`）、转写区场次下拉，以及 **React 条件渲染** 单一 `TranscriptPane` 实例（D4）。VOD 转写经 PR1 history API 拉取，禁止 `/api/sessions/{aweme_id}`。

**参考**

- 计划 Task 6–9：[2026-06-06-m2t-desktop-agent-pane.md](../superpowers/plans/2026-06-06-m2t-desktop-agent-pane.md)
- 原型：[finalized.html](../superpowers/designs/m2t-desktop/finalized.html)
- **依赖 PR1**（history transcript 路由）

## 验收标准

### 布局持久化（Task 6）

- [ ] `layoutConstants.ts`：`desktopLayoutPreset`（默认 `full`）、`agentHistoryW`（140–340，默认 200）
- [ ] localStorage 往返 + `--agent-history-w` CSS 变量

### 预设 UI（Task 7）

- [ ] `DesktopLayoutPresets.tsx` 三按钮切换 preset
- [ ] `#app` 类名：`desktop-layout-full` / `desktop-layout-transcript` / `desktop-layout-chat-only`
- [ ] `chat-only` 隐藏 `#collapse-right`，右栏仅 Agent

### 场次下拉（Task 8）

- [ ] `TranscriptSessionSelect` 加载 `GET /api/creators/{id}/sessions`
- [ ] 首项「当前直播」当 `active_session_id` 存在
- [ ] 无转写时 toast「该场次暂无转写」
- [ ] `useLayoutStore.transcriptSelection` 状态

### TranscriptPane 挂载（Task 9）

- [ ] **单一** `TranscriptPane` 实例，按 preset 挂到 center 或 right-split 之一
- [ ] history vod → `/api/creators/{id}/history/vod/{itemId}/transcript`
- [ ] history live → `/history/live/{id}/transcript`
- [ ] active live 仍用 `/api/sessions/{uuid}` + WS
- [ ] `transcript-chat` 下 `useColumnResize` 三分栏宽度 clamp

### 测试

- [ ] `pnpm --filter m2t-desktop test`（含 `layoutPresets.test.ts`、`transcriptSelection.test.ts`、`uiParity.test.tsx` 扩展）

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 手工 L1–L6：切换三种 preset；下拉选 VOD/历史直播；确认转写内容加载
```

## 非目标范围

- Agent 多 Tab / 历史侧栏（PR4）
- Sidecar refresh 字段（PR2，但联调可在 PR4 一并验收）
- Tab 拖拽排序、open-tabs 持久化

## 实现备注

- 分支：`issue-172-desktop-layout-presets`
- GitHub Issue: [#172](https://github.com/oychao1988/media2text/issues/172)
- preset 切换可能导致 live WS 重连（v1 可接受）
