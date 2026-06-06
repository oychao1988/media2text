# m2t-desktop Hermes M5a：Creator Profile + Agent Pane 双轨 UI（D8/D16）

## 背景

v2.1 需 **博主级 Agent Profile**（D13–D16）与 Agent Pane 文档对齐：全局/博主双轨 thread、历史栏筛选、409 block send、全局 badge（[#173](https://github.com/oychao1988/media2text/issues/173) 的 toast-only 行为 **supersede**）。

**参考**

- Hermes §24.1、H11–H13、H18
- [agent-pane-design](../superpowers/specs/2026-06-06-m2t-desktop-agent-pane-design.md) §1.1、A10–A14

**依赖**：M0（nullable `creatorId` + 409）、M2（WS Agent UI）。**阻塞**：M5b/M5c。

## 验收标准

### Task 1 — `profile_resolver`

- [ ] `agent/profile_resolver.py` — `AgentProfileContext`、`resolve_profile(creator_id=None|id)`
- [ ] workspace vs `creators/{sec_uid}/.agent/` 路径；USER/MEMORY/SOUL **二选一** volatile（D15）
- [ ] `build_skills_index()` **双根**：`packages/agent-skills/` + 博主 `skills/`；同名博主覆盖全局
- [ ] `model_tools.get_tool_schemas()` 按 profile `enabled_toolsets` 过滤（默认仅 `m2t-core`）

### Task 2 — Profile API

- [ ] `GET/PATCH /api/agent/profiles/workspace`、`GET/PATCH .../profiles/creators/{id}`
- [ ] `GET /api/agent/threads?creatorId=` — 筛选「当前博主」（A12：不含全局 thread）
- [ ] 懒创建 `creators/{sec_uid}/.agent/` 模板（`profile.yaml` 默认 `m2t-core`）

### Task 3 — Agent Pane UI（更新 #173）

- [ ] 历史栏：`全部` | `当前博主` 筛选 + **「新建全局会话」**
- [ ] 页签/列表 **「全局」** badge（`creator_id === null`）
- [ ] `#agent-mismatch-banner`：博主 thread sidebar 不一致 → **Composer 禁用** + CTA「切换到该博主」（非 toast-only）
- [ ] Vitest：409 mock、Composer disabled、全局 thread 任意 sidebar 可 send

### Task 4 — Prompt 集成

- [ ] `build_system_prompt()` 使用 `resolve_profile()`；博主 thread 不含 workspace USER/MEMORY（H11/H17）

### 测试

- [ ] `pytest tests/unit/test_agent_profile_resolver.py -v -m agent`
- [ ] `pnpm --filter m2t-desktop test` — AgentHistorySidebar / mismatch / global create

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_agent_profile_resolver.py tests/unit/test_api_agent_threads.py -v -m "agent or desktop"
pnpm --filter m2t-desktop test
```

## 非目标范围

- 蒸馏 bootstrap / evolve job（M5b/M5c）
- Terminal / delegate（M6）
- 博主设置抽屉 SOUL 编辑器（可 stub 只读）

## 实现备注

- 分支：`issue-185-hermes-m5a-profile-ui`
- GitHub Issue: [#185](https://github.com/oychao1988/media2text/issues/185)
- 合并后开 [#186](https://github.com/oychao1988/media2text/issues/186)
