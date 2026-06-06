# m2t-desktop Agent Pane UI 细化 PR3：空态身份条 + draft 页签 + 延迟建 thread

## 背景

锁定 §14.1：**Tab `+` 不再立即 `POST /threads`**，改为 client draft 页签；空态显示身份选择条；首条 send 时 `POST /threads` + turn，draft 晋升为 thread 页签。

**参考**

- 规格 §2.2、§3、§14.1、§11 A3：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md)

**依赖**：建议 PR1 消息区、PR2 历史分组已合并（非硬阻塞）

## 验收标准

### Tab 模型

- [x] `AgentTabEntry`：`{ kind: 'draft', draftId, agentId }` | `{ kind: 'thread', threadId }`
- [x] `useAgentTabs`：`+` → push draft（默认 `agentId: 'global'`）；**不**调用 POST
- [x] 关闭 draft 页签：无 API；丢弃 `draftAgentId`
- [x] 仍遵守最多 5 tab、关 tab 不 DELETE thread

### 空态 UI `#agent-chat-empty`

- [x] 显示条件：激活 tab 为 draft
- [x] `.agent-identity-bar`：logo + picker（灵犀置顶，再博主 listbox）
- [x] 选 Agent 更新 `draftAgentId`、placeholder（全局 vs「向 {name} Agent 提问…」）
- [x] empty 时 `#chat-live` / `#chat-playback` hidden

### 首条发送

- [x] `POST /api/agent/threads`（灵犀 omit `creatorId`；博主传 picker 的 `creatorId`）
- [x] 紧接着 `POST .../turn`；draft tab **晋升** 为 thread tab
- [x] picker 与 POST `creatorId` 一致，避免假 409 mismatch

### 测试

- [x] `useAgentTabs.test.ts`：draft 创建/关闭/晋升；cap 5 含 draft
- [x] 集成 mock：首条 send 仅一次 POST threads

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
# 手工 A3（需 sidecar + Tauri）：
# media2text serve --port 8765
# pnpm --filter m2t-desktop tauri dev
# + 无 network POST；选博主后发首条 → 建 thread + turn；关 draft 无 DELETE
# pytest tests/unit/test_api_chat.py -v -k thread
```

## 非目标范围

- `PATCH` 改绑 creator（API-1，明确不采用）
- 页签头像（PR4；draft 可先占位 abbr）
- 后端 / Agent 协议变更

## 实现备注

- 分支：`issue-201-agent-draft-thread`
- GitHub Issue: [#201](https://github.com/oychao1988/media2text/issues/201)
