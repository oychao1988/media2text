# P0 Archive 搜索与合规门禁（E1 + E4）

> **类型**：功能  
> **建议分支**：`issue-19-archive-search-compliance`  
> **GitHub**：[#19](https://github.com/oychao1988/media2text/issues/19)  
> **依赖**：[#18](https://github.com/oychao1988/media2text/issues/18) 已合并  
> **规格来源**：CEO E1 时间戳锚点、E4 合规包

## 背景

索引就绪后，用户需要 `media2text archive search <关键词>` 在数秒内命中转写段落，并带 **E1 锚点**（`segment_id`、`offset_sec`、`open_path`）便于跳转复盘。

对外产品口径要求 **E4 合规**：首次使用前确认免责声明；检索类命令在未确认前拒绝执行。

## 验收标准

### 搜索（E1）

- [ ] `archive search QUERY [--creator <id>] [--limit N] [--json]`：FTS 查询 `transcript_segments`。
- [ ] 每条命中 JSON 字段至少包含：`segment_id`、`offset_sec`（或 `start_sec`）、`session_id`、`session_type`、`creator_id`、`sec_uid`、`excerpt`、`transcript_path`、`started_at`（若 DB 有）。
- [ ] 无索引时：`ok: false` 或等价字段，`indexed: false`，提示运行 `archive index`；退出码与现有 CLI 约定一致（建议 1）。
- [ ] FTS 语法错误：用户可见「无效搜索语法」，不抛未处理 traceback。
- [ ] 共用 `core/archive/models.py` 中 `Hit` dataclass（供 timeline 单复用）。

### 合规（E4）

- [ ] `compliance accept`：写入 `data/.compliance-accepted`（ISO 时间 + 版本号）；`--json` 输出确认结果。
- [ ] 未接受时：`archive search`（本单范围；timeline/pricing 在后续单）返回退出码 **2**，JSON 含 `compliance_required: true` 与简短指引。
- [ ] `scripts/audit_compliance_copy.py`：扫描 `src/media2text/core/notify/`、`README.md` 等配置的禁词列表（荐股、跟单、买入卖出等模板用语）；CI 或本地可运行，违规时非零退出。
- [ ] README 增加固定声明：「个人研究档案工具，非投资咨询」。

### doctor 扩展（本单最小集）

- [ ] `doctor --json` 增加 `compliance_accepted: bool`（读 `data/.compliance-accepted`）。

## 验证命令

```bash
source .venv/bin/activate
ruff check src tests
pyright
pytest tests/unit/test_archive_search.py tests/unit/test_compliance.py tests/ -v

media2text compliance accept --json
media2text archive search "半导体" --json
media2text archive search "半导体" --creator <creator_id> --limit 10 --json
python scripts/audit_compliance_copy.py
media2text doctor --json
```

## 非目标范围

- `archive timeline`、跨场次时间线聚合（第三单）。
- `archive pricing-log`（第三单）。
- 飞书卡片文案改版（除非 audit 脚本发现必须改的禁词）。
- Tauri、Web UI 点击跳转锚点（P1；CLI JSON 预留字段即可）。

## 实现提示（给修单 Agent）

- 依赖上一单合并后的 `core/archive/indexer.py` 与 DB schema。
- 合规文件路径相对 `AppConfig.workspace`，勿提交 `data/` 内容。
- PR：`Fixes #<N>`；勿包含 notify WIP（在 `wip/notify-20260522`）。
