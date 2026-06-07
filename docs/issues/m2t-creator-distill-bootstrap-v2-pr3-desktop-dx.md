---
issue: 224
epic: creator-distill-bootstrap-v2
github: 224
branch: issue-224-distill-bootstrap-v2-pr3-desktop-dx
depends_on: [222]
spec: docs/superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md
spec_ids: [CD12]
plan: docs/superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md
---

# m2t Creator Distill Bootstrap v2 PR3：Desktop Tavily 配置 + Doctor

## 背景

Tauri sidecar **不继承** `~/.zshrc`；Bootstrap 六路 Web 需 `TAVILY_API_KEY` 经 Desktop **写入项目 `.env`**（CD12），对齐 LLM Provider / 飞书 webhook 通路。本 PR 仅 DX：config DTO、AI 段 UI、doctor 检查；**不**改 bootstrap job 编排。

**参考**：[规格 §5.2.2、§15](../superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md) · [计划 Phase v2.1b-dx Tasks 7–9](../superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md)

**依赖**：#222（`bootstrap_web_research` 等 config 字段）。**可与 #223 并行**。**阻塞**：#225（端到端需 key 通路）。

## 验收标准

### Task 1 — config DTO

- [x] GET `/api/config`：`tavilyConfigured`, `tavilyApiKey`（掩码）, `tavilyApiKeyEnv`, `bootstrapWebResearch`
- [x] PATCH：`tavilyApiKey` → `_apply_tavily_api_key()`（`upsert_env_var` + `reload_dotenv(override=True)`；忽略 `***`）
- [x] PATCH：`bootstrapWebResearch` → 写 `config.yaml`
- [x] `tests/unit/test_api_config_dto.py` 增补 PATCH tavily 用例

### Task 2 — doctor

- [x] `bootstrap_web_research: true` 时追加 check `web_search_tavily`（用 `resolve_tavily_api_key`，**非**仅 `os.environ`）
- [x] 同条件下已有 / 补充 `summarize` LLM 可用性提示（Web-only bootstrap 仍须 distill LLM）
- [x] `tests/unit/test_doctor_distill_web.py` 通过

### Task 3 — Desktop UI

- [x] `apps/m2t-desktop/src/lib/types.ts`：`ConfigDto` / `ConfigPatch` 新字段
- [x] `ConfigForm.tsx` `#config-panel-ai`：`ConfigAiPanel` 与 `#config-ai-agent-card` **之间**插入 `#cfg-distill-card`（Bootstrap Web toggle、Tavily password、状态）
- [x] 保存后 GET 显示 `tavilyConfigured: true`；**不重启** sidecar 可读 `.env`（热加载）
- [x] `pnpm --filter m2t-desktop test` 通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_api_config_dto.py tests/unit/test_doctor_distill_web.py -v -m desktop
pnpm --filter m2t-desktop test
```

## 非目标范围

- Tavily 六路实现（#223）
- `bootstrap.py` 编排（#225）
- Cursor `mcp.json` / Tavily MCP 配置
- `bing_cn` provider UI（v2.3）

## 实现备注

- 分支：`issue-224-distill-bootstrap-v2-pr3-desktop-dx`
- GitHub Issue: [#224](https://github.com/oychao1988/media2text/issues/224)
