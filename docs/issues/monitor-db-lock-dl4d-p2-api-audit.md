---
issue: 374
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/374
branch: issue-374-monitor-db-lock-dl4d
depends_on: [dl4c]
---

# DL-4d：P2 API/Hermes + 删除 `_sqlite_write_lock` + audit CI

GitHub Issue: [#374](https://github.com/oychao1988/media2text/issues/374)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§4.4 P2、§4.3  
系列：DL-4c → **DL-4d**

## 背景

P1 完成后，API 写路由、Hermes `SessionDB`、剩余 repos mutator 全部经 gateway；删除 `_sqlite_write_lock`；CI audit 防止新裸 commit。

## 验收标准

### Task 1 — 剩余 mutators

- [x] `CreatorRepo`、`AwemeRepo` 等 P2 mutators 经 gateway
- [x] `agent/hermes_state.py` `_write_with_retry` 改 gateway
- [x] API 写路由（recording start/stop、creators mutate）经 gateway

### Task 2 — 删除旧锁

- [x] 删除 `db.py` 的 `_sqlite_write_lock`（`with_db_lock_retry` 仅委托 gateway）
- [x] grep 生产代码无 scattered `with_db_lock_retry(lambda: open_db` 模式

### Task 3 — Audit CI

- [x] 新增 `scripts/audit_db_writes.py`：检测 `repos.py` / `state_writer.py` 内裸 `commit()` 不在 gateway 包装
- [x] `.github/workflows/ci.yml` 或 `issue-verify` 调用 audit（fail on regression）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/audit_db_writes.py
pytest tests/unit/test_hermes_db_lock.py tests/unit/test_db_write_gateway.py -v
ruff check src/media2text/core/storage/db.py src/media2text/agent/hermes_state.py
```

## 非目标范围

- Hermes 拆独立 `hermes.db`（未来 Epic）
- E2E 压测（→ E2E-1）

## 依赖与顺序

- **依赖 DL-4c**；与 MH-4d 可并行

## 实现备注（2026-07-06 orchestrator 补账）

- `_sqlite_write_lock` 已删除；`with_db_lock_retry` 在 gateway 未运行时 inline retry（CLI/单测），非 Issue 字面「仅委托 gateway」——见 retro review 非阻塞备注。
