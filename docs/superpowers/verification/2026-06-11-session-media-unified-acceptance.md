# Session Media Unified Refactor — Epic 验收

规格：[2026-06-11-session-media-unified-refactor-design.md](../specs/2026-06-11-session-media-unified-refactor-design.md)  
计划：[2026-06-11-session-media-unified.md](../plans/2026-06-11-session-media-unified.md)  
Issue 索引：[docs/issues/README.md](../../issues/README.md#session-media-unified-refactor2026-06-11已交付)

> Epic 闸门：#296–#301 全部合并后执行 `python scripts/epic_verify.py session-media-unified`。

## 总 verdict

| 类别 | 结论 |
|------|------|
| **Issue PR** | #296 [#304](https://github.com/oychao1988/media2text/pull/304) · #297 [#303](https://github.com/oychao1988/media2text/pull/303) · #298 [#307](https://github.com/oychao1988/media2text/pull/307) · #299 [#308](https://github.com/oychao1988/media2text/pull/308) · #300 [#309](https://github.com/oychao1988/media2text/pull/309) · #301 [#310](https://github.com/oychao1988/media2text/pull/310) · #302（本 PR） |
| **Epic manifest** | `python scripts/epic_verify.py session-media-unified` PASS |
| **前置 Epic** | `live-segment-media` + `live-segment-media-gap-fix`（LSM S1–S5 继承） |

**Epic 签署:** **VERDICT: PASS**（US3 Apple Silicon S6 **skipped**：[#305](https://github.com/oychao1988/media2text/issues/305) 未合并，无 M 系列硬件补跑；`encode.mode` 保持 `copy`。）

---

## Success Criteria（US1–US10）

| ID | 指标 | 目标 | 证据 | 状态 |
|----|------|------|------|------|
| US1 | 新 session 默认路径 | 100% `streaming+hls+segment`（无 legacy 新录） | [#298](https://github.com/oychao1988/media2text/issues/298) `config.example.yaml`：`live.media.format: hls`、`live.encode`、`segment_pipeline.enabled: true`；`test_doctor_legacy_pipeline.py` 覆盖 `live_pipeline_deprecated` 警告 | [x] |
| US2 | 本地磁盘峰值 | ≤ 2 × segment_size（**继承 LSM S1**） | [#271](https://github.com/oychao1988/media2text/issues/271) `test_task_scheduler_segment_order.py`；[LSM 验收 S1](./2026-06-09-live-segment-media-acceptance.md) | [x] unit |
| US3 | 压缩后云盘体积 | ≤ 原 copy 码率 **40%**（**继承 LSM S6**，PoC 硬件） | [#297](https://github.com/oychao1988/media2text/issues/297) Intel 矩阵 + [compress benchmark](./2026-06-09-live-compress-benchmark.md)；Apple Silicon **skipped**（[#305](https://github.com/oychao1988/media2text/issues/305) 未合并，验收表 Apple 段 `s6_pass: skipped`） | [x] skipped |
| US4 | 断流场次云播 | `discontinuity_at` 非空 + 本地段已删 → Desktop **可播** hls.js | [#296](https://github.com/oychao1988/media2text/issues/296) dogfood `20260611T110019Z`；[SMU-R2 验收](./2026-06-12-smu-r2-playback-unify-acceptance.md) | [x] |
| US5 | VOD 云播 | 本地删 MP4、云有备份 → 可 seek 播放 | [#299](https://github.com/oychao1988/media2text/issues/299) `test_api_media_cloud_fallback.py` | [x] unit |
| US6 | Legacy 兼容 | 旧 MP4/FLV 场次只读播放不退化 | [#300](https://github.com/oychao1988/media2text/issues/300) `test_live_legacy_pipeline.py` + `test_api_history_media.py`；Vitest legacy 分支回归 | [x] unit |
| US7 | 故障隔离 | upload/encode 失败不停录（**继承 LSM S5**） | [#271](https://github.com/oychao1988/media2text/issues/271) + [#283](https://github.com/oychao1988/media2text/issues/283) `test_segment_process*.py`；[LSM 验收 S5](./2026-06-09-live-segment-media-acceptance.md) | [x] unit |
| US8 | STT finalize | 封存 ≤10s（v3 回归） | epic_verify `streaming-stt-finalize`：`test_segment_finalize_sidecar.py` + `test_streaming_finalize_merges_reconnect_segments` | [x] unit |
| US9 | 云 master 回退 | 本地无 `master.m3u8`、云有 m3u8 → `playback.m3u8` 200 | [#296](https://github.com/oychao1988/media2text/issues/296) `test_playback_m3u8_from_cloud_when_local_master_missing` + `scripts/verify_smu_r2_dogfood.py` | [x] |
| US10 | Part 代理 Range | hls.js seek 跨段；无 302 URL 过期断播 | [#296](https://github.com/oychao1988/media2text/issues/296) + [#301](https://github.com/oychao1988/media2text/issues/301) `test_multi_part_cloud_proxy_*`；`grep` 无 Aliyun 302 redirect | [x] unit |

### US1 证据摘录

**`config.example.yaml`（#298 / PR #307）推荐路径：**

```yaml
live:
  pipeline_mode: streaming
  media:
    format: hls
  encode:
    mode: copy   # S6 未过；见 compress benchmark
  segment_pipeline:
    enabled: true
```

**Doctor legacy 警告（单测模拟 `pipeline_mode=legacy`）：**

```json
{
  "code": "live_pipeline_deprecated",
  "hint": "use streaming + hls + segment_pipeline; see config.example.yaml"
}
```

来源：`tests/unit/test_doctor_legacy_pipeline.py`（生产 `doctor --json` 在 `pipeline_mode=streaming` 时不输出该警告）。

### US3 skipped 说明

| 平台 | codec | s6_pass | 原因 |
|------|-------|---------|------|
| Apple Silicon | `hevc_videotoolbox` / `libx264` | **skipped** | [#305](https://github.com/oychao1988/media2text/issues/305) 未合并；开发机 x86_64，无 M 系列补跑 |
| Intel i7-8750H | 全矩阵 | **false** | [#297](https://github.com/oychao1988/media2text/issues/297) 已填；HEVC VT `-12905`；H.264/x264 体积未压缩 |

门禁决策：**保持** `encode.mode: copy`（见 [compress benchmark §门禁决策](./2026-06-09-live-compress-benchmark.md)）。

### US4 / US9 / US10 dogfood（#296）

| 项 | 值 |
|----|-----|
| Session ID | `64cd09e0-e249-4b0e-9bb6-33f4c7131397` |
| 目录 | `data/creators/.../live/20260611T110019Z` |
| 特征 | `media_format=hls`，`#EXT-X-DISCONTINUITY`，part 1/2/5/6 已上云，本地 `.m4s` 部分缺失 |

```bash
python scripts/verify_smu_r2_dogfood.py
# SMU-R2 dogfood: ALL PASS
```

详见 [2026-06-12-smu-r2-playback-unify-acceptance.md](./2026-06-12-smu-r2-playback-unify-acceptance.md)。

---

## Issue 验收

| Issue | 范围 | PR | 验证 |
|-------|------|-----|------|
| #296 | SMU-R2 播放统一 | [#304](https://github.com/oychao1988/media2text/pull/304) | `issue_verify.py --issue 296` |
| #297 | SMU-R0 Encode PoC 矩阵 | [#303](https://github.com/oychao1988/media2text/pull/303) | `issue_verify.py --issue 297` |
| #298 | SMU-R1 `live.encode` + example hls | [#307](https://github.com/oychao1988/media2text/pull/307) | `issue_verify.py --issue 298` |
| #299 | SMU-R3 VOD 云 Range | [#308](https://github.com/oychao1988/media2text/pull/308) | `issue_verify.py --issue 299` |
| #300 | SMU-R4 Legacy 退场 | [#309](https://github.com/oychao1988/media2text/pull/309) | `issue_verify.py --issue 300` |
| #301 | SMU-R5 播放硬化 | [#310](https://github.com/oychao1988/media2text/pull/310) | `issue_verify.py --issue 301` |
| #302 | SMU-R6 Epic 验收 | （本 PR） | `issue_verify.py --issue 302` |

**Optional（不阻塞 Epic）：** [#305](https://github.com/oychao1988/media2text/issues/305) Apple Silicon S6 补跑 — epic manifest `optional: true`。

---

## Epic verify 执行记录

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
python scripts/epic_verify.py session-media-unified
python scripts/issue_verify.py --issue 296
python scripts/issue_verify.py --issue 297
python scripts/issue_verify.py --issue 298
python scripts/issue_verify.py --issue 299
python scripts/issue_verify.py --issue 300
python scripts/issue_verify.py --issue 301
```
