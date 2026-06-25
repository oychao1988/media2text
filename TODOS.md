"""Manual smoke checklist (not run in CI)."""

## Monitor DB Contention / Hardening manual smoke

From [2026-06-25-monitor-db-contention-acceptance.md](docs/superpowers/verification/2026-06-25-monitor-db-contention-acceptance.md) §手动:

- [ ] 开机 `bin/monitor-watch-daemon.sh` 后不开 Desktop → `pgrep -fl "monitor watch"` 存活，`GET /api/runtime`（若 serve 未启则跳过）
- [ ] CLI daemon 运行中启动 Desktop → `GET /api/runtime` 显示 `managed_by=external`，health=healthy
- [ ] Desktop 无 CLI 时启动 → `managed_by=embedded`（需 `desktop.auto_start_monitor=true`）
- [ ] 博主开播且 post_process 积压时，日志出现 `post_process_deferred_for_live_lane`，随后 `prepare_live_recording` 成功
