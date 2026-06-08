---
epic: agent-context-attachments
issue: 258
github: 258
branch: issue-258-agent-context-sidecar-sync
depends_on: [255]
spec: docs/superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md
---

# m2t-desktop Agent 上下文：sidecar attachments 过渡同步（非验收闸门）

## 背景

桌面端 turn **主路径为 Python** `POST /api/agent/threads/{id}/turn` + `prompt_builder`（E2）。Node sidecar `context.ts` 仍可能被 WS `context.refresh` 消费者使用，需 **过渡对齐** `attachments[]` payload，但 **不以 sidecar 为 D4 Epic 验收依据**。

**参考**

- 规格 §7.2–§7.3 sidecar 过渡说明：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)

**依赖**：P1 [#255](https://github.com/oychao1988/media2text/issues/255) activate / `ContextAttachment` 类型已落地；可与 P1 **同 PR** 或 follow-up

## 验收标准

### `context.refresh` payload（§7.2）

- [x] `packages/m2t-agent-sidecar/src/context.ts`（或等价模块）接受 `attachments`、`contextMode`，与 activate body 对齐
- [x] legacy `transcriptPath` / `summaryPath` 仍可读（过渡）

### `buildSystemPrompt`

- [x] sidecar system prompt 增加 **「附加文档」** 列表块（经 `contextMode` 过滤）
- [x] legacy 双 path 行保留至 sidecar 全量升级

### 测试

- [x] sidecar 单元测试（若已有）：payload 含 attachments 时 prompt 含对应 path
- [x] 无回归：`pnpm --filter m2t-agent-sidecar test`（或 monorepo 等价命令）

## 验证命令

```bash
pnpm --filter m2t-agent-sidecar test 2>/dev/null || pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop test
```

## 非目标范围

- 将 turn 主路径迁回 sidecar LLM
- Epic D4 验收（以 Python prompt 为准）
- 新 REST API

## 依赖与顺序

- **依赖**：P1 activate + attachment 模型
- **阻塞**：无；**非** Epic 合并闸门

## 实现备注

- 分支：`issue-258-agent-context-sidecar-sync`
- GitHub Issue: [#258](https://github.com/oychao1988/media2text/issues/258)
- 可与 P1 同 PR；独立 Issue 便于 reviewer 标为非阻塞 follow-up
