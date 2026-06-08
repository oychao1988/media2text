---
epic: agent-context-attachments
issue: 257
github: 257
branch: issue-257-agent-context-p2-mention-popover
depends_on: [255]
spec: docs/superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md
---

# m2t-desktop Agent 上下文 P2：Composer `@` popover + lazy sessions

## 背景

产品 **D4/D5**：Composer 输入 `@` 打开 popover，从 **跨博主** 历史文档中选 **转写或摘要**（分行）；选中后 **追加 chip**（`source: 'mention'`），与场次默认附加 **累加**。

工程 **E6**：sessions 列表 **按需 lazy** 拉取；**并发上限 3**；**per-creator 内存缓存 ~5min**。

**参考**

- 规格 §6：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)

**依赖**：P1 [#255](https://github.com/oychao1988/media2text/issues/255) `ContextAttachment`、chip UI、`useAgentAttachments` **必须已合并**

## 验收标准

### 交互（§6.1）

- [x] 输入 `@` → anchored popover（相对 textarea）
- [x] 继续输入 → filter：`creatorName`、`display_label`、`title`
- [x] ↑ / ↓ / Enter 选中；Esc 关闭
- [x] 选中 → **追加** chip；清除输入框内 `@query` 段，保留其余文本
- [x] v1 **无** 输入框内持久 `@token` pill

### 列表项（§6.2）

- [x] 每个 session 展开 **0–2 行**：`has_transcript` → 转写行；`has_summary` → 摘要行
- [x] label 示例：`博主A · 2026-06-02 21:04 直播 · 转写`；VOD 用 title

### 数据源（E6）

- [x] popover 打开：`GET /api/creators` 取博主名
- [x] 按需：`GET /api/creators/{id}/sessions` — **仅 filter 命中的 creator**；并发 ≤3；缓存 ~5min
- [x] 客户端 filter + 展开 transcript/summary 行

### 与主 session（§6.4）

- [x] `@` 选中 **不修改** 主 `sessionId`
- [x] 跨博主 chip 显示 `creatorName` 前缀

### 规格验收 D1–D5

- [x] **D1**：`@` 列表含其他博主
- [x] **D2**：同场次转写/摘要分两行
- [x] **D3**：选中后 chip 追加，turn 可读该文档
- [x] **D4**：无匹配 →「无匹配文档」
- [x] **D5**：键盘导航与 Esc

### 测试

- [x] `AgentMentionPopover` 或 Composer 单测：filter、keyboard、选中追加
- [x] lazy fetch mock：并发上限、缓存命中（`useMentionSessionIndex` 实现 + `mentionDocuments` 单测）
- [x] 集成：跨博主 chip + turn prompt 含 mention attachment（沿用 P1 `test_agent_prompt_attachments.py`）

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop exec vitest run src/features/agent/AgentComposer.test.tsx 2>/dev/null || pnpm --filter m2t-desktop test
pytest tests/unit/test_api_agent_threads.py -v -k activate
# 手工：
# media2text serve --port 8765 && pnpm --filter m2t-desktop tauri dev
# 输入 @ → 搜其他博主 → 选摘要 → chip 出现 → 发送
```

## 非目标范围

- `GET /api/agent/context-documents` 统一搜索 API（P2 可选 follow-up）
- B 站 archive/dynamic 文档进 `@` 列表
- inline `@pill` 富文本
- 修改 P1 chip 移除 / session 绑定语义

## 依赖与顺序

- **依赖**：P1 **必须**已合并
- **阻塞**：Epic 验收 P2c

## 实现备注

- 分支：`issue-257-agent-context-p2-mention-popover`
- GitHub Issue: [#257](https://github.com/oychao1988/media2text/issues/257)
