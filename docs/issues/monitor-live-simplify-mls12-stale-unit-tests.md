---
epic: monitor-live-simplify-2026-07-06
depends_on: []
follow_up_from: monitor-live-simplify-acceptance
github: 410
branch: issue-410-mls12-stale-unit-tests
---

# MLS-12：Epic 后陈旧 unit test 修复（S4 Gap）

GitHub Issue: [#410](https://github.com/oychao1988/media2text/issues/410)

规格：[2026-07-06-monitor-live-simplify-acceptance.md](../superpowers/verification/2026-07-06-monitor-live-simplify-acceptance.md) §S4 Gap

## 背景

MLS-1 … MLS-11 交付后，`pytest tests/unit -m "not live"` 约 **938 passed / 26–31 failed**。失败用例多为 **MLS 前即存在的 mock/夹具**，未随以下行为变更更新：

| 变更 | 影响测试 |
|------|----------|
| MLS-2 legacy session guard | 新 session 需 `pipeline_mode=streaming`；仍用 legacy 开录的测试抛 `RecordingError` |
| MLS-5 删 `platform/*/live.run_once` | `test_bilibili_*_run_once_*`、`test_monitor_run_once_*` |
| MLS-11 distill 解耦 | `SlowTickLoop` 无 distill drain；`test_slow_tick_waits_until_next_due` 等 |
| 通知路径重构 | `MonitorWatcher._emit_pipeline_notifications` 已删；`test_notify.py` |
| finalize/HLS/streaming 语义 | ffmpeg 空夹具、HLS sidecar、benchmark 阈值 |

MLS issue 闸门与 `epic_verify` 已通过；本单不阻塞 Epic #409，但 **S4 全绿** 与 **MLS-10 issue_verify** 依赖本单。

## 验收标准

- [ ] `pytest tests/unit -v -m "not live" --tb=short -q` 全绿（0 failed）
- [ ] `python scripts/issue_verify.py --issue 396` 通过（MLS-10 全量 unit 验证）
- [ ] 删除或改写引用已移除 API 的测试（`run_once`、`_emit_pipeline_notifications`）；不恢复死代码
- [ ] legacy 相关测试仅覆盖 **只读 finalize 旧 session**（与 MLS-2 一致），新 session 用例默认 `streaming`

## 失败用例清单（2026-07-06 基线）

```text
test_agent_thread_title.py::test_suggest_thread_title_falls_back_without_llm
test_bilibili_dynamic.py::test_monitor_run_once_includes_dynamic_tick
test_bilibili_live.py::test_bilibili_live_run_once_starts_recording
test_live_observe_state.py::test_observe_live_state_does_not_start_recording
test_live_scheduler.py::test_live_tick_runs_while_slow_tick_blocks
test_live_scheduler.py::test_slow_tick_waits_until_next_due
test_live_sessions_migration.py::test_live_sessions_v4_pipeline_mode_backfill
test_live_snapshot_upsert.py::test_observe_live_state_upserts_snapshot
test_live_watcher.py::test_finalize_refresh_manifest
test_live_watcher.py::test_finalize_transcribe_on_complete
test_live_watcher.py::test_finalize_transcribe_skipped_without_extra
test_live_worker_tasks.py::test_prepare_live_recording_task
test_live_worker_tasks.py::test_prepare_not_blocked_by_executor_playwright_lock
test_manifest.py::test_refresh_manifest_live_transcript_path
test_notify.py::test_monitor_vod_notifications
test_notify.py::test_monitor_archive_notifications
test_offline_recording_signals.py::test_profile_offline_still_finalizes_when_no_signals
test_offline_recording_signals.py::test_profile_offline_after_flv_stall_ignores_reflow
test_pipeline_phase.py::test_pipeline_phase_derivation[session4-...]
test_poll_active_obs.py::test_poll_active_recordings_delegates_when_reconciler_enabled
test_probe_live_parallel.py::test_probe_live_parallel_uses_per_thread_connections
test_runtime_status.py::test_build_runtime_status_embedded_heartbeat_stale_health_degraded
test_runtime_status.py::test_build_runtime_status_embedded_heartbeat_stale_not_running
test_segment_finalize_sidecar.py::test_hls_finalize_uploads_sidecars_not_whole_mp4
test_segment_finalize_sidecar.py::test_hls_post_process_skips_whole_file_upload
test_segment_process.py::test_segment_process_deletes_local_only_after_upload_confirmed
test_segment_process.py::test_segment_process_keeps_local_on_upload_failure
test_streaming_benchmark.py::test_live_stats_check_targets_fail_exit_code
test_streaming_config_semantics.py::test_streaming_finalize_remux_when_configured
test_streaming_stt_mock_ws.py::test_streaming_stt_session_mock_ws_writes_partial_and_final
```

## 建议修复顺序

1. **API 删除类**（最快）：`notify`、`*_run_once_*` → 改测 `MonitorExecutor` / `reconcile_content` / gateway 路径
2. **legacy guard**：统一 fixture `pipeline_mode=streaming` 或显式测 `RecordingError`
3. **SlowTick / distill**：更新 `test_live_scheduler` 期望（无 distill_pool）
4. **finalize/ffmpeg/HLS**：补有效媒体夹具或 mock `finalize_recording` / segment upload
5. **streaming benchmark / runtime_status**：对齐当前阈值与 `prepare_embedded_monitor_startup` mock

## 验证命令

```bash
pytest tests/unit -v -m "not live" --tb=short -q
python scripts/issue_verify.py --issue 396
```

## 非目标

- 恢复 `run_once`、`_emit_pipeline_notifications`、SlowTick 内嵌 distill
- `tests/ -m live` 网络用例
