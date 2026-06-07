---
issue: 217
epic: agent-self-evolution
github: 217
branch: issue-217-agent-m7c-curator
depends_on: [216]
spec: docs/superpowers/specs/2026-06-07-m2t-agent-self-evolution-design.md
spec_ids: [S12, S13, S14, S15]
manual_ac: [S15]
epic_manifest: docs/issues/epic-manifests/agent-self-evolution.yaml
---

# m2t Agent 自进化 M7c：Curator + Idle Tick + CLI + Epic 验收

## 背景

M7a/M7b 交付 memory/skill background review 与 agent 自写 skill 库；长期运行后 skill 会 stale 且缺乏归档治理。M7c 复制 Hermes Curator：auto transition（30d stale / 90d archive）、LLM review fork 整理、备份/rollback，以及 API 进程 **idle tick** 触发；默认 `curator.enabled: false` 直至本阶段验收通过（O5）。

**参考**：[自进化规格 §9、§13 S12–S15、§18](../superpowers/specs/2026-06-07-m2t-agent-self-evolution-design.md) · [实施计划 M7c Tasks 12–14](../superpowers/plans/2026-06-07-m2t-agent-self-evolution.md)

**依赖**：#216（`skill_manage`、provenance、usage）。**阻塞**：Epic `agent-self-evolution` 系列验收。

## 验收标准

### Task 1 — curator 核心

- [x] `curator.py`：Phase 1 auto transition — 30d 未用 → `stale`；90d → 移至 `skills/.archive/`（S13）
- [x] **仅** `agent_created: true` skills 参与；不 touch bundled / distill pinned / foreground-created（S14）
- [x] Phase 2 LLM review fork：`skill_view` + `skill_manage` + archive terminal；`max_iterations=8`；`auxiliary.curator` 配置槽（可选，默认同主模型）
- [x] mutating run 前备份 `skills/.curator_backups/{ts}/`；`curator.backup.keep`（默认 5）
- [x] S12：`curator run --dry-run` 不修改磁盘
- [x] `tests/unit/test_curator_transitions.py` 通过

### Task 2 — Idle tick + CLI

- [x] `curator.enabled` 默认 **false**（O5）；`interval_hours`（168）、`min_idle_hours`（2）
- [x] API / `MonitorSupervisor` idle tick：无 in-flight agent turn ≥ `min_idle_hours` 且距上次 curator ≥ `interval` 时触发
- [x] 首次启用 seed `last_run_at=now`，defer 一整 interval
- [x] CLI（`media2text agent curator`）：
  - `status`
  - `run [--dry-run] [--background]`
  - `pin` / `unpin` / `restore`
  - `rollback [--list]`（S15 manual_ac：恢复备份）
- [x] S15（manual_ac）：mutating run 备份 → 破坏 skill → `rollback` 恢复（`test_agent_self_evolution_manual_acceptance.py`）
- [x] `tests/unit/test_cli_agent_curator.py` 通过

### Task 3 — Epic 与文档

- [x] `docs/issues/epic-manifests/agent-self-evolution.yaml` 指向 #215–#217 与 spec S1–S15
- [x] 起草 `docs/superpowers/verification/2026-06-07-m2t-agent-self-evolution-acceptance.md`（S1–S15 全部 PASS）
- [x] 更新 `CLAUDE.md` Desktop Agent（自进化 + curator CLI）
- [x] 更新 `config.example.yaml` `curator.*` 段
- [ ] Hermes 父规格 §4.2 Curator 非目标一行 → 指向本规格（spec §18）（follow-up）
- [x] `python scripts/epic_verify.py agent-self-evolution` 通过（manifest 落地后）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_curator_transitions.py tests/unit/test_cli_agent_curator.py tests/unit/test_agent_self_evolution_manual_acceptance.py -v -m agent
python scripts/agent_self_evolution_manual_acceptance.py
media2text agent curator status
media2text agent curator run --dry-run
python scripts/epic_verify.py agent-self-evolution
ruff check src/media2text/agent/ src/media2text/cli/
```

## 非目标范围

- Gateway cron / `/curator` slash
- 默认开启 `curator.enabled: true`（需人类在 config 显式打开）
- Honcho / 外部 memory
- Desktop review toast
- 修改 Agent Pane UI（设置页展示 review 摘要为 follow-up）

## 实现备注

- 分支：`issue-217-agent-m7c-curator`
- GitHub Issue: [#217](https://github.com/oychao1988/media2text/issues/217)
- PR: [#220](https://github.com/oychao1988/media2text/pull/220) merged 2026-06-07
