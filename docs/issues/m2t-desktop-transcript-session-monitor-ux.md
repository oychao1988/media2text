# m2t-desktop 转写场次下拉 + 折叠侧栏监控弹窗 + Agent 验收收尾

## 背景

Agent Pane Epic（#170–#177）合并后，转写区场次切换、折叠左栏监控入口、以及 Epic 验收自动化仍存在 UX/稳定性缺口：

1. **场次下拉**：原生 `<select>` 在 tab 行内易被 `overflow` 裁切；历史场次切换后转写/摘要未加载或闪回「当前 · 等待录制」。
2. **折叠侧栏监控**：状态灯需与 runtime 健康态同步闪烁；点击应弹出锚定菜单（同 UserMenu），而非展开侧栏或全屏 modal；首次打开不应闪到左上角。
3. **Agent Pane 验收**：Epic 验收表 L5/A5/A6/A9/A10 需 Vitest + sidecar 冒烟覆盖；布局预设切换时 CSS 变量 FOUC 需 inline bootstrap。

**参考**

- Epic 验收：[2026-06-06-m2t-desktop-agent-pane-acceptance.md](../superpowers/verification/2026-06-06-m2t-desktop-agent-pane-acceptance.md)
- 桌面规格：[m2t-desktop-design](../superpowers/specs/2026-06-04-m2t-desktop-design.md)

## 验收标准

### 转写场次（L5 增强）

- [x] `M2tSelect` portal 下拉：max-height ~480px、菜单内滚动不关闭、直播/VOD 图标 + 右侧日期
- [x] 历史场次选择写入 `transcriptSelection`（含 `transcriptPath` / `summaryPath` / `hasTranscript` / `hasSummary`）
- [x] `TranscriptPane` playback 模式可加载 VOD/live 历史转写与摘要（不依赖 `sessionId`）
- [x] 切换场次稳定：不因 pane remount 或 sessions 拉取完成而重置为「当前 · 等待录制」
- [x] `pnpm --filter m2t-desktop test`（含 `M2tSelect.test.tsx`、`transcriptSelection.test.ts`）

### 折叠侧栏监控弹窗

- [x] 折叠态 `#rail-daemon` 状态点：`health-*` + 录制中呼吸动画，与 runtime 一致
- [x] 点击状态点打开 `DaemonMonitorMenu`（透明 backdrop + 锚定 panel，非 modal overlay）
- [x] 首次打开定位在按钮附近（`positionReady` + `useLayoutEffect`），无左上角闪屏
- [x] `DaemonAppEffects` 统一维护 `#app.daemon-stopped`；折叠侧栏隐藏 inline `DaemonCard`

### Agent / 布局 polish

- [x] Agent Composer：`M2tSelect` 模型选择、`useAutoResizeTextarea`；`PromptDialog` 替代 `window.prompt`
- [x] Agent 历史侧栏重命名/右键菜单定位；Vitest `agentPaneAcceptance.test.tsx`
- [x] `index.html` inline 恢复 layout CSS 变量，减少预设切换 FOUC
- [x] `scripts/agent_pane_sidecar_smoke.mjs` A9 冒烟；Epic 验收文档第二轮记录

### 文档 / 流程

- [x] `issue-orchestrator` agent + Epic 验收表更新
- [x] `docs/issues/README.md` 索引本 Issue

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
node scripts/agent_pane_sidecar_smoke.mjs   # 需 media2text serve --port 8765

# 手工（tauri dev）
pnpm --filter m2t-desktop tauri dev
# 1. 转写 tab → 场次下拉选历史 live/VOD → 转写+摘要加载且选中保持
# 2. 折叠左栏 → 点状态灯 → 监控弹窗锚定在按钮旁，内点按钮无闪屏
```

## 非目标范围

- 场次下拉跨博主批量操作
- Tauri 内 Pi Agent 发送全链路（仍 sidecar/Vite 冒烟）
- 修改 `/api/creators/{id}/sessions` 响应 schema

## 实现备注

- GitHub Issue: [#178](https://github.com/oychao1988/media2text/issues/178) · PR: [#179](https://github.com/oychao1988/media2text/pull/179)
- 分支：`issue-178-m2t-desktop-transcript-session-monitor-ux`
