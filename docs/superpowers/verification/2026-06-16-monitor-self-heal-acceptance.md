# Monitor 自愈 Epic 验收（SH-1–SH-3）

**日期:** 2026-06-16  
**规格:** [2026-06-16-monitor-self-heal-design.md](../specs/2026-06-16-monitor-self-heal-design.md)  
**Issues:** [#313](https://github.com/oychao1988/media2text/issues/313) · [#314](https://github.com/oychao1988/media2text/issues/314) · [#315](https://github.com/oychao1988/media2text/issues/315)

## 自动化

| 检查 | 结果 | 备注 |
|------|------|------|
| SH-1 单元测 | PASS | `test_heartbeat` / `test_monitor_lock` / `test_process_lock` / `test_runtime_status` / supervisor / external_spawn / api_sessions / doctor |
| SH-2 单元测 | PASS | `test_session_recovery` / `test_monitor_self_heal` / `test_api_runtime` / `test_work_queue` |
| ruff（核心模块） | PASS | `heartbeat` / `monitor_lock` / `process_lock` / `session_recovery` / `monitor_self_heal` |

```bash
source .venv/bin/activate
pytest tests/unit/test_heartbeat.py tests/unit/test_monitor_lock.py \
  tests/unit/test_process_lock.py tests/unit/test_runtime_status.py \
  tests/unit/test_monitor_supervisor.py tests/unit/test_external_spawn.py \
  tests/unit/test_api_sessions.py tests/unit/test_doctor_legacy_pipeline.py \
  tests/unit/test_session_recovery.py tests/unit/test_monitor_self_heal.py \
  tests/unit/test_api_runtime.py tests/unit/test_work_queue.py -v
```

## 功能验收

| ID | 场景 | 预期 | 状态 |
|----|------|------|------|
| SH1 | 假锁 PID 非 `monitor watch` | `running=false`, `lock_valid=false`, `reason=lock_pid_mismatch` | PASS（单测） |
| SH2 | `serve` + 假锁 + `auto_start_monitor` | lifespan 清锁并 embedded 启动 | PASS（`test_api_runtime`） |
| SH3 | `heartbeat_stale` + embedded | `health=degraded`, `running=false` | PASS（单测） |
| SH4 | daemon 重启 | `recover_orphan_sessions` → offline 场次 enqueue finalize | PASS（单测） |
| SH5 | 新 daemon 写锁 | JSON v2 `.monitor-watch.lock` | PASS（`test_process_lock`） |
| SH6 | 自愈限流 | cooldown 120s + 每小时最多 3 次 | PASS（`test_monitor_self_heal`） |
| SH3-ops | `bin/monitor-watch-daemon.sh` | 启动前 Python `clear_invalid_monitor_lock` | PASS（脚本已改） |

## 手动（可选）

- [ ] `echo 581 > data/.monitor-watch.lock` → `media2text serve` → `GET /api/runtime` 显示 embedded running
- [ ] 同上假锁 → `bin/monitor-watch-daemon.sh` 清锁或启动合法 daemon

## 裁决

**Epic: PASS**（自动化全绿；手动项待本机 smoke）
