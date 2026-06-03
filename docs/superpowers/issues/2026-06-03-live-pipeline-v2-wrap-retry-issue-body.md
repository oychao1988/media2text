## 背景

Live Pipeline v2 P0–P3（#81 / #83 / #85 / #87）已 merge。Spec §10 与 P2 issue 仍要求失败 job 可重试，P3 明确列为非目标，**尚未单独开单**。

当前仅有 `media2text post-process run`；失败 job 只能改 DB 或重跑全队列。

**参考**

- [docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md](../specs/2026-06-03-live-pipeline-v2-design.md) §9、§10
- `src/media2text/cli/post_process.py`

## 验收标准

- [ ] CLI：`media2text post-process retry <job_id> --json`
  - 仅 `status=failed` 可重试；重置为 `pending`（或等价 `claim_pending` 路径）
  - JSON：`ok`、`job_id`、`previous_status`、`new_status`；非法状态返回明确 `error`
- [ ] `PostProcessJobRepo`：`retry_failed(job_id)` 或复用 `enqueue` 语义，带 `UPDATE ... WHERE status='failed'`
- [ ] 单元测试：failed→pending；running/pending 拒绝；不存在 job
- [ ] `CLAUDE.md` 命令速查补充 `post-process retry`
- [ ] （可选）`post-process status [--session ID] --json` 列出 failed + stage；若做则与 `live status` 字段对齐，避免重复造轮子

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_post_process_job_repo.py -v -k retry
ruff check src tests
media2text post-process retry <failed_job_id> --json
```

## 非目标

- 改 notify / offline / scheduler 线程模型
- 自动无限重试（需显式 CLI 或未来配置）
