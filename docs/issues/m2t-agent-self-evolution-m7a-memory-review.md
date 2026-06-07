---
issue: 215
epic: agent-self-evolution
github: 215
branch: issue-215-agent-m7a-memory-review
depends_on: []
spec: docs/superpowers/specs/2026-06-07-m2t-agent-self-evolution-design.md
spec_ids: [S1, S2, S3, S4, S5, S6]
manual_ac: []
epic_manifest: docs/issues/epic-manifests/agent-self-evolution.yaml
---

# m2t Agent 自进化 M7a：Memory Hermes 契约 + Background Review

## 背景

Hermes M0–M6 已交付 `AIAgent`、文件型 `memory` tool（`read`/`write`/`append`）与 compression lineage，但 **缺少** post-turn background review、Hermes 条目语义（`§` 分隔 `add`/`replace`/`remove`）、以及跨 turn 的 nudge 计数持久化。M7a 补齐聊天驱动自进化闭环的第一段：Memory 契约 + nudge + review fork（**不含** `skill_manage` / Curator）。

**参考**：[自进化规格 §5–§8、§10、§13 S1–S6](../superpowers/specs/2026-06-07-m2t-agent-self-evolution-design.md) · [实施计划 M7a Tasks 1–7](../superpowers/plans/2026-06-07-m2t-agent-self-evolution.md)

**依赖**：Hermes M3（memory/compression）、M5a（creator profile 根目录）。**阻塞**：M7b（`skill_manage`）、M7c（Curator）。

## 验收标准

### Task 1 — 配置项

- [ ] `MemoryConfig` 增加 `nudge_interval`（默认 10，0=禁用 memory review）、`soul_max_chars`、`memory_enabled` 等（spec §5.4）
- [ ] `AgentLoopConfig` 增加 `review_enabled`（默认 true）、`review_max_iterations`（默认 16）
- [ ] `SkillsConfig` / `CuratorConfig` 骨架字段写入 `config.py`（Curator 行为 M7c 才实现）
- [ ] `config.example.yaml` 同步上述键
- [ ] `tests/unit/test_agent_config_self_evolution.py` 通过

### Task 2 — `sessions.agent_state_json`

- [ ] `_migrate_hermes_v4`：`ALTER TABLE sessions ADD COLUMN agent_state_json TEXT`
- [ ] `agent_state.py`：`AgentState`（`turns_since_memory`、`review_in_flight`、`cached_system_prompt`）；`load`/`save`/`hydrate_turns_since_memory`
- [ ] `SessionDB`：`update_agent_state_json`、`count_user_messages`、`copy_agent_state`（compression fork 复制计数，spec O1/ER1）
- [ ] `review_in_flight` spawn 前置 true、线程 `finally` 清 false（ER8）
- [ ] S2：续聊 hydrate 使用 `prior_user_turns % nudge_interval`

### Task 3 — MemoryStore § 条目

- [ ] `MemoryStore.add/replace/remove/list_entries`；磁盘格式 `§` 分隔条目（S1）
- [ ] 无 `§` 的 legacy `MEMORY.md`（含 evolve bullet）在首次 `add`/`replace`/`read` 时惰性归一化为 `§` 前缀整文件一条
- [ ] 保留 `scan_content` 与 profile 级 char limit
- [ ] `tests/unit/test_memory_store_entries.py` 通过

### Task 4 — memory tool Hermes 契约

- [ ] `model_tools._handle_memory` 支持 `add` / `replace` / `remove` / `read`
- [ ] `write` / `append` **保留 6 个月**；返回 `deprecated: true`（S11 部分，M7b 不重复）
- [ ] `tools/registry.py` 更新 `memory` tool schema 的 `action` enum
- [ ] 扩展 `tests/unit/test_agent_memory.py`（add/replace/remove + deprecation）

### Task 5 — Background review 模块

- [ ] `background_review.py`：vendored `_MEMORY_REVIEW_PROMPT`（+ scope hint）；`REVIEW_TOOL_NAMES = {memory, skill_manage, skills_list, skill_view}`
- [ ] `agent_turn_hooks.py`：`ReviewFlags`、`compute_review_flags`、`maybe_spawn_background_review`
- [ ] M7a：`skill_manage` 不在 valid tools 时 **永不** `review_skills=True`（ER5）
- [ ] Review 线程 `open_db()` 独立连接；禁止复用 foreground 已 close 的 `SessionDB`（ER3）
- [ ] `review` toolset 仅注册 whitelist 工具；非 whitelist 返回 deny
- [ ] `tests/unit/test_background_review.py` 通过

### Task 6 — AIAgent 挂钩

- [ ] Turn 开始 hydrate + user message 后 `turns_since_memory += 1`
- [ ] 每次 LLM 返回 `tool_calls`：`iters_since_skill += 1`（本 turn 内存计数，不持久化）
- [ ] **压缩前** `copy.deepcopy(messages)` 作为 review 快照（ER2）；`finally` 顺序：compress → title → `turn_end` → spawn review
- [ ] `context_compressor` fork 时 `copy_agent_state(parent, child)`
- [ ] Prompt cache：binding/profile 未变时复用 `cached_system_prompt`（ER4）
- [ ] S3：review fork 拒绝 `m2t_*` 工具
- [ ] S4：review 使用与主 turn 相同 provider/model（mock 断言）
- [ ] S5：主 turn `TurnCancelled` 或无 final assistant 文本 → 不 spawn review
- [ ] `tests/unit/test_agent_nudge_counters.py`、`tests/unit/test_review_snapshot_order.py` 通过

### Task 7 — Profile 隔离集成

- [ ] S6：review 写入 creator A 的 `.agent/MEMORY.md`；creator B profile 不可见
- [ ] `tests/unit/test_api_agent_review_e2e.py`（mock LLM + thread join）通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_agent_config_self_evolution.py tests/unit/test_memory_store_entries.py tests/unit/test_agent_state_persistence.py tests/unit/test_agent_nudge_counters.py tests/unit/test_background_review.py tests/unit/test_review_snapshot_order.py tests/unit/test_agent_memory.py tests/unit/test_api_agent_review_e2e.py -v -m agent
ruff check src/media2text/agent/
```

## 非目标范围

- `skill_manage` 工具实现与 skill nudge 触发（M7b）
- Curator、idle tick、`media2text agent curator` CLI（M7c）
- Honcho / 外部 memory provider
- Desktop review toast / WS 通知（O2：v1 仅日志）
- 将 distill/evolve job 合并进 background review
- 跨 `session_id` 合并 nudge 计数

## 实现备注

- 分支：`issue-215-agent-m7a-memory-review`
- GitHub Issue: [#215](https://github.com/oychao1988/media2text/issues/215)
