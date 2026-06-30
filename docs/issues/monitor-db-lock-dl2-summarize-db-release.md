---
issue: 357
epic: monitor-db-lock-write-path-2026-06-30
github: 357
branch: issue-357-monitor-db-lock-dl2
depends_on: [356]
---

# DL-2：post_process summarize — LLM 期间释放 DB 连接

GitHub Issue: [#357](https://github.com/oychao1988/media2text/issues/357)  
Epic：**Monitor DB Lock Write Path**（2026-06-30）  
系列：DL-1 → **DL-2** → DL-3

## 背景

`_run_summarize()` 在 `open_db()` 后进入 `stage_event` 上下文，并在其中调用 `maybe_summarize_after_transcribe()`（LLM，可达数分钟）。虽单条 SQL autocommit，但：

- worker 线程长期占用连接槽位，与 live probe / scheduler 写碰撞概率上升；
- `stage_event` started 与 completed 之间夹 LLM，拉长 pipeline_events 行「进行中」窗口；
- 2026-06-30 现场有 summarize job `running` 6+ 小时，加剧 DB 争用。

本 Issue：**LLM 调用前关闭连接；完成后再开短连接写 summary 元数据 / manifest / stage_event completed**。

## 验收标准

### Task 1 — 重构 `_run_summarize`

- [ ] `update_stage(summarize)` 后 **close** worker conn
- [ ] `maybe_summarize_after_transcribe` 在无 DB 连接下执行
- [ ] LLM 完成后新开 conn：`stage_event` 仅包裹快速 DB 操作，或等价地 insert started → LLM → insert completed（duration 含 LLM）
- [ ] 失败路径仍 `mark_failed` / pipeline event failed

### Task 2 — 测试

- [ ] 单测：mock LLM 延迟期间，无 `open_db` 连接保持（spy connect 计数或 mock）
- [ ] 现有 `tests/unit/test_post_process*.py` 相关 summarize 用例 PASS

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_post_process_repo.py tests/unit/test_post_process_summarize_db.py tests/unit/test_streaming_finalize.py -v -k "summarize or post_process"
ruff check src/media2text/core/live/post_process.py
```

## 非目标范围

- summarize 算法 / prompt 变更
- 取消 `stage_event` 观测（可调整记录时机，不删表）
- DL-1 probe 路径（已合并前置）

## 依赖与顺序

- **依赖 DL-1 合并**（减少并行 probe 写竞争后再验 summarize）
