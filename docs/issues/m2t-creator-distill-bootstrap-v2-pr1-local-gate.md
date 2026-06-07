---
issue: 222
epic: creator-distill-bootstrap-v2
github: 222
branch: issue-222-distill-bootstrap-v2-pr1-local-gate
depends_on: [186]
spec: docs/superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md
spec_ids: [CD3, CD5]
plan: docs/superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md
---

# m2t Creator Distill Bootstrap v2 PR1：LocalScan + Merge Gate

## 背景

M5b（#186）Bootstrap 仅 manifest 索引 ≤20 条、无 Web、语料不足即 deferred。v2 规格要求 **本地 glob 扫描 + manifest 双轨**（CD3），以及 **Web 有效时本地 0 字仍可 distill** 的 Merge Gate 纯函数（CD5）。本 PR 只落地 **本地采集与 gate 逻辑**，不接入 Tavily、不改 `bootstrap.py` 主编排（留 #225）。

**参考**：[Bootstrap v2 规格 §5.3、§5.5、§8](../superpowers/specs/2026-06-07-m2t-creator-distill-bootstrap-v2-design.md) · [计划 Phase v2.1a Tasks 1–4](../superpowers/plans/2026-06-08-m2t-creator-distill-bootstrap-v2.md)

**依赖**：#186（M5b 已交付）。**阻塞**：#223、#224、#225。

## 验收标准

### Task 1 — DistillConfig v2 字段

- [x] `LocalScanConfig`（`enabled`, `include_manifest`, `max_files`, `globs`, `user_sources_dir`）嵌套于 `DistillConfig`
- [x] 新增 `bootstrap_web_research`（默认 `true`）、`web_*` / `tavily_*` 占位字段（PR2/PR4 使用）；`allow_web_research` 读取时映射到 `bootstrap_web_research`
- [x] `config.example.yaml` 同步 `desktop.agent.distill` 段
- [x] `tests/unit/test_creator_distill_config_v2.py` 通过

### Task 2 — BootstrapGateResult（CD5）

- [x] `creator_distill/gate.py`：`evaluate_bootstrap_gate()` + `BootstrapGateResult` dataclass
- [x] Web `web_channels_ok ≥ 1` → `proceed=True`（即使 `local_chars=0`）
- [x] Web 关 + local ≥ min → `proceed=True`；Web 开且全路无效 + local < min → `proceed=False`
- [x] `tests/unit/test_creator_distill_gate.py` 通过

### Task 3 — collect_local glob 扫描

- [x] `creator_distill/collect_local.py`：`scan_local_files()` 支持 spec 默认 globs；仅 `.md`/`.txt`；`max_files` + char budget
- [x] `tests/unit/test_creator_distill_collect_local.py` 通过

### Task 4 — collect_corpus facade

- [x] `collect.py`：`collect_corpus()` 在 manifest 循环后合并 local scan；路径去重
- [x] 无 manifest 条目时 glob 命中 transcript/summary 仍计入 `total_chars`
- [x] 现有 `test_creator_distill_bootstrap.py` 仍 PASS（行为兼容：Web 未启用时 deferred 语义不变）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_creator_distill_config_v2.py tests/unit/test_creator_distill_gate.py tests/unit/test_creator_distill_collect_local.py tests/unit/test_creator_distill_bootstrap.py -v -m agent
ruff check src/media2text/agent/creator_distill/collect.py src/media2text/agent/creator_distill/collect_local.py src/media2text/agent/creator_distill/gate.py src/media2text/core/config.py
```

## 非目标范围

- Tavily / 六路 Web（#223）
- Desktop Tavily UI / doctor（#224）
- `bootstrap.py` 编排、写 `01–06.md`、`merge_corpus_for_distill`（#225）
- Evolve 变更（M5c #187）
- `bing_cn` fallback（v2.3）

## 实现备注

- 分支：`issue-222-distill-bootstrap-v2-pr1-local-gate`
- GitHub Issue: [#222](https://github.com/oychao1988/media2text/issues/222)
