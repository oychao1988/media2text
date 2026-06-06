# m2t-desktop Agent Hermes 重构 — Epic 验收

**日期:** 2026-06-06（骨架；M2 merge 后开始填）  
**Spec:** [hermes-refactor-design](../specs/2026-06-06-m2t-desktop-agent-hermes-refactor-design.md)  
**Plan:** [hermes-refactor](../plans/2026-06-06-m2t-desktop-agent-hermes-refactor.md)  
**Epic manifest:** `docs/issues/epic-manifests/agent-hermes.yaml`

## 总 verdict

| 类别 | 结论 |
|------|------|
| Issue PR #180–#188 | **已合并**（末单 [#198](https://github.com/oychao1988/media2text/pull/198) → #188） |
| `python scripts/epic_verify.py agent-hermes` | **PASS**（2026-06-06） |
| Spec H1–H22 | 见下表 |

**Epic 签署:** 自动化项 PASS；H7 / H19–H22 部分手工见备注

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
| H9 | Agent Pane Vitest 迁移 | M2 | PASS | Vitest **95** passed（含 `useM2tAgent` / `piEvent.approval.request`） |
| H10 | CLI/daemon 不变 | M0+ | PASS | epic desktop-api-pytest 124 passed |
| H11–H13 | 博主 profile 隔离 | M5a | PASS | `test_agent_profile_resolver.py` + creator mismatch API |
| H14–H16 | terminal/delegate/approval | M6 | PASS | `test_agent_terminal.py` + `test_agent_delegate.py`；WS confirm + `POST /api/agent/approvals/{id}` |
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

**2026-06-06 验证：** `python scripts/epic_verify.py agent-hermes` 全 PASS（doctor / ruff / pyright / desktop pytest 124 / agent pytest 52 / vitest 95）。  
**未自动化：** `pnpm tauri dev` GUI 发消息 / terminal approval 真实 confirm（H7 首 token、H14 手工路径）。
