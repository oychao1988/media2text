# Monitor Hardening Epic 验收（MH-1–MH-5）

**日期:** 2026-06-26  
**来源:** `/plan-eng-review` 监控逻辑审查  
**Epic manifest:** `python scripts/epic_verify.py monitor-hardening-2026-06-26`

## 自动化

| 检查 | 结果 | 备注 |
|------|------|------|
| MH-1 | PASS | SlowTick due_at + intervals + live_lane SQL（#350） |
| MH-2 | PASS | per-creator content pause（#351） |
| MH-3 | PASS | prepare Playwright + hybrid conn（#352） |
| MH-4 | PASS | guards + run_once + integration + G1（#353） |
| MH-5 | PASS | open_db migration 单次化（#354） |
| Epic verify | PASS | `python scripts/epic_verify.py monitor-hardening-2026-06-26` |
| Monitor regression | PASS | 73 项 monitor 单测（2026-06-26 本地） |

## 功能验收

| ID | 场景 | 预期 | 状态 |
|----|------|------|------|
| MH1-1 | 多博主 vod/archive/dynamic 不同 due | SlowTick sleep ≈ min(due)，非 1s 狂扫 | PASS（`test_slow_tick_waits_until_next_due`） |
| MH2-1 | A 长直播 | B 仍 sync_catalog / download 执行 | PASS（`test_content_drain_claims_other_creator_while_recording`、集成测） |
| MH3-1 | sync_catalog 占 Playwright | prepare 不因 executor 层 acquire 失败 | PASS（`test_prepare_not_blocked_by_executor_playwright_lock`） |
| MH4-1 | reconciler_enabled=false | daemon 拒绝启动 | PASS（`test_monitor_daemon_integration`、CLI） |
| MH4-2 | G1 benchmark | P95 ≤ 30s（mock 注明环境） | PASS（mock: `test_g1_recording_latency`, p95=5s） |
| MH5-1 | 热路径 open_db | 同 db 路径 migration 只跑一次 | PASS（`test_open_db_migration_once`） |
| MP-smoke | MP Epic 手动 4 项 | 见 2026-06-25 acceptance §手动 | 待本机（`TODOS.md`） |

## 环境自检

| 检查 | 结果 |
|------|------|
| `media2text doctor --json` | PASS（ffmpeg / playwright / session / monitor lock） |
| `media2text monitor watch --json` | PASS（单轮 run_once；2026-06-26 修复 reconcile 签名） |

## 裁决

**Epic: PASS**（自动化全绿；MP-smoke 手动项待本机确认，非 MH 阻塞项）
