# Monitor DB Lock Write Path Epic 验收（DL-1–DL-3）

**日期:** 2026-06-30  
**事故:** 博主在播 Desktop 离线；`database is locked`；快照 stale  
**Issues:** [#356](https://github.com/oychao1988/media2text/issues/356) · [#357](https://github.com/oychao1988/media2text/issues/357) · [#358](https://github.com/oychao1988/media2text/issues/358)

## 自动化

| 检查 | 结果 | 备注 |
|------|------|------|
| DL-1 单元测 | PASS | 9 tests (`test_live_db_lock_probe_snapshot` / probe parallel) |
| DL-2 单元测 | PASS | `test_post_process_summarize_db` + post_process 相关 |
| DL-3 单元测 | PASS | self_heal / drain / db retry (27+) |
| Epic verify | PASS | `python scripts/epic_verify.py monitor-db-lock-write-path-2026-06-30` exit 0 |

## 功能验收

| ID | 场景 | 预期 | 状态 |
|----|------|------|------|
| DL1-1 | 并行 probe 11 博主 | snapshot 均更新，无 sustained `database is locked` | PASS（单测 mock 并行 persist） |
| DL1-2 | 探活期间 | 无长占 DB 连接（单测 mock） | PASS |
| DL2-1 | summarize LLM | worker conn 在 LLM 前关闭 | PASS |
| DL3-1 | external + Desktop | `managed_by=external`，self_heal 不 takeover | PASS（单测 `external_heartbeat_stale`） |
| DL3-2 | external 模式 | serve drain 降频 | PASS（`resolve_drain_interval_sec` 单测） |

**说明：** 终端 `monitor watch --daemon` 与 Desktop UI 同时运行时，`GET /api/runtime` 显示 `managed_by=external` 为预期；serve 仅作 UI/outbox drain，不抢 monitor 锁。

## 裁决

**Epic:** PASS（2026-06-30；PR #359 / #362 / #361 已合并 main）

**剩余 gap（非阻塞）：** DL1-1 真实 11 博主并行 probe 需 `pytest -m live` 手工/夜间跑；MH-3 长连接 hybrid 未在本 Epic 范围。
