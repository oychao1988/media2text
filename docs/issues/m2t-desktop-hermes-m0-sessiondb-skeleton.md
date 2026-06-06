# m2t-desktop Hermes M0：SessionDB 迁移 + AIAgent 骨架 + 双轨 thread API

## 背景

Desktop Agent v1 采用 SQLite（仅 user/assistant）+ Node Pi 内存双轨，切换 thread 后模型无法 replay。规格 [2026-06-06-m2t-desktop-agent-hermes-refactor-design.md](../superpowers/specs/2026-06-06-m2t-desktop-agent-hermes-refactor-design.md) 锁定 **Python 单核 `AIAgent`** + Hermes 同名表 `sessions`/`messages` 为唯一 LLM 真源（D1–D3、D11–D12）。

本单交付 **M0**：DB 迁移、最小 Agent 包布局、`POST /api/agent/threads/{id}/turn` echo turn，以及 Agent Pane 对齐所需的 **双轨 thread API**（D16 可选 `creatorId`、D8 博主 thread **409 creator_mismatch**）。

**参考**

- Hermes §6 schema、§12.1 REST、§21.1 包布局
- Agent Pane D8/D16：[agent-pane-design](../superpowers/specs/2026-06-06-m2t-desktop-agent-pane-design.md) §1.1、§7.1

**依赖**：无（Hermes 系列首单）。**阻塞**：M1–M6。

## 验收标准

### Task 1 — DB 迁移

- [x] Alembic/迁移脚本：`desktop_chat_threads` → `sessions`（含 `display_thread_id`、`parent_session_id` 可空、`creator_id` **nullable**）
- [x] `desktop_chat_messages` → `messages`（`seq`、`role`、`tool_*` 列预留；旧数据仅 user/assistant 仍可 replay）
- [x] 旧表 rename backup（如 `_legacy_desktop_chat_*`）；读写切到新表
- [x] `tests/unit/test_desktop_db_migration.py` 覆盖迁移前后 row 数与 `creator_id` nullable

### Task 2 — `SessionDB` + Agent 包骨架

- [x] `src/media2text/agent/hermes_state.py` — `SessionDB` 实现 §21.4 最小子集：`create_session`、`append_message`、`get_messages_as_conversation`、`get_active_session_for_thread`
- [x] `src/media2text/agent/ai_agent.py` — `class AIAgent`；`run_conversation()` echo：append user → append assistant stub → persist
- [x] `src/media2text/agent/run_agent.py` — CLI 入口 `media2text agent echo <thread_id>`（调试用）
- [x] `src/media2text/agent/prompt_builder.py` — stub 返回三段 tier 占位（stable/context/volatile 字符串非空）

### Task 3 — REST `/api/agent/*`（最小）

- [x] 路由挂载：`GET/POST/PATCH/DELETE /api/agent/threads`、`GET .../messages`
- [x] `POST /api/agent/threads`：`creatorId` **可选**；省略时 `creator_id=NULL`（D16）
- [x] `POST /api/agent/threads/{id}/turn`：异步返回 `{ turnId }`；body 含 `text`、`sidebarCreatorId`（或 header/query 约定）
- [x] 博主 thread（`creator_id` 非空）且 `sidebarCreatorId` ≠ `creator_id` → **409** `{ "code": "creator_mismatch" }`（D8/H3）
- [x] 全局 thread（`creator_id` NULL）→ **跳过** mismatch 校验
- [x] `/api/chat/*` 薄 alias 到 `/api/agent/*`（同 handler，响应头或 JSON 可标 deprecated）

### Task 4 — 配置与依赖

- [x] `config.example.yaml` 增加 `memory.*`、`compression.*`、`agent.max_turns` 段（§14）；默认值与 spec 一致
- [x] `pip install -e ".[desktop,dev]"` 可 import `media2text.agent`

### 测试

- [x] `pytest tests/unit/test_agent_session_db.py -v -m agent`（新建）
- [x] `pytest tests/unit/test_api_agent_threads.py -v -m desktop`（新建：nullable create、409 mismatch）
- [x] `pytest tests/unit/test_desktop_db_migration.py -v -m desktop`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_agent_session_db.py tests/unit/test_api_agent_threads.py tests/unit/test_desktop_db_migration.py -v -m "agent or desktop"
ruff check src/media2text/agent/ src/media2text/api/routes/agent.py
pyright src/media2text/agent/
```

## 非目标范围

- 真实 LLM 调用、tool loop、WS 流（M1）
- `memory` / `session_search` / compression（M3）
- React / Tauri 改动（M2、M5a）
- 删除 Node sidecar（M2）
- `CreatorAgentProfile` / 蒸馏（M5a–M5c）

## 实现备注

- 分支：`issue-180-hermes-m0-sessiondb`
- GitHub Issue: [#180](https://github.com/oychao1988/media2text/issues/180)
- 合并后开 M1 Issue [#181](https://github.com/oychao1988/media2text/issues/181)
