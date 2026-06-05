# Desktop Runtime PR4：管道 API + 移除 CLI spawn

## 背景

Desktop / Agent 仍通过 subprocess 调用 `media2text post-process` / `pipeline` CLI；`daemon.py` 内 `Popen(monitor watch --daemon)` 与 PR1 embedded supervisor 重复。本 Issue 落地 **PR4**：HTTP 直调 core、Agent tools 迁移、删除 daemon 服务内 CLI spawn、移除 deprecated `/api/daemon`。

**前置**：Desktop Runtime PR1 已合并；PR2/PR3 可并行未完成，但本 PR 依赖 PR1 supervisor。

**参考**

- 设计：[2026-06-05-desktop-runtime-design.md](../superpowers/specs/2026-06-05-desktop-runtime-design.md) §3.4 路由表、§6 M2–M4、§8 PR4、Success R6
- 代码锚点：`api/services/daemon.py`、`packages/m2t-agent-sidecar/src/m2t-tools.ts`

## 验收标准

### Task 1 — Post-process API

- [ ] `POST /api/post-process/run`：`body: { limit?: number }` → 包装 `drain_pending_jobs` / 现有 core
- [ ] `POST /api/post-process/retry/{job_id}` → 包装 repo retry
- [ ] JSON 字段与 CLI `post-process run --json` 对齐（或文档化差异）
- [ ] `tests/unit/test_api_post_process.py`

### Task 2 — Monitor tasks retry

- [ ] `POST /api/monitor-tasks/retry/{task_id}` → Phase 3 repo reset/retry
- [ ] `tests/unit/test_api_monitor_tasks.py`（或扩展现有）

### Task 3 — Pipeline async

- [ ] `POST /api/creators/{id}/pipeline/run` → **202** + `{ job_id, status: "queued" }`；异步入队 sync+download+transcribe 链
- [ ] 不入队阻塞 HTTP；job 状态可经 runtime queues 或后续 job API 观测
- [ ] `tests/unit/test_api_pipeline_run.py`

### Task 4 — 移除 CLI spawn

- [ ] `api/services/daemon.py`：**删除** `Popen(["-m", "media2text", "monitor", "watch", "--daemon"])`
- [ ] `start`/`stop` 委托 `MonitorSupervisor`（与 `/api/runtime/*` 一致）
- [ ] grep `src/media2text/api`：无 `Popen.*media2text`（**auth login** 交互式 spawn 除外）
- [ ] 移除 `/api/daemon` 路由（或返回 410 + 指向 `/api/runtime`）；更新 `test_api_daemon.py` → 迁移或删除

### Task 5 — Agent sidecar

- [ ] `m2t-tools.ts`：`m2t_get_live_status` / daemon 相关 tool 改指向 `/api/runtime`
- [ ] post-process / pipeline tool 改 HTTP API
- [ ] sidecar 单测或 smoke 更新

### Task 6 — 文档

- [ ] `CLAUDE.md` / desktop 验收 doc：`/api/runtime` 为首选；CLI daemon 仍可用于终端用户
- [ ] `config.example.yaml` desktop 段注释更新

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"

pytest tests/unit/test_api_post_process.py \
  tests/unit/test_api_monitor_tasks.py \
  tests/unit/test_api_pipeline_run.py \
  tests/unit/test_api_runtime.py \
  -v -m desktop

rg 'Popen.*media2text' src/media2text/api --glob '*.py' || true
# 预期：仅 auth 相关或零匹配

pnpm --filter m2t-desktop test
ruff check src/media2text/api
```

## 非目标范围

- 合并 `post_process_jobs` 与 `monitor_tasks` 表
- Desktop 队列 bulk retry UI
- 改 `media2text auth login` 的 CLI spawn
- Tauri 双 sidecar 架构变更

## 依赖与顺序

- **依赖**：Desktop Runtime PR1（supervisor + runtime routes）
- **建议分支**：`issue-<N>-desktop-runtime-pr4`
- **建议**：PR2 合并后再删 `/api/daemon`，避免 Desktop 旧 poll 404

## 实现备注

- GitHub Issue: [#161](https://github.com/oychao1988/media2text/issues/161)
- 分支：`issue-161-desktop-runtime-pr4`
- PR 正文 `Fixes #<N>`；合并顺序 PR1 → PR2 →（PR3 ∥ PR4）
