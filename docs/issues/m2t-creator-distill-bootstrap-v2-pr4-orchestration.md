---
issue: 225
epic: creator-distill-bootstrap-v2
github: 225
branch: issue-225-distill-bootstrap-v2-pr4-orchestration
depends_on: [222, 223, 224]
spec: docs/superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md
spec_ids: [CD1, CD4, CD5, CD6]
plan: docs/superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md
---

# m2t Creator Distill Bootstrap v2 PR4：编排 + Merge Corpus + API

## 背景

PR1–PR3 交付 local scan、gate、Tavily 六路、Desktop 密钥。本 PR **接线** `run_bootstrap_job`：Web ∥ Local → Merge Gate → `merge_corpus_for_distill` → distill；修订 deferred/promote；扩展 `distill-status` payload。完成后零本地语料新博主可产出含 **01–06** 的 perspective skill。

**参考**：[规格 §5.1、§5.4、§5.5、§9](../superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md) · [计划 Phase v2.1c Tasks 10–13](../superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md)

**依赖**：#222、#223、#224。**阻塞**：Epic 验收（规格 §15）。

## 验收标准

### Task 1 — merge_corpus_for_distill

- [x] `creator_distill/merge_corpus.py`：char budget（meta 2k / local 60k / web 50k，cap `max_input_chars`）；`truncated` 标记
- [x] `distill_llm.py`：sources 允许 local path + `references/research/0X-*.md` + 公开 URL；硬截用 `max_input_chars` 非固定 100k
- [x] `tests/unit/test_creator_distill_merge_corpus.py` 通过

### Task 2 — bootstrap.py 编排

- [x] Web 启用且无 Tavily key → job **`failed`**，`error=tavily_api_key_missing`（非 deferred）
- [x] Web ∥ Local 完成后 `evaluate_bootstrap_gate`；`proceed=False` → deferred payload 含 `web_channels_ok`, `local_chars`
- [x] 成功路径：写 `01–06.md` + `00-local-corpus.md` + SKILL/SOUL + pin
- [x] `mark_done` payload 含 gate 白名单字段
- [x] `test_bootstrap_proceeds_when_web_ok_local_empty`、`test_bootstrap_failed_missing_tavily_key` 通过

### Task 3 — deferred promote

- [x] `maybe_promote_bootstrap`：读 payload/`distill_state` 的 `web_channels_ok`；历史 web 已成功不应永久 deferred

### Task 4 — API distill-status

- [x] `_job_dict()` 解析 payload 白名单：`webChannelsOk`, `localChars`, `truncated` 等
- [x] `tests/unit/test_api_agent_distill_status.py` 通过

### Task 5 — 回归

- [x] 规格 §11 P0 用例在 `test_creator_distill_bootstrap.py` / 新文件中覆盖
- [x] Evolve 仍不修改 `01-writings.md` mtime（回归 `test_evolve_does_not_touch_research` 或等价）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_creator_distill*.py tests/unit/test_api_agent_distill_status.py -v -m "agent or desktop"
ruff check src/media2text/agent/creator_distill/ src/media2text/api/routes/agent_profiles.py
```

## 非目标范围

- v2.2 本地 L2 写入 01–06、PDF sources
- v2.3 `bing_cn` fallback
- Evolve / background_review 行为变更
- Hermes §24.4 全文改写（可另开 doc PR 交叉引用）
- `on_creator_add` 默认 enqueue bootstrap（仍 O9 false）

## 实现备注

- 分支：`issue-225-distill-bootstrap-v2-pr4-orchestration`
- GitHub Issue: [#225](https://github.com/oychao1988/media2text/issues/225)
- 系列合并顺序：**#222 → #223 ∥ #224 → #225**
