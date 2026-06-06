# m2t-desktop Hermes M1：Tool 移植 + replay + WS turn 事件

## 背景

M0 交付 SessionDB 与 echo turn。M1 实现 Hermes 对齐的 **完整 agent loop**：`m2t_*` domain tools + agent 内拦截的 `memory`/`session_search`/`skills_*` 注册、`model_tools.handle_function_call()`、mock/real LLM tool loop、**WS `/api/agent/stream`** 推送 turn 事件（§12.2）。

**参考**：Hermes §10–11、§21.3–§21.5、规格 H1/H2/H7/H9

**依赖**：M0 已合并。**阻塞**：M2（前端切 WS）。

## 验收标准

### Task 1 — Tool registry

- [x] `agent/tools/registry.py` + `toolsets.py`；默认 toolset `m2t-core`
- [x] 移植 v1 sidecar 全部 `m2t_*` tools 至 `agent/tools/m2t_*.py`（直调 core，无 HTTP 自调用）
- [x] `agent/model_tools.py`：Hermes 核心名 agent 内拦截 — `memory`、`session_search`、`skills_list`、`skill_view`（M1 可为 stub 返回固定 JSON，完整实现 M3/M4）
- [x] `IterationBudget`（`agent/iteration_budget.py`）+ `agent.max_turns` 配置

### Task 2 — Agent loop

- [x] `AIAgent.run_conversation()`：load replay → frozen prompt → LLM loop → persist tool_call/tool_result rows
- [x] `runtime_provider.py` OpenAI-compatible mode（复用 `summarize.llm.providers`）
- [x] `_interruptible_api_call` + `POST /api/agent/turns/{turnId}/cancel`
- [x] 并发 tool：`ThreadPoolExecutor` 多 tool_call 并行（§21.5）
- [x] `max_tool_output_chars` 截断后进 DB

### Task 3 — WebSocket

- [x] `WS /api/agent/stream?threadId=` 推送 §12.2 事件类型（`turn.start`、`message.assistant.delta`、`tool.start`、`tool.result`、`turn.end`、`error`）
- [x] 字段与 v1 PiEvent **对齐**，便于 React 最小改动

### Task 4 — Prompt

- [x] `prompt_builder.build_system_prompt()`：stable/context/volatile 分层；manifest 摘要进 context tier
- [x] `resolve_profile()` stub（M5a 前固定 workspace `data/.agent/`）

### 测试

- [x] `pytest tests/unit/test_agent_tools.py -v -m agent` — registry schema 名：`memory` 非 `m2t_memory`
- [x] `pytest tests/unit/test_agent_run_conversation.py -v -m agent` — mock LLM 固定 tool_calls，第二轮引用第一轮 fact（H1/H2）
- [x] `pytest tests/unit/test_api_agent_stream.py -v -m desktop` — WS 事件序列

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_agent_tools.py tests/unit/test_agent_run_conversation.py tests/unit/test_api_agent_stream.py -v -m "agent or desktop"
ruff check src/media2text/agent/
```

## 非目标范围

- FTS / 真 memory 写盘（M3）
- skills 渐进披露索引（M4）
- 删 Node sidecar / React 改 WS 客户端（M2）
- Anthropic `prompt_caching.py`（可 stub；完整 M3+）

## 实现备注

- 分支：`issue-181-hermes-m1-tools-ws`
- GitHub Issue: [#181](https://github.com/oychao1988/media2text/issues/181)
- 依赖 [#180](https://github.com/oychao1988/media2text/issues/180)
