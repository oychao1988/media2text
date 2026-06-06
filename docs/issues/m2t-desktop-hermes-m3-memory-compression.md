# m2t-desktop Hermes M3：MEMORY + session_search FTS + compression lineage

## 背景

M2 后 Agent 可对话但缺 Hermes 记忆与上下文治理。M3 交付 curated **`memory` tool**、**`session_search` FTS5**、**middle-turn compression**（D12：`fork_session` + `parent_session_id`，`protect_last_n=20`）。

**参考**：Hermes §8–§9、§21.2 配置、H4–H6、H5

**依赖**：M1（Agent loop）、M2 推荐已合并（非硬依赖）。

## 验收标准

### Task 1 — Curated memory

- [ ] `data/.agent/MEMORY.md` + `USER.md`（+ 可选 `SOUL.md`）读写；`memory` tool agent 内拦截
- [ ] volatile tier 会话启动 frozen 注入；mid-turn 写盘 **不**注入当前 turn（Hermes 语义）
- [ ] `memory.*` 配置上限 + 内容安全扫描（regex，§7.2）
- [ ] H5：新 thread 首条 prompt 含 MEMORY 块

### Task 2 — session_search（FTS5）

- [ ] `messages_fts` + trigger 同步；CJK `messages_fts_trigram`（或等价 trigram 表）
- [ ] `session_search` tool：`query`、`limit`、`session_id?`、`creator_id?`
- [ ] 博主 thread 默认 `creator_id=thread.creator_id`；全局 thread 默认不限定
- [ ] H6：1 万 message 合成数据 P95 ≤ 200ms（pytest 计时）

### Task 3 — Compression

- [ ] `context_compressor.py` + `auxiliary_client.py`（summarize LLM 或独立 fallback）
- [ ] preflight `compression.preflight_ratio` + post-turn `compression.auto_ratio`
- [ ] 超阈值 → `SessionDB.fork_session()`；`display_thread_id` 不变；replay 含 `compression_summary` message
- [ ] H4：DB 可见 `parent_session_id` lineage

### Task 4 — WAL

- [ ] SessionDB WAL mode + write retry jitter（§21.4）

### 测试

- [ ] `pytest tests/unit/test_agent_memory.py tests/unit/test_agent_session_search.py tests/unit/test_agent_compression.py -v -m agent`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_agent_memory.py tests/unit/test_agent_session_search.py tests/unit/test_agent_compression.py -v -m agent
```

## 非目标范围

- 博主级 `creators/.../.agent/MEMORY.md`（M5a / D15）
- skills 渐进披露（M4）
- `CreatorAgentEvolve` 写 MEMORY（M5c）

## 实现备注

- 分支：`issue-183-hermes-m3-memory-compression`
- GitHub Issue: [#183](https://github.com/oychao1988/media2text/issues/183)
