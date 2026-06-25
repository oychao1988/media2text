# Monitor Hardening Epic 验收（MH-1–MH-5）

**日期:** 2026-06-26  
**来源:** `/plan-eng-review` 监控逻辑审查  
**Epic manifest:** `python scripts/epic_verify.py monitor-hardening-2026-06-26`

## 自动化

| 检查 | 结果 | 备注 |
|------|------|------|
| MH-1 | — | SlowTick due_at + intervals + live_lane SQL |
| MH-2 | — | per-creator content pause |
| MH-3 | — | prepare Playwright + hybrid conn |
| MH-4 | — | guards + run_once + integration + G1 |
| MH-5 | — | open_db migration 单次化 |
| Epic verify | — | `python scripts/epic_verify.py monitor-hardening-2026-06-26` |

## 功能验收

| ID | 场景 | 预期 | 状态 |
|----|------|------|------|
| MH1-1 | 多博主 vod/archive/dynamic 不同 due | SlowTick sleep ≈ min(due)，非 1s 狂扫 | — |
| MH2-1 | A 长直播 | B 仍收到 new_aweme / sync_catalog 执行 | — |
| MH3-1 | sync_catalog 占 Playwright | prepare 不因 executor 层 acquire 失败 | — |
| MH4-1 | reconciler_enabled=false | daemon 拒绝启动 | PASS（`test_monitor_daemon_integration`, CLI） |
| MH4-2 | G1 benchmark | P95 ≤ 30s（mock 注明环境） | PASS（mock: `test_g1_recording_latency`, p95=5s） |
| MP-smoke | MP Epic 手动 4 项 | 见 2026-06-25 acceptance §手动 | — |

## 裁决

**Epic:** —（待 MH-1–MH-5 交付）
