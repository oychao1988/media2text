---
issue: 302
epic: session-media-unified
github: 302
branch: issue-302-smu-r6-epic-acceptance
depends_on: [296, 297, 298, 299, 300, 301]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R6：Session Media Unified Epic 验收

## 背景

#296–#301 合并后，对照 spec **US1–US10** 填 Epic 验收表，并确保 `python scripts/epic_verify.py session-media-unified` 全绿。

**参考**

- [design spec §6 Success Criteria](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [implementation plan](../superpowers/plans/2026-06-11-session-media-unified.md)
- Dogfood：`data/creators/.../live/20260611T110019Z/`（断流 + 云-only 可播）

## 验收标准

### 文档

- [x] 新增 `docs/superpowers/verification/2026-06-11-session-media-unified-acceptance.md`：逐项勾选 US1–US10
- [x] **US1**：引用 #298 example + doctor 警告截图/JSON 片段
- [x] **US2/US7**：标注「继承 LSM S1/S5」+ 指向 #271/#272 或现有 segment 单测 PASS 记录
- [x] **US4/US9/US10**：含 #296 dogfood `20260611T110019Z` 手工步骤或 PR 记录
- [x] **US8**：`test_streaming_stt_finalize*` 在 epic_verify 中 PASS
- [x] **US3**：引用 #297 / #305 验收表 `s6_pass` 行（Apple Silicon 须 #305 完成或标 skipped+原因）

### 自动化

- [x] `docs/issues/epic-manifests/session-media-unified.yaml` 存在且 steps 全 PASS
- [x] `python scripts/epic_verify.py session-media-unified` exit 0
- [x] 各 issue `python scripts/issue_verify.py --issue N`（#296–#301）exit 0

### README

- [x] `docs/issues/README.md` SMU 段 PR/Issue 链接补全

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
python scripts/epic_verify.py session-media-unified
python scripts/issue_verify.py --issue 296
python scripts/issue_verify.py --issue 297
python scripts/issue_verify.py --issue 298
python scripts/issue_verify.py --issue 299
python scripts/issue_verify.py --issue 300
python scripts/issue_verify.py --issue 301
test -f docs/superpowers/verification/2026-06-11-session-media-unified-acceptance.md
```

## 非目标范围

- 新功能开发
- VOD 上传（R3b）
- 修改 spec/plan 正文（仅验收表）

## 依赖与顺序

- **依赖**：#296–#301 全部 merged
- **建议分支**：`issue-302-smu-r6-epic-acceptance`

## GitHub

- Issue: [#302](https://github.com/oychao1988/media2text/issues/302)
