---
epic: monitor-live-simplify-2026-07-06
github: 392
depends_on: [MLS-3]
---

# MLS-6：Desktop agent API 迁 `/api/agent/*`

规格：§3 P2-5、D11

## 验收标准

- [x] `useM2tAgent.ts` 改 `/api/agent/providers`（或等价端点）
- [x] 删 `api/routes/chat.py` deprecated 路由
- [x] Vitest `useM2tAgent.test.ts` 更新

## 验证命令

```bash
pnpm --filter m2t-desktop test
pytest tests/unit/test_api_agent_threads.py -v -m desktop
```
