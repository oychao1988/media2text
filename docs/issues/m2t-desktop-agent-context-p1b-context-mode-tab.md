---
epic: agent-context-attachments
issue: 256
github: 256
branch: issue-256-agent-context-p1b-context-mode
depends_on: [255]
spec: docs/superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md
---

# m2t-desktop Agent 上下文 P1b：TranscriptPane tab → contextMode

## 背景

产品 **D3**：`contextMode` **随转写区 Tab**（转写 / 摘要）自动切换；turn 时仅注入当前 tab 对应类型的 attachments，chip 仍全部可见。

**参考**

- 规格 §5：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)

**依赖**：P1 [#255](https://github.com/oychao1988/media2text/issues/255) 的 `ContextAttachment`、`filterByContextMode`、activate `contextMode` 字段；可与 P1 **并行**（TranscriptPane 小改）

## 验收标准

### TranscriptPane → AppShell

- [x] `TranscriptPane` 上抛 `onTabChange(tab: 'transcript' | 'summary')`
- [x] `AppShell` 写入 `sessionContext.contextMode`：`transcript` ↔ `summary`（v1 无第三 Tab）

### 传播链（§5.2）

- [x] `AppShell` → `AgentPanel` / `useM2tAgent` → `PATCH .../activate { contextMode }`
- [x] Tab 切换 **不重算** attachments 列表；仅 turn 时 **过滤** + chip **未启用** 样式

### Turn 行为

- [x] Python `prompt_builder` 仅列出经 `contextMode` 过滤后的 attachments（与 P1 联调）
- [x] `useM2tAgent` send 前 activate 携带当前 `contextMode`

### 规格验收 C1–C3

- [x] **C1**：摘要 Tab + 双 chip → turn 仅读摘要 attachment
- [x] **C2**：切回转写 Tab → turn 仅读转写 attachment
- [x] **C3**：chip 仍全部可见；被过滤项有未启用样式

### 测试

- [x] `agentAttachments.test.ts`：`filterByContextMode` 边界
- [x] `useM2tAgent.test.ts`：tab 切换后 activate payload 含 `contextMode`
- [x] TranscriptPane 组件测试或 AppShell mock：`onTabChange` 触发

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop exec vitest run src/features/agent/useM2tAgent.test.ts
pytest tests/unit/test_agent_prompt_attachments.py -v -k context_mode || pytest tests/unit/test_agent_memory.py -v
# 手工：
# media2text serve --port 8765 && pnpm --filter m2t-desktop tauri dev
# 选双文档场次 → 切摘要 Tab → 发送 → 侧car/日志可见仅 summary path
```

## 非目标范围

- 新增 TranscriptPane 第三 Tab「两者」（映射 `both` 留作未来）
- `@` popover（P2）
- 修改 chip 增删逻辑（P1）

## 依赖与顺序

- **依赖**：P1 类型与 activate 字段（可同 PR 或先 P1 后 P1b）
- **阻塞**：无

## 实现备注

- 分支：`issue-256-agent-context-p1b-context-mode`
- GitHub Issue: [#256](https://github.com/oychao1988/media2text/issues/256)
