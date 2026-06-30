# Monitor DB Lock Write Path Epic 验收（DL-1–DL-3）

**日期:** 2026-06-30  
**事故:** 博主在播 Desktop 离线；`database is locked`；快照 stale  
**Issues:** [#356](https://github.com/oychao1988/media2text/issues/356) · [#357](https://github.com/oychao1988/media2text/issues/357) · [#358](https://github.com/oychao1988/media2text/issues/358)

## 自动化

| 检查 | 结果 | 备注 |
|------|------|------|
| DL-1 单元测 | | `test_live_db_lock_probe_snapshot` / probe parallel |
| DL-2 单元测 | | summarize db release |
| DL-3 单元测 | | self_heal / drain |
| Epic verify | | `python scripts/epic_verify.py monitor-db-lock-write-path-2026-06-30` |

## 功能验收

| ID | 场景 | 预期 | 状态 |
|----|------|------|------|
| DL1-1 | 并行 probe 11 博主 | snapshot 均更新，无 sustained `database is locked` | |
| DL1-2 | 探活期间 | 无长占 DB 连接（单测 mock） | |
| DL2-1 | summarize LLM | worker conn 在 LLM 前关闭 | |
| DL3-1 | external + Desktop | `managed_by=external`，self_heal 不 takeover | |
| DL3-2 | external 模式 | serve drain 降频 | |

## 裁决

**Epic:** （待全部 Issue 合并后填写 PASS/FAIL）
