---
issue: 375
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/375
branch: issue-375-monitor-db-lock-e2e
depends_on: [dl4d, mh4d]
---

# E2E-1：DB 锁压测 + Epic 验收 gate

GitHub Issue: [#375](https://github.com/oychao1988/media2text/issues/375)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§2 Success Criteria W1–W3、§10.2  
系列：DL-4d + MH-4d → **E2E-1**（Epic 最后一单）

## 背景

Phase 2 全部 Issue 合并后，需压测证明 embedded monitor **30min 无 sustained `task_scheduler_db_locked`**，并填 Epic acceptance 文档。

## 验收标准

### Task 1 — 压测脚本

- [ ] 新增 `scripts/db_lock_stress.py` 或 `tests/stress/test_db_lock_stress.py`（`pytest -m db_stress`）
- [ ] Mock 11 creators parallel probe + scheduler 60s：`task_scheduler_db_locked` count == 0
- [ ] `live_tick` max gap < 2 × `live_poll_interval_sec`

### Task 2 — Epic acceptance

- [ ] 新增 `docs/superpowers/verification/2026-07-05-monitor-db-write-path-phase2-acceptance.md`
- [ ] 更新 `docs/issues/epic-manifests/monitor-db-write-path-phase2-2026-07-05.yaml` acceptance_doc 路径
- [ ] `python scripts/epic_verify.py monitor-db-write-path-phase2-2026-07-05` exit 0

### Task 3 — 7/3 回归文档

- [ ] acceptance 表含 W4 僵尸 recovery 单测引用 + 7/3 事故 N/A 说明

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_session_recovery_offline_finalize.py tests/stress/test_db_lock_stress.py -v -m "not db_stress"
pytest tests/stress/test_db_lock_stress.py -v -m db_stress
python scripts/epic_verify.py monitor-db-write-path-phase2-2026-07-05
pytest tests/unit/test_probe_live_parallel.py tests/unit/test_task_scheduler.py tests/unit/test_db_write_gateway.py tests/unit/test_session_state_machine.py -v --tb=short -q
```

## 非目标范围

- 真实 11 博主 `pytest -m live`（acceptance 标 **手工/N/A** 可选）
- external + embedded 双进程零 busy（spec §8 已知限制）

## 依赖与顺序

- **依赖 DL-4d、MH-4d 合并**；Epic 关单闸门
