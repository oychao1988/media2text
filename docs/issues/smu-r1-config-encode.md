---
issue: 298
epic: session-media-unified
github: 298
branch: issue-298-smu-r1-config-encode
depends_on: [297]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R1：`live.encode` 配置收拢 + example 默认 hls

## 背景

Spec **U1/U2**：唯一推荐路径 `streaming + hls + segment_pipeline`；压缩配置从 `live.compress` 迁移到 `live.encode`（`mode: copy|compress`，`video_codec: auto`）。保留 `compress` YAML **别名** 以免破坏现有 `config.yaml`。

**参考**

- [design spec §3–4、U1/U2](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [plan SMU-R1 Task 1.1](../superpowers/plans/2026-06-11-session-media-unified.md)
- PoC 门禁：#297 验收表 + [#305 Apple Silicon 补跑](smu-r0b-apple-silicon-encode-poc.md)（未通过则 example 仍 `encode.mode: copy`）

## 验收标准

### Task 1.1 — Config 模型

- [x] `LiveEncodeConfig` in `core/config.py`（`mode`, `video_codec`, `video_bitrate`, `audio_bitrate`）
- [x] `@model_validator`：`compress.enabled=true` → `encode.mode=compress`（别名迁移）
- [x] `tests/unit/test_encode_profile.py::test_compress_alias_migrates_to_encode` 通过

### Task 1.2 — `encode_profile.py`

- [x] `resolve_video_encoder()`：`copy` 或 auto 选 hevc → h264 VT → libx264
- [x] `hls_recorder.build_hls_recorder_args` 改用 `resolve_video_encoder`（不再直接读 `LiveCompressConfig`）

### Task 1.3 — Example 与文档

- [x] `config.example.yaml`：`live.media.format: hls`；新增 `live.encode` 块；`segment_pipeline.enabled: true`
- [x] `encode.mode: copy` 默认；注释指向 PoC 验收文档
- [x] CLAUDE.md / README 一句：新用户推荐 `streaming + hls + segment_pipeline`（**US1 文档级**；不强制改代码默认）

### Task 1.4 — Doctor 警告（spec §8 迁移）

- [x] `media2text doctor --json`：若 `live.pipeline_mode=legacy`，输出 `warnings[]` 含 `live_pipeline_deprecated` 与迁移指引（指向 example 推荐路径）
- [x] `tests/unit/test_doctor*.py` 或等价单测覆盖 legacy 警告

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_encode_profile.py tests/unit/test_hls_recorder.py -v
media2text doctor --json
ruff check src/media2text/core/config.py src/media2text/core/live/encode_profile.py src/media2text/core/live/hls_recorder.py
```

## 非目标范围

- 改 `pipeline_mode` 代码默认（仍尊重用户 yaml；example 推荐 streaming）
- Playback / cloud proxy（#296）
- VOD 云播（#299）

## 依赖与顺序

- **依赖**：#297 验收表可读（非阻塞合并，但默认 compress 须表内 Apple 或 Intel 行 `s6_pass: true`；Apple 见 #305）
- **建议分支**：`issue-298-smu-r1-config-encode`

## GitHub

- Issue: [#298](https://github.com/oychao1988/media2text/issues/298)
