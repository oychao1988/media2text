# m2t-desktop Agent Hermes 重构 — Epic 验收

**日期:** 2026-06-06（骨架；M2 merge 后开始填）  
**Spec:** [hermes-refactor-design](../specs/2026-06-06-m2t-desktop-agent-hermes-refactor-design.md)  
**Plan:** [hermes-refactor](../plans/2026-06-06-m2t-desktop-agent-hermes-refactor.md)  
**Epic manifest:** `docs/issues/epic-manifests/agent-hermes.yaml`

## 总 verdict

| 类别 | 结论 |
|------|------|
| Issue PR #180–#188 | 待合并 |
| `python scripts/epic_verify.py agent-hermes` | 待跑 |
| Spec H1–H22 | 见下表 |

**Epic 签署:** _pending_

---

## Spec 成功项

| ID | 描述 | 阶段 | 结论 | 证据 |
|----|------|------|------|------|
| H1 | thread 切换 replay ≤2s | M1 | | |
| H2 | 重启后续聊一致 | M1/M2 | PASS | `test_h2_messages_survive_api_restart` + live WS ready smoke |
| H3 | creator mismatch 409 block | M0/M5a | | |
| H4 | compression lineage | M3 | | |
| H5 | MEMORY 新 thread 可见 | M3 | | |
| H6 | session_search ≤200ms | M3 | | |
| H7 | 首 token ≤10s | M1 | 手工/N/A | |
| H8 | 无 Node 时 tauri dev 全功能 | M2 | PASS | `lib.rs` 无 agent_sidecar；live `serve` + WS `sidecar.ready`；结构验证 2026-06-06 |
| H9 | Agent Pane Vitest 迁移 | M2 | PASS | Vitest **87** passed（含 `useM2tAgent.test.ts` 6 项 mock WS）；`agentContext` + pane 验收集 |
| H10 | CLI/daemon 不变 | M0+ | | |
| H11–H13 | 博主 profile 隔离 | M5a | | |
| H14–H16 | terminal/delegate/approval | M6 | | |
| H17–H18 | USER 二选一 / 全局 thread | M5a | | |
| H19–H22 | 蒸馏/进化 | M5b/M5c | 部分手工 | |

---

## 自动化执行记录

```bash
python scripts/agent_m2_verify.py          # M2 全量：issue_verify + smoke + live WS
python scripts/issue_verify.py --issue 182
pytest tests/unit/test_api_agent_m2_smoke.py -v -m desktop
pnpm --filter m2t-desktop test
```

**2026-06-06 验证：** `python scripts/agent_m2_verify.py` 全 PASS。  
**未自动化：** `pnpm tauri dev` GUI 发消息 / tool 卡片视觉确认（H8 运行时等价已由 API+WS smoke 覆盖）。
