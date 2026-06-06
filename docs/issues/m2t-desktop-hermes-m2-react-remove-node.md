# m2t-desktop Hermes M2：React 切 WS + 移除 Node Agent sidecar

## 背景

M1 提供 Python Agent loop + WS。M2 将 Desktop **数据面**从 Tauri NDJSON + Node `m2t-agent-sidecar` 迁至 **HTTP turn + WS stream**（D4），删除 `agent_sidecar.rs` / `packages/m2t-agent-sidecar` 默认路径（D2）。

Agent Pane **布局/页签/历史栏 UI 不变**（D9）；仅替换 `useM2tAgent` 与 sidecar 依赖（Hermes §13）。

**参考**：[agent-pane-design](../superpowers/specs/2026-06-06-m2t-desktop-agent-pane-design.md) §7、验收 A9

**依赖**：M1 已合并。**阻塞**：M3+ 可与 M2 并行，但 E2E 以 M2 为 Agent 运行时基线。

## 验收标准

### Task 1 — 前端 Agent 数据层

- [x] `useM2tAgent`：连接 `WS /api/agent/stream`；send 走 `POST /api/agent/threads/{id}/turn`
- [x] 删除 `POST .../messages` 双写；消息列表以 GET messages + WS delta/reconcile 为准
- [x] `PATCH .../activate` 替代 sidecar `context.refresh`（binding/session/paths/contextMode）
- [x] 处理 409 `creator_mismatch`（toast/banner 可先沿用 #173，M5a 再强化）

### Task 2 — 移除 Node sidecar

- [x] 删除或 stub `apps/m2t-desktop/src/features/agent/agentSidecar.ts`
- [x] Tauri：移除 `agent_sidecar.rs` spawn；`pnpm tauri dev` **无 Node 进程**仍 Agent 可用（H8）
- [x] `packages/m2t-agent-sidecar/` 标记 deprecated README；CI 不再 spawn Node agent
- [x] 移除 `config` 中 `desktop.agent.runtime: pi` 分支（或仅保留文档说明回滚用 revert）

### Task 3 — 回归

- [x] 迁移/更新 Vitest：`useM2tAgent`、AgentPanel、tool-card 状态机（mock WS）
- [x] `pnpm --filter m2t-desktop test` 通过（含原 Agent Pane 38 项或等价集，H9）

### Task 4 — 文档

- [x] `CLAUDE.md` Desktop 段：Agent 经 Python API + WS，无 Node sidecar
- [x] 起草 `docs/superpowers/verification/2026-06-06-m2t-desktop-agent-hermes-acceptance.md` 骨架（M2 章节可填）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pnpm --filter m2t-desktop test
pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop
pytest tests/unit/test_api_agent_m2_smoke.py -v -m desktop   # H2 重启续聊 + thread replay + tool WS
python scripts/agent_m2_verify.py                             # M2 全量验证（含 live serve + WS ready）
# 可选手工：pnpm tauri dev — GUI 发消息、tool 卡片视觉确认
```

## 非目标范围

- 历史栏双轨 UI / 全局 thread 新建（M5a；API 已在 M0）
- memory/FTS/compression（M3）
- 删 `/api/chat/*` alias（M4）

## 实现备注

- 分支：`issue-182-hermes-m2-react-ws`
- GitHub Issue: [#182](https://github.com/oychao1988/media2text/issues/182)
- 依赖 [#181](https://github.com/oychao1988/media2text/issues/181)
