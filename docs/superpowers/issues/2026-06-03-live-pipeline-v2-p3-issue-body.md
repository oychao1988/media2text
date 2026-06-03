## 背景

P0–P2 已 merge main。剩余 **P3**：并行 live 检测、`post_process_max_parallel: 0` 自适应 worker、文档收尾（G6/G8 部分）。

**参考**：Plan Task 9–11；Spec §8 `scan_concurrency`、`post_process_max_parallel: 0`

## 验收标准

- [ ] `LiveConfig.scan_concurrency: int = 4`；`post_process_max_parallel: 0` 表示 auto（`min(2, max(1, cpu_count // 2))`）
- [ ] `resolve_post_process_workers(cfg)` 供 `PostProcessExecutor` / scheduler 使用
- [ ] `scan_and_start` 对无 active session 的博主并行 `get_live_room`（ThreadPoolExecutor，`scan_concurrency`）
- [ ] `config.example.yaml` + `CLAUDE.md` 文档化
- [ ] 单元测试：worker 解析、并行 scan mock

## 验证命令

```bash
pytest tests/unit/test_post_process_pool.py tests/unit/test_live_recording_core.py -v
pytest tests/ -v
ruff check src tests
```

## 非目标

- `post-process retry` CLI
- 改 notify / offline 逻辑

## 实现备注

- GitHub Issue: [#87](https://github.com/oychao1988/media2text/issues/87)
- 分支：`issue-87-live-pipeline-v2-p3`
