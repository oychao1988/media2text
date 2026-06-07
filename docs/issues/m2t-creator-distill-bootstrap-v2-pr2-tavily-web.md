---
issue: 223
epic: creator-distill-bootstrap-v2
github: 223
branch: issue-223-distill-bootstrap-v2-pr2-tavily-web
depends_on: [222]
spec: docs/superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md
spec_ids: [CD6, CD8, CD10, CD11]
plan: docs/superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md
---

# m2t Creator Distill Bootstrap v2 PR2：Tavily + 六路 Web Research

## 背景

Bootstrap v2 首次蒸馏需 nuwa 对齐的 **六路公网调研**，落盘 `references/research/01–06.md`（CD6）。检索 **直连 Tavily REST API**（CD10），不用 inference.sh / `infsh`（CD11）。本 PR 交付 HTTP 客户端 + 六路 orchestrator；**不**改 `run_bootstrap_job` 主流程（#225 接线）。

**参考**：[规格 §5.2、§5.2.1](../superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md) · [计划 Phase v2.1b Tasks 5–6](../superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md)

**依赖**：#222（`DistillConfig` v2 字段）。**阻塞**：#225。**可与 #224 并行**（Desktop 不依赖本 PR 代码路径，但 doctor 会调用 `resolve_tavily_api_key`）。

## 验收标准

### Task 1 — TavilyClient + resolve_tavily_api_key

- [x] `creator_distill/tavily_client.py`：`POST /search`；可选 `extract`（默认 `tavily_extract_top_urls: 0` 不调用）
- [x] `resolve_tavily_api_key()`：**项目 `.env` 优先**于空 `os.environ`（对齐 LLM key 语义）
- [x] HTTP 429/5xx：每请求最多 2 次指数退避；401 不重试
- [x] `tests/unit/test_creator_distill_tavily.py` 通过（mock `httpx`）

### Task 2 — WebSearchProvider

- [x] `creator_distill/web_search.py`：`TavilyWebSearchProvider`；`provider: none` 供单测离线

### Task 3 — 六路 web_research

- [x] `creator_distill/web_research.py`：`run_six_channel_research()` 写 `01-writings.md` … `06-timeline.md`
- [x] 单路「有效内容」：`answer` 非空 **或** denylist 过滤后 `results ≥ 1`（CD5/CD8）
- [x] 单路失败写占位 md + `channel_status`；返回 `WebResearchResult(channels_ok, …)`
- [x] `web_research_max_parallel` 默认 2
- [x] `tests/unit/test_creator_distill_web_research.py` 通过（mock Tavily，无真实网络）

### Task 4 — 配置与示例

- [x] `.env.example` 增加 `TAVILY_API_KEY=` 占位说明

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_creator_distill_tavily.py tests/unit/test_creator_distill_web_research.py -v -m agent
ruff check src/media2text/agent/creator_distill/tavily_client.py src/media2text/agent/creator_distill/web_search.py src/media2text/agent/creator_distill/web_research.py
```

## 非目标范围

- `bootstrap.py` 调用六路（#225）
- Desktop 配置页 / `PATCH tavilyApiKey`（#224）
- `bing_cn` fallback（v2.3）
- 每路 aux LLM 整理（v2.2）
- Evolve 触达 `references/research/*`

## 实现备注

- 分支：`issue-223-distill-bootstrap-v2-pr2-tavily-web`
- GitHub Issue: [#223](https://github.com/oychao1988/media2text/issues/223)
