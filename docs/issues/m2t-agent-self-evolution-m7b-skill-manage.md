---
issue: 216
epic: agent-self-evolution
github: 216
branch: issue-216-agent-m7b-skill-manage
depends_on: [215]
spec: docs/superpowers/specs/2026-06-07-m2t-agent-self-evolution-design.md
spec_ids: [S7, S8, S9, S10, S11]
manual_ac: [S10]
epic_manifest: docs/issues/epic-manifests/agent-self-evolution.yaml
---

# m2t Agent 自进化 M7b：skill_manage + Provenance + Usage

## 背景

M7a 交付 memory review fork 与 nudge 基础设施；Agent 仍无法把 workflow 教训写成可复用 SKILL，也无法在 review 中 patch 蒸馏 persona skill。M7b 对齐 Hermes `skill_manage`、`skill_provenance`、`skills/.usage.json` 遥测，并启用 **skill creation nudge**（`creation_nudge_interval`）。

**参考**：[自进化规格 §7、§8.2–§8.3、§10.2、§13 S7–S11](../superpowers/specs/2026-06-07-m2t-agent-self-evolution-design.md) · [实施计划 M7b Tasks 8–11](../superpowers/plans/2026-06-07-m2t-agent-self-evolution.md)

**依赖**：#215（M7a background review + agent_state）。**阻塞**：M7c（Curator 需 `agent_created` 标记与 usage）。

## 验收标准

### Task 1 — skill_usage 遥测

- [ ] `skill_usage.py`：读写 `{profile}/skills/.usage.json`（`use_count`、`view_count`、`patch_count`、`pinned`、`agent_created` 等，spec §7.4）
- [ ] `skills_index.handle_skill_view` 递增 `view_count`
- [ ] skill 加载进 prompt（default_skills / slash）递增 `use_count`（若已有 hook 则接入）
- [ ] `skill_manage` 写操作递增 `patch_count`
- [ ] bundled `packages/agent-skills/` **不写** telemetry
- [ ] `tests/unit/test_skill_usage.py` 通过

### Task 2 — skill_provenance

- [ ] `skill_provenance.py`：`ContextVar` `write_origin`（`foreground` | `background_review`）
- [ ] background review 路径 `write_origin=background_review`；`create` 时 `mark_agent_created`
- [ ] foreground `skill_manage create` **不**标 `agent_created`（S8）
- [ ] `tests/unit/test_skill_provenance.py` 通过

### Task 3 — skill_manage 工具

- [ ] `skill_manage.py`：`create` / `patch` / `edit` / `delete` / `write_file` / `remove_file`
- [ ] 写入根 `{profile_dir}/skills/{name}/SKILL.md`；kebab-case 校验；拒绝 `..` 路径遍历
- [ ] bundled skills **只读** → `PROTECTED_SKILL`
- [ ] distill `{slug}-perspective`：可 patch/edit/write_file（**禁止** `references/research/*`）；**不可** `delete`；默认 **pinned**（S9）
- [ ] `model_tools.py` + `tools/registry.py` 注册 OpenAI schema
- [ ] `toolsets.py`：`_HERMES_NAMES` 与 `m2t-core` 默认含 `skill_manage`；review toolset 含 `skill_manage`
- [ ] S7：`skill_manage patch` 落盘；`skills_list` 可见
- [ ] `tests/unit/test_skill_manage.py` 通过

### Task 4 — Distill pin + skill nudge

- [ ] `creator_distill` bootstrap（或 evolve 落盘）完成时：`skill_usage.pin("{slug}-perspective")` + frontmatter `metadata.hermes.protected: distill`
- [ ] M7b 起：`compute_review_flags` 在 `"skill_manage" in valid_tool_names` 且达 `skills.creation_nudge_interval` 时 `review_skills=True`
- [ ] `skill_manage` 成功执行后 `_iters_since_skill` 归零
- [ ] S10（manual_ac）：mock 集成 — 用户纠正口吻后 review patch `{slug}-perspective` 的 pitfall 段（非 `references/research/*`）

### Task 5 — 兼容与文档

- [ ] S11：`write`/`append` memory 仍可用且返回 `deprecated: true`（M7a 若已交付则回归即可）
- [ ] `CLAUDE.md` Desktop Agent 小节补充 `skill_manage` 一句（可选，与 M7c 文档一并亦可）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_skill_usage.py tests/unit/test_skill_provenance.py tests/unit/test_skill_manage.py tests/unit/test_agent_nudge_counters.py tests/unit/test_background_review.py tests/unit/test_agent_memory.py -v -m agent
ruff check src/media2text/agent/
```

## 非目标范围

- Curator stale/archive/LLM 整理（M7c）
- 删除或覆盖 distill `references/research/*`
- Gateway slash `/curator`
- 将 CreatorAgentEvolve job 改为 chat review
- Docker/ssh terminal 或 delegate 变更

## 实现备注

- 分支：`issue-216-agent-m7b-skill-manage`
- GitHub Issue: [#216](https://github.com/oychao1988/media2text/issues/216)
