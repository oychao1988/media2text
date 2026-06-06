# m2t-desktop Hermes M5c：CreatorAgentEvolve 进化（本地摘要驱动）

## 背景

新直播摘要完成后 **增量更新** 博主 SKILL + MEMORY（D18），读本地 `.summary.md` / `.transcript.md`，禁止整文件重写（§24.4.5）。

默认触发：`summarize_completed`（O10：`new_aweme` 默认关）。

**参考**：Hermes §24.4.5、H21–H22

**依赖**：M5b（SKILL/SOUL 骨架、`creator_agent_jobs`）。可与 M5b 同 PR 拆 commit，但 Issue 独立便于 review。

## 验收标准

### Task 1 — Evolve worker

- [x] `creator_distill/evolve.py`；kind=`evolve`；按 `source_id` 幂等
- [x] 入队：`PostProcessPool` / monitor 钩子在 `summarize_completed` 后
- [x] 增量规则表（§24.4.5）：补案例、标注立场变化、MEMORY bullet 带 `source_id`
- [x] `evolve-log.jsonl` 审计行

### Task 2 — MEMORY 边界

- [x] 超长 MEMORY 合并最旧条目；`profile.yaml.distill.source_session_ids` 去重

### Task 3 — API

- [x] `POST .../evolve` `{ source_id }` 手动补跑
- [x] `GET .../evolve-log` 分页

### Task 4 — Prompt 可见性

- [x] 进化后 `skills_list` 仍可见 `{slug}-perspective`；`skill_view` 含新 `source_id` 引用（H21）

### 测试

- [x] `test_evolve_idempotent`、`test_evolve_memory_bound`（§24.4.10）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_creator_distill_evolve.py -v -m agent
```

## 非目标范围

- Bootstrap 全量重蒸馏
- `new_aweme` 元数据轻量进化（配置默认关）
- 交互式女娲 Phase 0B

## 实现备注

- 分支：`issue-187-hermes-m5c-distill-evolve`
- GitHub Issue: [#187](https://github.com/oychao1988/media2text/issues/187)
