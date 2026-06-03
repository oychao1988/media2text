## 背景

P0（#81）三线程隔离与 P1（#83）墙钟 offline + `live_ended` 已 merge main。仍缺 **pipeline 事件流** 与 **`live status|timeline|stats` CLI**（G7/G8）。

**参考**

- Spec §6.2、§9：[docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md](docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md)
- Plan P2 Task 7–8：[docs/superpowers/plans/2026-06-03-live-pipeline-v2.md](docs/superpowers/plans/2026-06-03-live-pipeline-v2.md)

## 验收标准

### Task 7 — `live_pipeline_events`

- [ ] `live_pipeline_events` 表 + index（`db.py`）
- [ ] `PipelineEventRow` + `PipelineEventRepo`（insert started / complete with `duration_ms`）
- [ ] `src/media2text/core/live/pipeline_events.py`：`emit_event` / `complete_event` helper
- [ ] `recording.py`：instrument `detected_live`、`stream_resolve`、`recording`、`remux`（含 offline_pending / offline_cancelled）
- [ ] `post_process.py`：instrument `transcribe`、`summarize`、`cloud_upload`
- [ ] `tests/unit/test_pipeline_events.py`

### Task 8 — CLI

- [ ] `src/media2text/cli/live.py`：`status`、`timeline`、`stats`（均支持 `--json`）
- [ ] `main.py` 注册 `live` typer
- [ ] `live status --json` 形状含 `active_recordings`、`post_process`（pending/running jobs、max_workers）
- [ ] `live timeline <session_id> --json`：有序 events + duration_ms
- [ ] `live stats --days N --json`：按 stage 聚合 P50/P95（基于 events）
- [ ] `tests/unit/test_live_status_cli.py`

### 质量

- [ ] `pytest tests/unit/test_pipeline_events.py tests/unit/test_live_status_cli.py -v`
- [ ] `pytest tests/ -v`、`ruff check src tests`
- [ ] 更新 `CLAUDE.md` 命令速查

## 验证命令

```bash
source .venv/bin/activate
ruff check src tests
pytest tests/unit/test_pipeline_events.py tests/unit/test_live_status_cli.py -v
pytest tests/ -v
media2text live status --json
media2text live timeline <session_id> --json
media2text live stats --days 7 --json
```

## 非目标范围

- **P3**：`scan_concurrency`、adaptive workers
- `post-process retry` CLI（spec 提及，另开单）
- Redis / 多进程

## 待确认问题

无。

## 实现备注

- GitHub Issue: [#85](https://github.com/oychao1988/media2text/issues/85)
- 分支建议：`issue-85-live-pipeline-v2-p2`
