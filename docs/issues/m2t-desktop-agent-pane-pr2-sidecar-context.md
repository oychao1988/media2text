# m2t-desktop Agent Pane PR2：Sidecar context.refresh 扩展（D2）

## 背景

Agent sidecar 的 `context.refresh` 目前只传 `creatorId` / `sessionId` / `threadId`；`hydrateContextFromApi` 固定 `GET /api/sessions/{sessionId}`，对 VOD 无效。

规格 D2：扩展 refresh 载荷，含 `transcriptPath`、`summaryPath`、`sessionKind`、可选 `contextMode`；有 path 时 **跳过** session GET。

**参考**

- 计划 Task 4–5：[2026-06-06-m2t-desktop-agent-pane.md](../superpowers/plans/2026-06-06-m2t-desktop-agent-pane.md)
- **依赖 PR1** 合并（API 返回 path 字段供桌面端转发）

## 验收标准

### Sidecar（Task 4）

- [ ] `applyRefreshPayload(ctx, payload)` 设置 `transcriptPath`、`summaryPath`、`sessionKind`、`contextMode`
- [ ] `hydrateContextFromApi`：若 `ctx.transcriptPath` 或 `ctx.summaryPath` 已设，**不**请求 `/api/sessions/{id}`
- [ ] `main.ts` 的 `context.refresh` handler 调用 `applyRefreshPayload` 后 `reloadContext()`
- [ ] `packages/m2t-agent-sidecar/src/context.test.ts` 覆盖 path-first hydrate

### Desktop 桥接（Task 5）

- [ ] `agentSidecar.ts` 导出 `buildContextRefreshPayload`，含 paths + kind
- [ ] `sendAgentContextRefresh` 将扩展字段传给 Tauri invoke
- [ ] `agentSidecar.test.ts` 断言 payload 形状

### 测试

- [ ] `pnpm --filter m2t-agent-sidecar test`
- [ ] `pnpm --filter m2t-desktop test -- agentSidecar`

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-agent-sidecar test
pnpm --filter m2t-desktop test -- agentSidecar
```

## 非目标范围

- 布局 preset / TranscriptPane 挂载（PR3）
- Agent Tab / 历史侧栏 UI（PR4）
- 修改 Pi 工具语义

## 实现备注

- 分支：`issue-171-agent-sidecar-context`
- GitHub Issue: [#171](https://github.com/oychao1988/media2text/issues/171)
- 阻塞 PR4；可与 [#172](https://github.com/oychao1988/media2text/issues/172) 并行
