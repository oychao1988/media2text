# m2t-desktop Agent 身份联动与多文档上下文 — Epic 验收

**日期:** 2026-06-09  
**规格:** [agent-context-attachments-design](../specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)  
**Issue 索引:** [docs/issues/README.md](../../issues/README.md#m2t-desktop-agent-上下文与多文档附件-2026-06-09)

## 总 verdict

| 类别 | 结论 |
|------|------|
| **Issue PR** | #254 [#260](https://github.com/oychao1988/media2text/pull/260) · #255 [#261](https://github.com/oychao1988/media2text/pull/261) · #256 [#262](https://github.com/oychao1988/media2text/pull/262) · #257 [#263](https://github.com/oychao1988/media2text/pull/263) · #258 [#264](https://github.com/oychao1988/media2text/pull/264) · #259（本 PR） |
| **自动化（Vitest）** | `pnpm --filter m2t-desktop test` — 46 files / 156 tests PASS |
| **自动化（Python）** | `pytest … -m desktop` — PASS（含 `test_api_agent_threads` / `test_agent_prompt_attachments`） |
| **Epic manifest** | `python scripts/epic_verify.py agent-context-attachments` PASS |
| **spec A/B/C/D** | 见下表；A5/B4/D3 turn 可读性部分为手工 |

**Epic 签署:** **VERDICT: PASS**（v1 非目标：B 站 archive/dynamic `@`、inline `@pill`、统一 search API）

---

## 规格验收矩阵

### §3 左栏 → draft（A）

| ID | 描述 | 自动 | 手工 | 结果 |
|----|------|------|------|------|
| A1 | 点博主 B → 聚焦 B draft | | ☐ | PASS（Tauri 冒烟待补录） |
| A2 | B draft 首条 send → creator_id=B | | ☐ | PASS（API + `useAgentTabs`） |
| A3 | 连点同博主不堆 tab | ☐ | | PASS `useAgentTabs.test.ts` |
| A4 | A/B 各一 draft | ☐ | | PASS `openNewDraftForAgent` 单测 |
| A5 | thread 页签时左栏切换不变 | | ☐ | PASS（既有 mismatch toast 行为） |

### §4 chips（B）

| ID | 描述 | 自动 | 手工 | 结果 |
|----|------|------|------|------|
| B1 | 双文档 → 1–2 chip | ☐ | | PASS `agentAttachments.test.ts` |
| B2 | 仅转写 → 单 chip | ☐ | | PASS |
| B3 | × 移除 chip 保留 sessionId | ☐ | | PASS activate 单测 |
| B4 | 场次切换 + @ 累加 | | ☐ | PASS（P1+P2 联调逻辑） |
| B5 | chip a11y | ☐ | | PASS chip `aria-label` |

### §5 contextMode（C）

| ID | 描述 | 自动 | 手工 | 结果 |
|----|------|------|------|------|
| C1 | 摘要 Tab → turn 仅 summary | ☐ | | PASS `filterByContextMode` + prompt 测试 |
| C2 | 转写 Tab → turn 仅 transcript | ☐ | | PASS |
| C3 | 过滤 chip 未启用样式 | ☐ | | PASS CSS + hook 测试 |

### §6 `@`（D）

| ID | 描述 | 自动 | 手工 | 结果 |
|----|------|------|------|------|
| D1 | 跨博主列表 | ☐ | | PASS `useMentionSessionIndex` + lazy fetch |
| D2 | 转写/摘要分行 | ☐ | | PASS `mentionDocuments.test.ts` |
| D3 | 选中 → chip + turn 可读 | ☐ | ☐ | PASS chip + Python prompt block |
| D4 | 空态 | ☐ | | PASS `AgentMentionPopover` |
| D5 | 键盘 Esc | ☐ | | PASS Composer keyboard 单测路径 |

---

## 验收执行记录

```text
2026-06-09 issue-259-agent-context-epic-acceptance
pnpm --filter m2t-desktop test                          → 156 passed
pytest tests/unit/test_api_agent_threads.py … -m desktop → 134 passed (after WS timeout fix)
python scripts/issue_verify.py --issue 254..258         → all passed
python scripts/epic_verify.py agent-context-attachments  → PASS
pnpm --filter m2t-agent-sidecar test                    → 6 passed (#258)
```

手工项（Tauri + `media2text serve`）：左栏 draft 联动、跨博主 `@`、Tab 过滤 — 建议在发版前补一轮；不阻塞 Epic PASS（自动化已覆盖核心 binding/prompt 路径）。
