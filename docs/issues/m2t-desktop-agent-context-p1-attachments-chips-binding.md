---
epic: agent-context-attachments
issue: 255
github: 255
branch: issue-255-agent-context-p1-attachments
depends_on: [254]
spec: docs/superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md
---

# m2t-desktop Agent 上下文 P1：ContextAttachment + chips + binding/activate + Python prompt

## 背景

产品 **D2/D4**：选中历史场次后 **默认附加** 转写/摘要为 Composer 上方 **chip**；× 仅移除文档，**保留 `sessionId`**；场次默认与 `@` 引用 **累加**（path 去重）。

工程 **E1**：chip UI、binding、activate、**Python turn prompt** 为 **同一里程碑**；仅 chip 无 binding 不算 D4 完成。

工程 **E2/E3/E5**：turn 注入以 **`prompt_builder`（Python）** 为主；**per-tab attachments**（`tabEntryKey`）；activate PATCH 失败 **toast**，禁止静默 `.catch`。

**参考**

- 规格 §2、§4、§7、§0.4 E1–E3/E5：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)

**依赖**：P0 [#254](https://github.com/oychao1988/media2text/issues/254) 建议先合并；类型与 UI 可与 P0 并行开发

## 验收标准

### 数据模型与工具

- [x] `ContextAttachment` 类型（`id`, `docType`, `path`, `label`, `creatorId`, `creatorName`, `source: 'session' | 'mention'`）
- [x] `agentAttachments.ts`：`dedupeByPath`、`legacyBindingToAttachments`、`filterByContextMode`
- [x] `useAgentAttachments`：per-tab map（key = `tabEntryKey`）；`appendSessionAttachments` / remove / 读 active tab

### 状态分层（E3）

- [x] `AppShell` 广播 **`SessionDocumentsOffer`**（本场次可用 transcript/summary paths）；**不**持有 attachments 数组
- [x] 仅 **active tab** handler 调用 `appendSessionAttachments(offer)`；切换 tab 不污染其他 tab chips
- [x] draft：attachments 存 React state；关 draft 丢弃
- [x] thread：增删 chip → `PATCH /api/agent/threads/{id}/activate` `{ attachments }`

### Chip UI（§4.2）

- [x] `AgentAttachmentStrip` + `AgentAttachmentChip` 于 `.agent-composer-wrap` 内、textarea **之上**
- [x] label / docType 文案 / 可选 size；跨博主前缀 `creatorName ·`
- [x] × 移除单 attachment；**不** `clearSession`（D2）
- [x] `contextMode` 过滤项：降低 opacity + `title="当前 Tab 未注入上下文"`（与 P1b 联调；P1 可先写死 `both` 或随 P1b 合并）

### 场次自动附加（§4.1）

- [x] 历史 live/vod、回放场次、partial live → 按有无转写/摘要追加 chip（`source: 'session'`）
- [x] path 去重；切换场次 **追加** + 更新主 `sessionId`；不清空跨博主 chip
- [x] 无转写 → toast「该场次暂无转写」

### API / 持久化（§7.1）

- [x] `PATCH /api/agent/threads/{id}/activate` body 扩展：`attachments`, `contextMode`（及 legacy `transcriptPath`/`summaryPath` 过渡）
- [x] `attachments: []` 清空文档；**不** imply `clearSession`
- [x] `hermes_state` / `SessionDB.activate_thread` 同步扩展；legacy 读入迁移 synthetic attachments

### Python turn 注入（E2，必做）

- [x] `prompt_builder.build_system_prompt` context tier 增加 **「附加文档」** 小节（path、label、docType、creatorName；经 `contextMode` 过滤）
- [x] legacy binding 经 `legacyBindingToAttachments` 再渲染

### activate 错误（E5）

- [x] `useM2tAgent`：PATCH activate 失败 **toast**（含重试提示）；删除空 `.catch(() => {})`

### 规格验收 B1–B5

- [x] **B1–B2**：有转写+摘要 → 1–2 chip；仅转写 → 单 chip
- [x] **B3**：× 移除转写 chip → `sessionId` 仍在 binding
- [x] **B4**：切换场次后 chips 累加（`@` 在 P2）
- [x] **B5**：× 可 focus；`aria-label` 含文档描述

### 测试

- [x] `agentAttachments.test.ts`（或同级）：dedupe、legacy 迁移、filterByContextMode
- [x] `useM2tAgent.test.ts`：activate attachments round-trip；失败 toast
- [x] `tests/unit/test_api_agent_threads.py`：activate attachments round-trip
- [x] `tests/unit/test_agent_prompt_attachments.py`（新建或扩展现有 prompt 测试）：prompt 含 attachments 块

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop exec vitest run src/features/agent/useM2tAgent.test.ts
pytest tests/unit/test_api_agent_threads.py tests/unit/test_agent_memory.py -v -k "activate or attachment or prompt"
# 新建 test 文件若已添加：
pytest tests/unit/test_agent_prompt_attachments.py -v
pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop --tb=short -q
```

## 非目标范围

- `@` popover（P2）
- TranscriptPane tab → `contextMode` 完整联动（P1b；P1 可预留字段）
- sidecar `context.ts` 同步（[#258](https://github.com/oychao1988/media2text/issues/258) follow-up，非验收闸门）
- B 站 archive/dynamic 进列表
- 附件二进制上传、inline `@pill` 富文本
- v1 附件数量硬上限 UI 截断

## 依赖与顺序

- **依赖**：P0 建议先合并（左栏 draft 联动）
- **阻塞**：P2 `@` popover、Epic 验收（P2c）

## 实现备注

- 分支：`issue-255-agent-context-p1-attachments`
- GitHub Issue: [#255](https://github.com/oychao1988/media2text/issues/255)
