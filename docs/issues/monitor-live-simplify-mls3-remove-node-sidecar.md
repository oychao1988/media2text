---
epic: monitor-live-simplify-2026-07-06
github: 389
branch: issue-389-mls3-remove-node-sidecar
depends_on: []
---

# MLS-3：移除 Node m2t-agent-sidecar

GitHub Issue: [#389](https://github.com/oychao1988/media2text/issues/389)

规格：§3 P1-4；Hermes M2 已迁 Python Agent（`media2text serve` + `/api/agent/*`）

## 背景

Tauri 仅 spawn `python_sidecar`；`packages/m2t-agent-sidecar` 与 bundle 为死代码。

## 验收标准

- [x] 删除 `packages/m2t-agent-sidecar/`（或留 `README.md` 说明已废弃）
- [x] 删除 `apps/m2t-desktop/src-tauri/resources/agent/start-sidecar.mjs` 与 bundle 产物
- [x] 更新 `pnpm-workspace.yaml` / lockfile（若引用 sidecar）
- [x] `scripts/agent_m2_verify.py` 等仍通过
- [x] Desktop agent turn 仍经 Python WS（手工或现有 Vitest mock）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_desktop_agent.py tests/unit/test_api_agent.py -v -m desktop 2>/dev/null || pytest tests/unit/test_api_agent.py -v
pnpm --filter m2t-desktop test
python scripts/agent_m2_verify.py
```

## 非目标范围

- `/api/chat/*` 路由删除（MLS-6）
