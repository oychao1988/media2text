# 设计文档与 monitor 模型对齐

> **类型**：文档  
> **建议分支**：`issue-9-design-spec-sync`  
> **GitHub**：[#9](https://github.com/oychao1988/media2text/issues/9)

## 背景

实现已演进为 `monitor watch` + `monitor_enabled`，而 `docs/superpowers/specs/2026-05-20-media2text-douyin-design.md` 仍描述 `live watch` / `watch_live`。`creator-monitor-and-profile.md` 验收项未勾选。

## 验收标准

- [x] 更新 design spec：CLI 表、`creators` 表、`monitor watch`、VOD tick、`platform_changed` JSON、退出码说明与代码一致。
- [x] `docs/issues/creator-monitor-and-profile.md` P1–P3 全部勾选为已完成。
- [x] `docs/issues/README.md` 索引与 PR 状态可追踪。
- [x] README 命令表补充 `--limit`、`--delete-media`、云端转写配置说明。

## 非目标

- 重写整份 design spec 全文；仅同步与当前代码冲突的章节。

Fixes #9
