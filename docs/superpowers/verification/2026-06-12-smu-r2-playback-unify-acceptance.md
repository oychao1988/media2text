# SMU-R2 播放统一 — Issue #296 验收

规格：[2026-06-11-session-media-unified-refactor-design.md](../specs/2026-06-11-session-media-unified-refactor-design.md)  
Issue：[smu-r2-playback-unify.md](../../issues/smu-r2-playback-unify.md)

## Dogfood 场次

| 项 | 值 |
|----|-----|
| Session ID | `64cd09e0-e249-4b0e-9bb6-33f4c7131397` |
| 目录 | `data/creators/MS4wLjABAAAAvOVYmHtxbIkHL6FLKewVaMeTD5rQ3CAwWMY3l4m3uNU/live/20260611T110019Z` |
| 特征 | `media_format=hls`，`#EXT-X-DISCONTINUITY`，part 1/2/5/6 已上云 |

## 自动化验收（2026-06-12）

```bash
source .venv/bin/activate
pytest tests/unit/test_cloud_byte_proxy.py tests/unit/test_session_playback.py \
  tests/unit/test_playback_api.py tests/unit/test_streaming_finalize.py \
  tests/unit/test_streaming_stt_resilience.py -v -m desktop
python scripts/verify_smu_r2_dogfood.py
pnpm --filter m2t-desktop test -- ViewPlayback.test.tsx
ruff check src/media2text/api/services/cloud_byte_proxy.py \
  src/media2text/api/services/session_playback.py \
  src/media2text/api/routes/playback.py
```

| ID | 验收项 | 证据 | 状态 |
|----|--------|------|------|
| U4 | discontinuity 走 hls.js 非 remux | `ViewPlayback.test.tsx` | [x] |
| U10 / US9 | 本地无 master → 云 master 200 + rewrite | `verify_smu_r2_dogfood.py` | [x] |
| U11 / US10 | part1/part2 云 Range 206 代理（非 302） | `test_multi_part_cloud_proxy_*` + dogfood | [x] |
| US4 | 断流 playlist 保留 `#EXT-X-DISCONTINUITY` | dogfood local master | [x] |

### Dogfood 脚本输出（摘要）

```
PASS: local master.m3u8 200 + discontinuity + part rewrite
PASS: cloud master fallback 200 + part rewrite
PASS: part 1 cloud Range proxy 206 len=1024
PASS: part 2 cloud Range proxy 206 len=1024
SMU-R2 dogfood: ALL PASS
```

### 修复记录（审查跟进）

- Aliyun CDN 下载需 `Referer: https://www.aliyundrive.com/`：`cloud_byte_proxy.stream_cloud_file` 与 `_fetch_cloud_m3u8_text` 已补齐（否则 part/m3u8 云回退 403 或 XML 错误体）。

## 仍 defer（非 #296）

| 项 | 归属 |
|----|------|
| ER4 `missing_parts[]` | R5 / #301 |
| 上游失败 502 JSON | R5 / #301 |
| 删除 `_cloud_*_redirect` 死代码 | R5 / #301 |

## VERDICT

**PASS**（Issue #296 Tasks 2.1–2.6；spec R2 核心 U4/U10/U11/U13 + US4/US9/US10 dogfood）
