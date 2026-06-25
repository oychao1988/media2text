# Monitor DB Contention Epic 验收（MP-1–MP-3）

**日期:** 2026-06-25  
**事故:** 博主已开播但 `active_recordings` 为空；日志 `database is locked` / `prepare_live_recording` 失败  
**Issues:** [#334](https://github.com/oychao1988/media2text/issues/334) · [#335](https://github.com/oychao1988/media2text/issues/335) · [#336](https://github.com/oychao1988/media2text/issues/336)

## 自动化

| 检查 | 结果 | 备注 |
|------|------|------|
| MP-1 单元测 | PASS | `test_post_process_repo` / `test_streaming_finalize` |
| MP-2 单元测 | PASS | `test_monitor_lock` / `test_monitor_supervisor` / `test_api_runtime` / `test_runtime_status` |
| MP-3 单元测 | PASS | `test_task_scheduler` / `test_live_lane_priority` |
| Epic verify | PASS | `python scripts/epic_verify.py monitor-db-contention-2026-06-25` |
| CI（#337–#339） | PASS | python / issue-verify / desktop-frontend |

```bash
source .venv/bin/activate
python scripts/epic_verify.py monitor-db-contention-2026-06-25
```

## 功能验收

| ID | 场景 | 预期 | 状态 |
|----|------|------|------|
| MP1-1 | 同 session 重复 finalize enqueue | 仅一条 active post_process job | PASS（单测 dedupe + partial unique index） |
| MP1-2 | stale job + session 已 completed | job → `failed`（`superseded:session_terminal`），不复活 pending | PASS（单测） |
| MP1-3 | 默认 stale 阈值 | `post_process_stale_running_sec=600` | PASS（config default） |
| MP2-1 | serve + 有效 external lock | `supervisor.takeover()`，非 defer | PASS（`test_api_runtime`） |
| MP2-2 | `POST /api/runtime/restart` | 始终 embedded restart，不 spawn CLI daemon | PASS（单测） |
| MP2-3 | embedded lock + heartbeat | 不被 `clear_invalid_monitor_lock` 误删；`running=true` | PASS（单测） |
| MP3-1 | 在播无 session / pending prepare | `live_lane_needs_priority=true` | PASS（`test_live_lane_priority`） |
| MP3-2 | live lane 优先 | 跳过 `post_process` drain，log 含 count | PASS（`test_task_scheduler_defers_post_process_when_live_pending`） |

## 手动（建议本机 smoke）

- [ ] Desktop `serve` 启动后 `GET /api/runtime` 仅 embedded monitor，`managed_by=embedded`
- [ ] 模拟 external `monitor watch --daemon` 与 serve 并存 → serve takeover 后仅单进程写 DB
- [ ] 博主开播且 post_process 积压时，日志出现 `post_process_deferred_for_live_lane`，随后 `prepare_live_recording` 成功

## 非本 Epic 范围（follow-up）

| 项 | 说明 |
|----|------|
| `open_db()` migration 单次化 | 每次 connect 全量 migration 仍放大锁竞争 |
| Playwright 槽位 / probe 并发 | 次要放大因素 |
| 手工 sqlite3 清队列 | 运维脚本未纳入 |

## 裁决

**Epic: PASS**（自动化全绿；手动 smoke 待本机确认）
