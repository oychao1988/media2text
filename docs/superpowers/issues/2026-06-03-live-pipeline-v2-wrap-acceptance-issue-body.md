## 背景

[2026-06-03-live-pipeline-v2-design.md](../specs/2026-06-03-live-pipeline-v2-design.md) §12 手动验收清单仍为 `[ ]`，无结构化验收记录。需要一次 **生产/准生产** 可复现的收尾验证，闭合 G1–G8 代理指标。

## 验收标准

- [ ] 新增 `docs/superpowers/verification/2026-06-03-live-pipeline-v2-acceptance.md`，逐项记录 Spec §12：
  - LiveTick 在 post-process 长跑时仍 ~10s（日志或 `live status`）
  - 首次 offline ≤5s 内 `live_ended`（说明 poll 间隔约束）
  - 持续 offline ≥45s → `recording_completed`
  - 两场重叠 live 互不拖死 poll
  - `live timeline` 全链：detected_live → recording → remux → transcribe（+ summarize/cloud 若启用）
  - `live stats --days N` 含 G1 相关 stage P50/P95
- [ ] 每条注明：命令、样例 `session_id`、通过/失败、日期、环境备注（勿贴密钥）
- [ ] Spec §12 勾选为已完成，并链接 verification 文档
- [ ] 若某项失败：在本 issue 或子 issue 记录 blocker，不勾选

## 验证命令（执行人填写结果到 verification 文档）

```bash
media2text live status --json
media2text live timeline <session_id> --json
media2text live stats --days 7 --json
# 守护进程日志：grep live_recording / bilibili status 间隔
```

## 非目标

- 新功能开发（仅验证；失败项另开 bug issue）
- CI 自动化压测（可后续单开）

## 依赖

- 建议在「config 默认 10s」「events 补全」合并后执行，避免验收口径不一致
