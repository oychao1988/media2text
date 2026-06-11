---
issue: 301
epic: session-media-unified
github: 301
branch: issue-301-smu-r5-hardening-cleanup
depends_on: [296, 283]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R5：播放硬化（删 302 残留 + G3 共存回归）

## 背景

#296 将 part/init 云回退改为 Range 代理后，应删除 `_cloud_part_redirect` / `_cloud_init_redirect` 302 路径（或标记 internal deprecated 一 release 后移除）。#283（G3 segment job retry）已交付，本 Issue 做 **SMU Epic 硬化收尾**：确认无 302 回归、segment retry 与 cloud proxy 共存。

**参考**

- [design spec §7 R5、US10](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [plan SMU-R5](../superpowers/plans/2026-06-11-session-media-unified.md)
- G3：`docs/issues/live-segment-gap-g3-segment-job-retry-reconciler.md`（#283）

## 验收标准

### Task 5.1 — 移除 302 云 redirect

- [x] `playback.py` 无 `RedirectResponse` 到 Aliyun 临时 URL（part/init）
- [x] 删除或 privatize `_cloud_part_redirect` / `_cloud_init_redirect`；更新/删除对应单测
- [x] 云 upstream 失败返回 **502** JSON（非 HTML），便于 hls.js 触发 Desktop error copy

### Task 5.2 — G3 回归

- [x] `pytest tests/unit/test_segment_process*.py tests/unit/test_task_scheduler_segment_order.py -v` 通过
- [x] `grep -R "302" src/media2text/api/routes/playback.py` 无 cloud redirect 用法

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_playback_api.py tests/unit/test_cloud_byte_proxy.py tests/unit/test_segment_process.py tests/unit/test_task_scheduler_segment_order.py -v
ruff check src/media2text/api/routes/playback.py
```

## 非目标范围

- 新 segment retry 逻辑（#283 已交付）
- VOD / encode 配置
- 监控 metrics 大盘

## 依赖与顺序

- **依赖**：#296 合并；#283 已关闭
- **Epic 最后一单**（#302 验收前）
- **建议分支**：`issue-301-smu-r5-hardening-cleanup`

## GitHub

- Issue: [#301](https://github.com/oychao1988/media2text/issues/301)
