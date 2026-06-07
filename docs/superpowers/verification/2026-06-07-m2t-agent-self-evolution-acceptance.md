# m2t Agent 自进化 — Epic 验收

**规格:** [2026-06-07-m2t-agent-self-evolution-design.md](../specs/2026-06-07-m2t-agent-self-evolution-design.md)  
**Issues:** #215 M7a · #216 M7b · #217 M7c

## 自动化 (S1–S14)

| ID | 项 | 状态 |
|----|-----|------|
| S1 | `memory.nudge_interval` + agent_state 持久化 | PASS |
| S2 | MemoryStore `§` 条目 add/replace/remove | PASS |
| S3 | background review fork + 白名单 | PASS |
| S4 | 压缩前 deepcopy 快照 | PASS |
| S5 | review_in_flight 并发守卫 | PASS |
| S6 | API e2e review 写 memory | PASS |
| S7 | skill_manage create/patch | PASS |
| S8 | foreground create 不标 agent_created | PASS |
| S9 | distill/pinned/bundled 保护 | PASS |
| S11 | memory write/append deprecated | PASS |
| S12 | curator dry-run 不修改磁盘 | PASS |
| S13 | 30d stale / 90d archive | PASS |
| S14 | 仅 agent_created skills 参与 curator | PASS |

## 人工 (S10, S15)

| ID | 项 | 状态 |
|----|-----|------|
| S10 | review patch distill perspective pitfall 段 | 待人工 |
| S15 | curator rollback 恢复备份 | 待人工 |

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_memory_store_entries.py \
       tests/unit/test_agent_state_persistence.py \
       tests/unit/test_agent_nudge_counters.py \
       tests/unit/test_background_review.py \
       tests/unit/test_review_snapshot_order.py \
       tests/unit/test_skill_manage.py \
       tests/unit/test_skill_provenance.py \
       tests/unit/test_curator_transitions.py \
       tests/unit/test_cli_agent_curator.py -v -m agent
media2text agent curator run --dry-run
python scripts/epic_verify.py agent-self-evolution
```
