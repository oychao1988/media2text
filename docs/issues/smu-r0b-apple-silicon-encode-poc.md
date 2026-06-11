---
issue: 305
epic: session-media-unified
github: 305
branch: issue-305-smu-r0b-apple-silicon-encode-poc
depends_on: [297]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R0b：Apple Silicon S6 补跑（Encode PoC 门禁）

## 背景

#297（SMU-R0）已在 Intel 上完成 codec 矩阵与验收表，但 **Spec R0 首要项「Apple Silicon 重跑 S6」** 因开发机为 x86_64 未实测。本 Issue 在 **M 系列 Mac** 上补跑 `hevc_videotoolbox` + `libx264`，更新验收表 Apple 段；若 `s6_pass: true` 再评估是否允许 #298 将 example 默认改为 `encode.mode: compress`。

**前置**

- 脚本：`scripts/benchmark_live_compress.py`（#297）
- 验收表：`docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`
- Intel 基线：#297 已填（S6 未过，不得开 compress）

## 验收标准

### Task 0.b.1 — Apple Silicon benchmark（人工，须 M 系列硬件）

- [ ] 在 Apple Silicon 上使用与 Intel 相同 FLV 样本（或等价 720p+ 直播 FLV）跑：
  - `hevc_videotoolbox`
  - `libx264`
- [ ] 将 stdout JSON 指标写入验收表 **Apple Silicon** 段（替换 `skipped` 行）
- [ ] 每行标注 `s6_pass: true|false`

### Task 0.b.2 — 门禁决策更新

- [ ] 验收表「门禁决策」与 `config.example.yaml` 注释一致：
  - 任一 Apple 行 `s6_pass: true` → 可在 #298 **讨论** example `encode.mode: compress`（仍须产品确认）
  - 全部 `s6_pass: false` → **保持** `compress.enabled: false` / `encode.mode: copy`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_benchmark_live_compress.py -v
ruff check scripts/benchmark_live_compress.py
test -f docs/superpowers/verification/2026-06-09-live-compress-benchmark.md
# 人工（须 M 系列 Mac + FLV 样本）:
# SAMPLE=data/creators/<sec_uid>/live/<timestamp>.flv
# python scripts/benchmark_live_compress.py --sample "$SAMPLE" --video-codec hevc_videotoolbox --json
# python scripts/benchmark_live_compress.py --sample "$SAMPLE" --video-codec libx264 --json
```

## 非目标范围

- 修改 benchmark 脚本行为（除非补跑暴露 bug）
- 接入 `hls_recorder` / `live.encode`（#298）
- Intel 矩阵重跑（#297 已完成）

## 依赖与顺序

- **依赖**：#297 脚本与验收表结构
- **inform**：#298 默认 compress 须读本 Issue 更新后的验收表
- **Epic**：`session-media-unified` 中 **optional**（无 Apple 硬件时不阻塞 #298–#302）
- **建议分支**：`issue-305-smu-r0b-apple-silicon-encode-poc`

## GitHub

- Issue: [#305](https://github.com/oychao1988/media2text/issues/305)
