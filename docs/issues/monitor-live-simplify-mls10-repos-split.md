---
epic: monitor-live-simplify-2026-07-06
depends_on: []
github: 396
---

# MLS-10：`repos.py` 按域拆分

规格：§3 P3-4、D12（独立 PR，可与 MLS-7+ 并行）

## 验收标准

- [x] `storage/repos/` 包；单文件 <800 行
- [x] `DesktopChatRepo` 迁至 `agent/` 或 `storage/chat.py`
- [x] 全量 `pytest tests/unit` 绿

## 验证命令

```bash
pytest tests/unit -v -m "not live" --tb=short -q
ruff check src/media2text/core/storage/
```
