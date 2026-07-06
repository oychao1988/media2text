---
epic: monitor-live-simplify-2026-07-06
depends_on: []
---

# MLS-11：`creator_distill` 与 monitor 解耦

规格：§3 P3-5

## 验收标准

- [ ] `SlowTickLoop` 不再 import `agent.creator_distill.pool`
- [ ] distill 改 CLI/cron 或 opt-in 配置
- [ ] `core/monitor`、`core/live` 无 `import media2text.agent`

## 验证命令

```bash
pytest tests/unit/test_monitor_mp_smoke.py -v
rg 'from media2text\.agent' src/media2text/core/monitor src/media2text/core/live
```
