# Desktop Runtime PR2：RuntimeHealthLoop + WS + 前端去轮询

## 背景

PR1 交付 `/api/runtime` 与 embedded `MonitorSupervisor` 后，Desktop 仍通过 `DaemonCard`（5s）与 `useDaemonRunning`（8s）重复轮询 `/api/daemon`，sidecar 日志密集。本 Issue 落地 **PR2**：`RuntimeHealthLoop` 推送 WS、`EventsProvider` 单连接、`RuntimeProvider`、组件删 dual poll。

**前置**：Desktop Runtime PR1 已合并。

**参考**

- 设计：[2026-06-05-desktop-runtime-design.md](../superpowers/specs/2026-06-05-desktop-runtime-design.md) §3.5–3.6、§8 PR2、§12 fixes 4–5
- 代码锚点：`api/services/events_hub.py`、`features/creators/useEventsWs.ts`、`DaemonCard.tsx`、`LeftRail.tsx`

## 验收标准

### Task 1 — WS 事件类型

- [ ] 扩展 `EventType`：`runtime.health`、`queue.updated`（payload 见 spec §3.5）
- [ ] `runtime.health` 默认发 **diff**（health 档位、tick_age、queues 变化）；HTTP `/api/runtime` 仍全量
- [ ] `tests/unit/test_api_events_ws.py` 扩展：订阅后收到 `runtime.health`

### Task 2 — `RuntimeHealthLoop`

- [ ] 新增 `api/services/runtime_health_loop.py`：`run_runtime_health_loop(app, cfg, stop)`，间隔 1–2s 读 DB + supervisor，diff 后 publish
- [ ] lifespan 与现有 `run_drain_loop` 并行启动/停止
- [ ] health 档位变化立即 publish；否则按 `desktop.runtime_ws_interval_sec` 心跳
- [ ] `tests/unit/test_api_runtime_health_loop.py`

### Task 3 — 前端 `EventsProvider` + `RuntimeProvider`

- [ ] 合并现有 Creators WS 为 **单连接** `EventsProvider`，dispatch `creator.updated` / `runtime.health` / `queue.updated`
- [ ] `RuntimeProvider`：mount 时 `GET /api/runtime` 一次；WS 更新 state；reconnect 全量 GET
- [ ] WS 断开 fallback：`GET /api/runtime` 每 **60s**（`runtime_http_fallback_sec`），非 5s
- [ ] `pnpm --filter m2t-desktop test` 新增/扩展 RuntimeProvider 单测

### Task 4 — 组件改造

- [ ] `DaemonCard`：消费 `useRuntime()`；删除 5s `/api/daemon` poll；启停改 `/api/runtime/start|stop`
- [ ] `LeftRail`：读 `runtime.health !== 'stopped'`；删除 `useDaemonRunning` 8s poll
- [ ] `ConfigForm`：`requires_daemon_restart` 时调 `POST /api/runtime/restart`（替换 daemon stop/start）
- [ ] `useLiveStatus`：`active_recordings` 摘要来自 runtime context；**保留** lazy `GET /api/live/status?creator=` 作 per-creator 详情

### Task 5 — 成功指标 R1

- [ ] Desktop 常态 WS 连接时 sidecar **无密集** `GET /api/daemon`（可 grep serve 日志或 pytest mock）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"

pytest tests/unit/test_api_runtime_health_loop.py \
  tests/unit/test_api_events_ws.py \
  tests/unit/test_api_runtime.py \
  -v -m desktop

pnpm --filter m2t-desktop test
ruff check src/media2text/api/services/runtime_health_loop.py
```

**手动验收**

```bash
media2text serve --port 8765
pnpm --filter m2t-desktop tauri dev
# 打开 App 30s，sidecar stdout 无连续 GET /api/daemon
# DevTools WS：收到 runtime.health
```

## 非目标范围

- Health 三态 UI 颜色、`health_reasons` 展示、日志自动刷新（→ PR3）
- post-process / pipeline API（→ PR4）
- 删除 `/api/daemon` 路由
- 改 `useLiveStatus` 完全移除 per-creator GET（spec 明确保留 lazy load）

## 依赖与顺序

- **依赖**：Desktop Runtime PR1
- **建议分支**：`issue-<N>-desktop-runtime-pr2`
- **可与 PR3/PR4 并行**：PR2 合并后

## 实现备注

- GitHub Issue: [#159](https://github.com/oychao1988/media2text/issues/159)
- 分支：`issue-159-desktop-runtime-pr2`
- eng review §12 fix #4–#5
