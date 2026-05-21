# P0 Archive 时间线与定价实验（E2 + E6）

> **类型**：功能  
> **建议分支**：`issue-20-archive-timeline-pricing`  
> **GitHub**：[#20](https://github.com/oychao1988/media2text/issues/20)  
> **依赖**：[#18](https://github.com/oychao1988/media2text/issues/18)、[#19](https://github.com/oychao1988/media2text/issues/19) 已合并  
> **规格来源**：CEO E2 跨场次关键词时间线、E6 虚拟定价实验

## 背景

复盘主场景是：对某博主在 7–30 天内围绕「半导体」等关键词，按时间看态度演变。需要 `archive timeline --creator <id> --keyword <K> [--days N]`，输出按 `started_at` 排序的 excerpt 列表，命中结构 **与 search 共用 E1 锚点**。

同时记录 founder 自用阶段「愿付 ¥99/月」的虚拟实验（E6），写入 `data/pricing-experiment.jsonl`，支撑 7 天 Assignment。

## 验收标准

### 时间线（E2）

- [ ] `archive timeline --creator <id> --keyword <K> [--days 30] [--limit N] [--json]`。
- [ ] 结果按场次 `started_at` 升序（新→旧或旧→新须在 help/README 写明，建议旧→新便于复盘）。
- [ ] 每条含 E1 字段：`segment_id`、`offset_sec`、`session_id`、`session_type`、`excerpt`、`transcript_path`、`started_at`。
- [ ] 零命中：JSON 明确 `hits: []`，非静默失败。
- [ ] 未 `compliance accept`：退出码 2，与 search 一致。
- [ ] 无索引：提示 `archive index`，行为与 search 一致。

### 定价实验（E6）

- [ ] `archive pricing-log [--yes|--no] [--note TEXT] [--creator <id>] [--session <id>] [--json]`：追加一行 JSONL 到 `data/pricing-experiment.jsonl`。
- [ ] 字段：`ts`（ISO8601）、`would_pay_99_cny`（bool）、`note`（可选）、`creator_id`、`session_id`（可选）。
- [ ] 文件不存在时自动创建；不提交 git。

### doctor 扩展

- [ ] `doctor --json` 增加 `index_stale`：存在 transcript 文件但 `transcript_segments` 未覆盖（启发式：抽样或计数对比，PR 说明算法）。
- [ ] `doctor --json` 增加 `monitor_lock_pid`：若存在 `data/.monitor-watch.lock` 则读出 PID，否则 null。

### 测试

- [ ] `tests/unit/test_archive_timeline.py`：多 session fixture；`--days` 过滤；零命中。
- [ ] `tests/unit/test_archive_pricing_log.py`：追加 jsonl、字段校验。
- [ ] 现有 `pytest tests/ -v` 全绿。

## 验证命令

```bash
source .venv/bin/activate
ruff check src tests
pyright
pytest tests/unit/test_archive_timeline.py tests/unit/test_archive_pricing_log.py tests/ -v

media2text compliance accept --json
media2text archive timeline --creator <creator_id> --keyword "半导体" --days 30 --json
media2text archive pricing-log --yes --note "复盘后愿付" --creator <creator_id> --json
cat data/pricing-experiment.jsonl
media2text doctor --json
```

## 非目标范围

- Tauri 时间线 UI、图表可视化。
- 多博主并排对比、云端同步。
- 外部付费墙或真实收款。
- E3 转写置信度展示与人工校正。
- 修改索引 schema（应在前两单完成）。

## 实现提示（给修单 Agent）

- 复用：`core/archive/search.py` 的 FTS 查询与 `Hit`；timeline 在应用层按 `session_id` 分组排序。
- `started_at` 来自 JOIN `live_sessions` / `awemes`，勿重复存储 display_name。
- PR：`Fixes #<N>`；合并顺序应在搜索/合规单之后。

## 7 天 Assignment（人类，非本单代码）

- 3 场已录直播 + 转写：记录 `archive search` / `timeline` 耗时是否 <10s。
- 至少 3 条 `pricing-experiment.jsonl`。
- 未达标则不做 Tauri（见 CEO plan）。
