---
issue: 334
epic: monitor-db-contention-2026-06-25
github: 334
branch: issue-334-monitor-db-mp1-post-process-dedupe
depends_on: []
---

# MP-1：post_process 去重与 stale 回收（SQLite 锁竞争缓解）

GitHub Issue: [#334](https://github.com/oychao1988/media2text/issues/334)  
Epic：**Monitor DB Contention**（2026-06-25 直播检测但未开录事故）  
系列：**MP-1** → MP-2 → MP-3

## 背景

2026-06-25 生产事故：博主已开播（`creator_live_snapshots.is_live=1`），但 `active_recordings` 为空。根因链之一：

1. 万狮虎上一场 HLS 直播 finalize 后，`post_process_jobs` **无 session 级去重**，同一 session 累积 6+ 个 `running/pending` job（summarize 卡住）。
2. `reset_stale_running` 默认阈值 **3600s**，僵尸 job 长时间占用 post_process worker 与 DB 连接。
3. stale 回收将 job 改回 **`pending`** 而非终止，与 live lane（`prepare_live_recording`）争抢 SQLite，日志大量 `database is locked`。

本 Issue 落实 **post_process 幂等入队 + 对已完结 session 的 stale 终止**，减轻 DB 锁竞争。

## 验收标准

### Task 1 — `PostProcessJobRepo.ensure_enqueue`

- [x] 新增 `ensure_enqueue(session_id, ...)`：同 session 已有 `pending`/`running` job 时返回已有 id，不 INSERT 新行
- [x] DB migration：partial unique index `idx_post_process_jobs_active_session ON post_process_jobs(session_id) WHERE status IN ('pending','running')`
- [x] `enqueue()` 保留（测试/CLI 直调）；finalize 路径改调 `ensure_enqueue`
- [x] `test_post_process_ensure_enqueue_dedupes_active_session` 通过

### Task 2 — stale 回收不对已完结 session 复活

- [x] `reset_stale_running`：若 `live_sessions.status` 为 `completed`/`failed`，将 stale job 标为 `failed`（error=`superseded:session_terminal`），**不**改回 `pending`
- [x] `test_post_process_stale_completed_session_marked_failed` 通过

### Task 3 — 配置默认值

- [x] `config.example.yaml` 中 `live.post_process_stale_running_sec` 默认 **600**（原 3600）；`config.py` Field default 同步
- [x] 已有 `config.yaml` 不受影响（用户值优先）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_post_process_repo.py tests/unit/test_streaming_finalize.py -v
ruff check src/media2text/core/storage/repos.py src/media2text/core/live/recording.py src/media2text/core/config.py
```

## 非目标范围

- Desktop serve 与外部 CLI 单 owner（→ MP-2）
- live lane 暂停 post_process drain（→ MP-3）
- `open_db()` migration 单次化（另开 Issue）
- Playwright 并发槽位调整
- 手工 `sqlite3` 清队列运维脚本

## 依赖与顺序

- **无前置依赖**
- **阻塞**：MP-2、MP-3 可并行，但建议先合并本单
