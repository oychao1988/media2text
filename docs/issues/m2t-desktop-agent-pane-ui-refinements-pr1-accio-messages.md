# m2t-desktop Agent Pane UI 细化 PR1：Accio 式消息组件

## 背景

将 `AgentPanel` 中旧版 `.msg-user` / `.msg-assistant` 替换为与 [finalized.html](../superpowers/designs/m2t-desktop/finalized.html) 一致的 Accio 风格消息流：用户右对齐气泡、助手全宽正文、处理过程行、底栏常驻操作。

**参考**

- 规格 §5、§5.3.1、§11 A5–A6：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md)
- 前置 Epic（已交付）：[#170–#173](./README.md#m2t-desktop-agent-pane--布局预设2026-06-06)

**依赖**：无（可与 PR2 并行，但建议在 PR3 前合并以便空态/历史联调）

## 验收标准

### 组件结构

- [x] 新增 `ChatMessageUser`：`.chat-msg-user`、`.chat-msg-head`（时间·名称·头像右对齐）、`.chat-msg-bubble`、悬停 `.chat-msg-actions`（重试/编辑/复制 → toast）
- [x] 新增 `ChatMessageAgent`：`.chat-msg-agent` 全宽、`.chat-msg-body` Markdown 样式、`.chat-msg-footer` 常驻（复制/赞/踩 → v1 noop 或 toast）
- [x] 新增 `ChatMessageProcess`（§5.3.1 / §14.3）：
  - Turn 进行中：显示 WS `turn.phase` → `phaseLabel`；不可展开
  - Turn 完成：「已处理 {duration_s} 秒」；默认折叠
  - 有 `thinking_text` 时可展开 `.chat-msg-process-body`；无则隐藏 `›`
  - `aria-expanded` 绑在 process 按钮上
- [x] `#chat-live` / `#chat-playback`：`flex column; gap: 20px; width: 100%`；用户消息 `margin-left: auto`
- [x] 保留 `.tool-card` 嵌于助手流

### 数据映射

- [x] `duration_ms` / WS `message.assistant.durationMs` → 处理行秒数
- [x] `thinking_text` / WS `message.thinking` → 展开正文
- [x] 流式过程中 **不** 逐字展开 thinking；完成后一次性可读

### 测试

- [x] `pnpm --filter m2t-desktop test`（消息组件 snapshot / 结构测试）
- [x] 扩展 `agentPaneAcceptance.test.tsx` 覆盖 A5、A6（mock 消息 + phase）

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
media2text serve --port 8765
# 手工 A5/A6：用户气泡右对齐；助手全宽；流式 phase → 完成后「已处理 N 秒」+ thinking 展开
open docs/superpowers/designs/m2t-desktop/finalized.html
```

## 非目标范围

- 历史 Agent 分组、HistoryFilter 移除（PR2）
- Draft 页签 / 延迟 POST thread（PR3）
- 页签头像（PR4）
- 布局 preset / chat-only 居中（PR5）
- Composer 高度修复（PR6）
- 点赞/点踩后端持久化（API-3 P2）
- 重试/编辑真实逻辑（v1 toast）

## 实现备注

- 分支：`issue-199-agent-accio-messages`
- GitHub Issue: [#199](https://github.com/oychao1988/media2text/issues/199)
- 原 #199 为系列总单空壳，已拆分为 PR1–PR6（见 [README](./README.md#m2t-desktop-agent-pane-ui-细化2026-06-07)）
