# m2t-desktop Hermes M5b：CreatorAgentBootstrap 蒸馏（nuwa 方法论）

## 背景

登记博主后异步生成 **perspective skill + SOUL**（D17），方法论对齐 [nuwa-skill](https://github.com/alchaincyf/nuwa-skill)，落盘 `creators/{sec_uid}/.agent/skills/{slug}-perspective/`（§24.4）。

默认 **`distill.on_creator_add: false`**（O9）；语料不足 → job `deferred`，由 watcher 在首场摘要后 promote（§24.4.4.1）。

**参考**：Hermes §24.4.3–§24.4.7、H19–H20

**依赖**：M5a（profile 路径、`skills_list` 双根）。**阻塞**：M5c。

## 验收标准

### Task 1 — Job 表与 worker

- [ ] 表 `creator_agent_jobs`（§24.4.6 schema）；**DB 为真源**；`distill_state.json` 为 API 缓存
- [ ] `CreatorAgentJobPool` + `creator_distill/bootstrap.py`
- [ ] 幂等：同一 `creator_id` bootstrap 仅一条 `pending|running`
- [ ] 队列优先级：bootstrap priority 5 < evolve 10（evolve 可插队）

### Task 2 — Bootstrap 流程

- [ ] Phase Collect：manifest + summary/transcript 合并，上限 `max_input_chars`
- [ ] chars < `defer_until_min_chars` → `deferred`；**不**失败 `creator add`
- [ ] Phase Distill：LLM → 结构化 JSON → `SKILL.md`（agentskills.io frontmatter）
- [ ] 写 `SOUL.md`、更新 `profile.yaml.default_skills` + `distill.*` 元数据
- [ ] **原子写盘**：`.tmp` + `os.replace`；creator-level 锁（§24.4.6）

### Task 3 — Deferred watcher

- [ ] `creator_distill/deferred.py::maybe_promote_bootstrap`
- [ ] SlowTick 扫描 + `summarize_completed` 钩子 re-enqueue

### Task 4 — API

- [ ] `POST /api/agent/profiles/creators/{id}/distill` `{ force?: bool }`
- [ ] `GET .../distill-status` — 读 DB 聚合

### 测试

- [ ] `test_bootstrap_deferred_low_corpus`、`test_bootstrap_writes_skill`、`test_deferred_watcher_promotes`、`test_distill_atomic_write`（§24.4.10）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,transcribe-cloud,dev]"
pytest tests/unit/test_creator_distill_bootstrap.py -v -m agent
```

## 非目标范围

- Evolve 增量 patch（M5c）
- 公网六路调研（O11：`allow_web_research` 默认 false）
- darwin-skill 八维评分（v3）
- CLI `media2text agent distill`（可选，非阻塞）

## 实现备注

- 分支：`issue-186-hermes-m5b-distill-bootstrap`
- GitHub Issue: [#186](https://github.com/oychao1988/media2text/issues/186)
