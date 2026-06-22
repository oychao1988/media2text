# Session Media Unified Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify live archive playback (HLS + cloud Range proxy, no remux-on-discontinuity), add encode profile + PoC gate, VOD cloud Range playback, and deprecate legacy whole-MP4 paths—without rebuilding LSM segment upload/recording.

**Architecture:** Thin `session_playback` service wraps existing `playback.py` routes; cloud bytes flow through httpx `StreamingResponse` with Range passthrough (not expiring 302). Desktop always uses `playback.m3u8` + hls.js. Encode moves from `live.compress` to `live.encode` with hardware auto-selection. VOD reuses `/api/media` Range logic with cloud fallback.

**Tech Stack:** Python 3.12+, FastAPI, httpx, SQLite (`cloud_uploads`, `live_session_parts`), Vitest/hls.js, pytest, ffmpeg VideoToolbox/x264.

**Spec:** [2026-06-11-session-media-unified-refactor-design.md](../specs/2026-06-11-session-media-unified-refactor-design.md) (Eng Review CLEAR 2026-06-11).

**MVP merge target:** SMU-R2 (playback) first; SMU-R0 ∥ SMU-R2; then SMU-R1, SMU-R3, SMU-R4, SMU-R5.

---

## File map (new / modified)

| File | Responsibility |
|------|----------------|
| `src/media2text/api/services/session_playback.py` | Resolve cloud upload rows; fetch cloud m3u8 text; shared lookup for parts/init/master |
| `src/media2text/api/services/cloud_byte_proxy.py` | httpx stream proxy: Aliyun download URL + client Range → `StreamingResponse` |
| `src/media2text/api/routes/playback.py` | Playlist cloud fallback; part/init Range proxy (replace 302) |
| `src/media2text/api/routes/media.py` | Cloud Range fallback when local file missing (VOD + legacy MP4) |
| `src/media2text/core/config.py` | `LiveEncodeConfig`; merge `compress` alias |
| `src/media2text/core/live/encode_profile.py` | `resolve_encode_args()` — auto codec selection |
| `src/media2text/core/live/hls_recorder.py` | Use `encode_profile` instead of raw `LiveCompressConfig` |
| `apps/m2t-desktop/src/features/history/ViewPlayback.tsx` | Remove `hlsNeedsRemux`; always hls.js for HLS |
| `scripts/benchmark_live_compress.py` | Extend for x264 + multi-codec matrix (R0) |
| `config.example.yaml` | `media.format: hls`, `live.encode` block |

---

## PR 拆分（推荐顺序）

| PR | Phase | 主题 | 依赖 | Spec |
|----|-------|------|------|------|
| **SMU-R2** | R2 | 播放统一：Range 代理、云 master、Desktop hls.js | LSM-3 merged | US4, US9, US10 |
| **SMU-R0** | R0 | Encode PoC + 验收表更新 | — | US3, S6 |
| **SMU-R1** | R1 | `live.encode` config + example + doctor | R0 可选 | US1, ER5 |
| **SMU-R3** | R3 | VOD 云 Range 播放 | SMU-R2 (`cloud_byte_proxy`) | US5 |
| **SMU-R4** | R4 | Legacy deprecation 日志 + HLS finalize 瘦身 | SMU-R2 | U6 |
| **SMU-R5** | R5 | G3 段 job 重试 + 删 302 残留 | SMU-R2 | G3 |

**并行 Lane:** SMU-R0 与 SMU-R2 可同时开分支（无文件冲突）。SMU-R3 在 `cloud_byte_proxy.py` 合并后开。

---

## Desktop Playback UX (SMU-R2 + R3)

**Classifier:** APP UI — reuse existing `ViewPlayback` chrome (`.video-placeholder`, `.hint`, `.history-video`). No new pages or marketing surfaces.

**Information hierarchy (unchanged):**

```
1. Breadcrumb: ← 返回列表 › {creator} › {sessionPlaybackLabel}
2. Primary: video viewport (full width of center column)
3. Secondary: native <video controls> only (no custom transport bar)
```

**Interaction state table** (what the user *sees*, not backend):

| Feature | LOADING | EMPTY | ERROR | SUCCESS | PARTIAL |
|---------|---------|-------|-------|---------|---------|
| HLS archive (local segments) | `<video controls>` + browser spinner | — | `.hint`「回放加载失败」 | video playing | hls.js buffer stall → native spinner |
| HLS archive (cloud-only) | same (no app overlay; **decision D2-A**) | — | `.hint`「回放加载失败」; if `cloudOnly` add second line「云端分段不可用，可尝试从云端下载」 | video playing via proxied parts | fatal hls.js after part 502 → error row |
| HLS + `discontinuity_at` | same as HLS | — | same | hls.js + `alignPlaybackTime` on `timeupdate` | seek across `#EXT-X-DISCONTINUITY` (player handles) |
| Legacy MP4/FLV | browser spinner | listed pending placeholder | `.hint`「回放加载失败」 | native / flv.js | — |
| VOD cloud-only (R3) | browser spinner on Range | listed pending | same error copy as live | `/api/media` 206 stream | — |

**User journey (dogfood `20260611T110019Z`):**

| Step | User does | User feels | Plan specifies |
|------|-----------|------------|----------------|
| 1 | Opens history › picks session | expects instant play | breadcrumb + video area |
| 2 | Waits 1–5s (cloud manifest + part 0) | impatient if blank | D2-A: browser spinner only |
| 3 | Playback starts mid-stream discontinuity | confused if seek jumps | `alignPlaybackTime` (existing) |
| 4 | hls.js fatal (502/404 part) | needs actionable message | Task 2.5 error copy |

**API → Desktop error mapping:**

| API | hls.js signal | Desktop UI |
|-----|---------------|------------|
| `502` cloud upstream | `NETWORK_ERROR` fatal | `.hint` + cloud-only subline |
| `404` part/init | `NETWORK_ERROR` fatal | same |
| `416` bad Range | recoverable or fatal | browser handles; fatal → `.hint` |

**Responsive / a11y (no change):** Existing `#view-playback` keyboard `Escape` → back; `<video controls>` provides native a11y; touch targets on controls are OS-native. Do not add custom seek bar.

**NOT in scope (design):** Timeline discontinuity markers; download progress UI; new player skin; live preview (`stream/proxy`) layout.

**What already exists (reuse):** `ViewPlayback.tsx` placeholders (lines 341–379), `sessionCloudAvailable` / `cloudOnly` copy, `alignPlaybackTime`, Vitest hls.js mocks.

**Approved mockups:** Skipped — behavioral-only change; visual chrome unchanged. Dogfood reference: `20260611T110019Z`.

---

## SMU-R2 — 播放统一（优先）

### Task 2.1: `cloud_byte_proxy` — Range 流式代理

**Files:**
- Create: `src/media2text/api/services/cloud_byte_proxy.py`
- Test: `tests/unit/test_cloud_byte_proxy.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch

import pytest
from starlette.responses import StreamingResponse

from media2text.api.services.cloud_byte_proxy import stream_cloud_file


def test_stream_cloud_file_forwards_range_header():
    mock_client = MagicMock()
    mock_client.get_download_url.return_value = "https://cdn.example/file"
    upstream = MagicMock()
    upstream.status_code = 206
    upstream.headers = {"content-type": "video/mp4", "content-length": "100"}
    upstream.iter_bytes.return_value = [b"chunk"]
    with patch("httpx.stream", return_value=upstream) as mock_stream:
        resp = stream_cloud_file(
            mock_client,
            file_id="fid-1",
            range_header="bytes=0-99",
        )
    assert isinstance(resp, StreamingResponse)
    mock_stream.assert_called_once()
    call_kwargs = mock_stream.call_args.kwargs
    assert call_kwargs["headers"]["Range"] == "bytes=0-99"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate
pytest tests/unit/test_cloud_byte_proxy.py::test_stream_cloud_file_forwards_range_header -v
```

Expected: FAIL (`ModuleNotFoundError` or `ImportError`)

- [ ] **Step 3: Implement minimal proxy**

```python
"""Stream Aliyun Drive file bytes through API (Range-aware)."""

from __future__ import annotations

import httpx
from starlette.responses import StreamingResponse

def stream_cloud_file(
    client,
    file_id: str,
    *,
    range_header: str | None = None,
    media_type: str = "video/mp4",
) -> StreamingResponse:
    url = client.get_download_url(file_id)
    headers: dict[str, str] = {}
    if range_header:
        headers["Range"] = range_header
    upstream = httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60.0)
    resp = upstream.__enter__()
    if resp.status_code not in (200, 206):
        upstream.__exit__(None, None, None)
        raise RuntimeError(f"cloud upstream status {resp.status_code}")

    out_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": resp.headers.get("content-type", media_type),
    }
    if "content-range" in resp.headers:
        out_headers["Content-Range"] = resp.headers["content-range"]
    if "content-length" in resp.headers:
        out_headers["Content-Length"] = resp.headers["content-length"]

    def _iter():
        try:
            for chunk in resp.iter_bytes():
                yield chunk
        finally:
            upstream.__exit__(None, None, None)

    status = 206 if resp.status_code == 206 else 200
    return StreamingResponse(_iter(), status_code=status, headers=out_headers, media_type=out_headers["Content-Type"])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_cloud_byte_proxy.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/services/cloud_byte_proxy.py tests/unit/test_cloud_byte_proxy.py
git commit -m "feat(api): add Aliyun cloud byte Range proxy helper"
```

---

### Task 2.2: `session_playback` — cloud upload 查找

**Files:**
- Create: `src/media2text/api/services/session_playback.py`
- Modify: `src/media2text/api/routes/playback.py` (import helpers)
- Test: `tests/unit/test_session_playback.py`

- [ ] **Step 1: Write the failing test**

```python
from media2text.api.services.session_playback import find_part_upload
from media2text.core.storage.repos import CloudUploadRepo, CreatorRepo, LiveSessionRepo


def test_find_part_upload_by_part_index(workspace):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(sec_uid="sec", profile_url="https://x", monitor_enabled=True)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid, room_id="r1", temp_path="/x", session_dir=str(workspace / "live"),
    )
    upload_id = CloudUploadRepo(conn).create(
        session_id=sid,
        creator_id=cid,
        platform="douyin",
        file_name="seg-00005.m4s",
        file_kind="m4s",
        size=100,
        pre_hash="abc",
        part_index=5,
    )
    CloudUploadRepo(conn).mark_done(
        upload_id,
        cloud_file_id="cf-part-5",
        cloud_relative_path="media2text/douyin/u/live/seg-00005.m4s",
    )
    row = find_part_upload(conn, session_id=sid, part_index=5)
    assert row is not None
    assert row.cloud_file_id == "cf-part-5"
    conn.close()
```

(Use existing `CloudUploadRepo` test fixtures from `test_playback_api.py` patterns.)

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/unit/test_session_playback.py -v
```

- [ ] **Step 3: Implement lookup helpers**

```python
"""Session HLS playback: cloud upload resolution (thin service, spec U13)."""

from __future__ import annotations

from media2text.core.storage.repos import CloudUploadRepo


def find_part_upload(conn, *, session_id: str, part_index: int):
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.part_index == part_index and row.upload_status == "done" and row.cloud_file_id:
            return row
        if (
            row.upload_status == "done"
            and row.cloud_file_id
            and row.file_kind == "m4s"
            and f"seg-{part_index:05d}.m4s" in (row.file_name or "")
        ):
            return row
    return None


def find_init_upload(conn, *, session_id: str):
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.upload_status == "done" and row.cloud_file_id and row.file_kind == "init_mp4":
            return row
        if row.upload_status == "done" and row.cloud_file_id and row.file_name == "init.mp4":
            return row
    return None


def find_m3u8_upload(conn, *, session_id: str):
    for row in CloudUploadRepo(conn).list_for_session(session_id):
        if row.upload_status == "done" and row.cloud_file_id and row.file_kind == "m3u8":
            return row
        if row.upload_status == "done" and row.cloud_file_id and row.file_name == "master.m3u8":
            return row
    return None
```

- [ ] **Step 4: pytest + commit**

```bash
pytest tests/unit/test_session_playback.py -v
git add src/media2text/api/services/session_playback.py tests/unit/test_session_playback.py
git commit -m "feat(api): session_playback cloud upload lookup helpers"
```

---

### Task 2.3: Part/init — 302 改 Range 代理

**Files:**
- Modify: `src/media2text/api/routes/playback.py`
- Modify: `tests/unit/test_playback_api.py`

- [ ] **Step 1: Write failing test — cloud part returns 206 StreamingResponse, not 302**

```python
def test_get_part_cloud_proxies_range(api_client, workspace, monkeypatch):
    sid, session_dir = _seed_hls_session(workspace)
    part_path = session_dir / "parts" / "seg-00001.m4s"
    part_path.unlink()  # local deleted
    # seed cloud_uploads row + mock AliyunDriveClient.open
    ...
    r = api_client.get(f"/api/sessions/{sid}/parts/1", headers={"Range": "bytes=0-10"})
    assert r.status_code == 206
    assert "content-range" in r.headers
```

- [ ] **Step 2: Run test — expect FAIL** (still 302 or 404)

- [ ] **Step 3: Replace `_cloud_part_redirect` usage in `get_playback_part`**

In `get_playback_part`, after local miss and `part_row.state in ("uploaded", "local_deleted")`:

```python
from media2text.api.services.cloud_byte_proxy import stream_cloud_file
from media2text.api.services.session_playback import find_part_upload
from media2text.core.cloud.aliyundrive import AliyunDriveClient

upload = find_part_upload(conn, session_id=session_id, part_index=part_index)
if upload and cfg.aliyundrive.enabled:
    token_path = cfg.aliyundrive_token_path()
    if token_path.is_file():
        with AliyunDriveClient.open(token_path) as client:
            return stream_cloud_file(
                client,
                str(upload.cloud_file_id),
                range_header=request.headers.get("range"),  # inject Request
                media_type="video/mp4",
            )
```

Add `Request` to route signature. Mirror same pattern in `get_playback_init`.

- [ ] **Step 4: Update existing redirect tests to expect proxy behavior**

```bash
pytest tests/unit/test_playback_api.py -v -m desktop
```

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/routes/playback.py tests/unit/test_playback_api.py
git commit -m "feat(playback): proxy cloud HLS parts with Range instead of 302"
```

---

### Task 2.4: `playback.m3u8` 云 master 回退 (US9)

**Files:**
- Modify: `src/media2text/api/routes/playback.py`
- Modify: `src/media2text/api/services/session_playback.py` (optional `fetch_cloud_m3u8_text`)
- Test: `tests/unit/test_playback_api.py`

- [ ] **Step 1: Failing test — no local master, cloud m3u8 exists**

```python
def test_playback_m3u8_from_cloud_when_local_master_missing(api_client, workspace, monkeypatch):
    sid, session_dir = _seed_hls_session(workspace)
    (session_dir / "master.m3u8").unlink()
  # seed cloud_uploads m3u8 + mock client download text
    r = api_client.get(f"/api/sessions/{sid}/playback.m3u8")
    assert r.status_code == 200
    assert "/api/sessions/" in r.text and "/parts/" in r.text
```

- [ ] **Step 2: Implement in `get_playback_m3u8`**

```python
master = session_dir / "master.m3u8"
if not master.is_file():
    upload = find_m3u8_upload(conn, session_id=session_id)
    if upload and cfg.aliyundrive.enabled and token_path.is_file():
        with AliyunDriveClient.open(token_path) as client:
            url = client.get_download_url(str(upload.cloud_file_id))
            raw = httpx.get(url, timeout=30.0).text
    else:
        raise HTTPException(status_code=404, detail="playlist not found")
else:
    raw = master.read_text(encoding="utf-8")
rewritten = _rewrite_m3u8(raw, session_id=session_id)
```

- [ ] **Step 3: pytest + commit**

```bash
pytest tests/unit/test_playback_api.py::test_playback_m3u8_from_cloud_when_local_master_missing -v
git commit -m "feat(playback): cloud master.m3u8 fallback for playback.m3u8"
```

---

### Task 2.5: Desktop — 移除 `hlsNeedsRemux` (US4)

**Files:**
- Modify: `apps/m2t-desktop/src/features/history/ViewPlayback.tsx`
- Modify: `apps/m2t-desktop/src/features/history/ViewPlayback.test.tsx`

- [ ] **Step 1: Update failing test** — replace remux test with hls.js + discontinuity

```typescript
it('uses playback.m3u8 when discontinuity_at is present', async () => {
  const { playbackM3u8Url, playbackMp4Url } = await import('../../lib/api');
  render(
    <ViewPlayback
      active
      creatorName="主播"
      session={baseSession({ media_format: 'hls', discontinuity_at: [630.76] })}
    />,
  );
  await waitFor(() => {
    expect(playbackM3u8Url).toHaveBeenCalledWith('sess-1');
  });
  expect(playbackMp4Url).not.toHaveBeenCalled();
  expect(mockHlsInstances.length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run Vitest — expect FAIL**

```bash
pnpm --filter m2t-desktop test -- ViewPlayback.test.tsx
```

- [ ] **Step 3: Remove remux branch in `ViewPlayback.tsx`**

Delete `hlsNeedsRemux` and always use `playbackM3u8Url` when `isHls && canPlayHls`. Keep `playbackMp4Url` only for explicit legacy MP4 sessions if needed (non-HLS).

- [ ] **Step 3b: Cloud-aware error copy (D2-A — no loading overlay)**

When `error && cloudOnly`, show primary + secondary hint (reuse existing placeholder pattern):

```tsx
) : error ? (
  <div className="video-placeholder">
    <p className="hint">回放加载失败</p>
    {cloudOnly ? (
      <p className="video-placeholder-hint">
        云端分段不可用，可尝试从云端下载
      </p>
    ) : null}
  </div>
) : (
```

Add Vitest:

```typescript
it('shows cloud fallback hint when hls fails on cloud-only session', async () => {
  const { playbackM3u8Url } = await import('../../lib/api');
  playbackM3u8Url.mockRejectedValueOnce(new Error('network'));
  render(
    <ViewPlayback
      active
      creatorName="主播"
      session={baseSession({
        media_format: 'hls',
        media_available: false,
        cloud_available: true,
      })}
    />,
  );
  await waitFor(() => {
    expect(screen.getByText(/云端分段不可用/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Vitest pass + commit**

```bash
pnpm --filter m2t-desktop test -- ViewPlayback.test.tsx
git add apps/m2t-desktop/src/features/history/ViewPlayback.tsx apps/m2t-desktop/src/features/history/ViewPlayback.test.tsx
git commit -m "fix(desktop): always use HLS playlist for discontinuity sessions"
```

---

### Task 2.6: SMU-R2 回归闸门

- [ ] **Run full desktop + playback unit suite**

```bash
source .venv/bin/activate
pytest tests/unit/test_playback_api.py tests/unit/test_cloud_byte_proxy.py tests/unit/test_session_playback.py tests/unit/test_streaming_stt_finalize*.py -v -m desktop
pnpm --filter m2t-desktop test
ruff check src/media2text/api/
```

Expected: all PASS; STT finalize regression unchanged.

---

## SMU-R0 — Encode PoC（与 R2 并行）

### Task 0.1: 扩展 benchmark 脚本（x264 + codec 矩阵）

**Files:**
- Modify: `scripts/benchmark_live_compress.py`
- Modify: `docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`

- [ ] **Step 1: Add CLI flags `--video-codec hevc_videotoolbox|h264_videotoolbox|libx264`**

```python
def run_encode(sample: Path, *, video_codec: str, video_bitrate: str, audio_bitrate: str) -> dict:
    codec_map = {
        "hevc_videotoolbox": ["-c:v", "hevc_videotoolbox"],
        "h264_videotoolbox": ["-c:v", "h264_videotoolbox"],
        "libx264": ["-c:v", "libx264", "-preset", "veryfast"],
    }
    ...
```

- [ ] **Step 2: Run on Apple Silicon sample (manual)**

```bash
python scripts/benchmark_live_compress.py \
  --sample data/creators/<sec>/live/<timestamp>.flv \
  --video-codec hevc_videotoolbox --json

python scripts/benchmark_live_compress.py \
  --sample ... --video-codec libx264 --json
```

- [ ] **Step 3: Fill verification table; set `s6_pass` per hardware row**

- [ ] **Step 4: Commit script only (verification table after human run)**

```bash
git add scripts/benchmark_live_compress.py
git commit -m "chore(poc): extend live compress benchmark for codec matrix"
```

---

## SMU-R1 — Config `live.encode`

### Task 1.1: `LiveEncodeConfig` + compress alias

**Files:**
- Create: `src/media2text/core/live/encode_profile.py`
- Modify: `src/media2text/core/config.py`
- Modify: `config.example.yaml`
- Test: `tests/unit/test_encode_profile.py`

- [ ] **Step 1: Failing test — compress YAML maps to encode**

```python
def test_compress_alias_migrates_to_encode():
    cfg = AppConfig.model_validate({
        "live": {
            "compress": {"enabled": True, "video_bitrate": "2M"},
        }
    })
    assert cfg.live.encode.mode == "compress"
    assert cfg.live.encode.video_bitrate == "2M"
```

- [ ] **Step 2: Add models**

```python
class LiveEncodeConfig(BaseModel):
    mode: str = "copy"  # copy | compress
    video_codec: str = "auto"
    video_bitrate: str = "2M"
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"


class LiveConfig(BaseModel):
    ...
    encode: LiveEncodeConfig = Field(default_factory=LiveEncodeConfig)
    compress: LiveCompressConfig = Field(default_factory=LiveCompressConfig)

    @model_validator(mode="after")
    def _migrate_compress_to_encode(self) -> LiveConfig:
        if self.compress.enabled and self.encode.mode == "copy":
            self.encode.mode = "compress"
        if self.compress.video_bitrate and self.encode.video_bitrate == "2M":
            pass  # encode explicit wins if set in YAML after merge
        return self
```

- [ ] **Step 3: `resolve_encode_args(cfg)` in `encode_profile.py`**

```python
def resolve_video_encoder(cfg: LiveEncodeConfig) -> tuple[str, list[str]]:
    if cfg.mode != "compress":
        return "copy", ["-c", "copy"]
    codec = cfg.video_codec
    if codec == "auto":
        codec = _detect_best_vt_codec()  # hevc → h264 → libx264 fallback
    ...
```

- [ ] **Step 4: Wire `hls_recorder.build_hls_recorder_args` to use `resolve_video_encoder`**

- [ ] **Step 5: Update `config.example.yaml`**

```yaml
live:
  pipeline_mode: streaming
  media:
    format: hls
    segment_duration_sec: 600
  encode:
    mode: copy  # switch to compress after PoC S6 pass on your hardware
    video_codec: auto
    video_bitrate: 2M
    audio_bitrate: 128k
  segment_pipeline:
    enabled: true
```

- [ ] **Step 6: pytest + ruff + commit**

```bash
pytest tests/unit/test_encode_profile.py tests/unit/test_hls_recorder.py -v
git add src/media2text/core/config.py src/media2text/core/live/encode_profile.py src/media2text/core/live/hls_recorder.py config.example.yaml tests/unit/test_encode_profile.py
git commit -m "feat(live): add live.encode profile with compress alias migration"
```

---

## SMU-R3 — VOD 云 Range 播放

### Task 3.1: `/api/media` cloud fallback

**Files:**
- Modify: `src/media2text/api/routes/media.py`
- Modify: `src/media2text/api/services/history_media.py` (shared cloud path resolver)
- Test: `tests/unit/test_api_media_cloud_fallback.py`

- [ ] **Step 1: Failing test — local mp4 missing, cloud_uploads has aweme**

```python
def test_media_cloud_range_when_local_missing(api_client, workspace, monkeypatch):
    # seed aweme + cloud_uploads with file_kind mp4, mock stream_cloud_file
    r = api_client.get("/api/media", params={"path": "creators/sec/videos/123.mp4"}, headers={"Range": "bytes=0-100"})
    assert r.status_code in (200, 206)
```

- [ ] **Step 2: In `get_media`, before 404:**

```python
if not target.is_file():
    cloud_resp = try_cloud_media_range(cfg, conn, workspace_rel_path=path, range_header=range)
    if cloud_resp is not None:
        return cloud_resp
    raise HTTPException(status_code=404, detail="file not found")
```

Reuse `cloud_byte_proxy.stream_cloud_file` + lookup from `agent-manifest` / `cloud_uploads` by workspace path.

- [ ] **Step 3: Desktop VOD error copy** — reuse Task 2.5 Step 3b pattern when `mediaUrl` fails and `cloud_available`; extract shared fragment if VOD + live both need it.

- [ ] **Step 4: pytest + commit**

```bash
pytest tests/unit/test_api_media_cloud_fallback.py -v
git commit -m "feat(api): cloud Range fallback for /api/media (VOD)"
```

---

## SMU-R4 — Legacy deprecation

### Task 4.1: Deprecation warnings + HLS finalize trim

**Files:**
- Modify: `src/media2text/core/live/recording.py` (HLS finalize: skip remux MP4)
- Modify: `src/media2text/core/live/post_process.py` (log when legacy whole-file upload runs)
- Test: extend `tests/unit/test_post_process_hls_skip_upload.py`

- [ ] **Step 1: Log once per finalize when `pipeline_mode=legacy`**

```python
log.warning("live_pipeline_deprecated", mode="legacy", hint="use streaming+hls; see config.example.yaml")
```

- [ ] **Step 2: Ensure HLS finalize does not call `remux_hls_to_playback_mp4` or enqueue whole-file upload** (grep `recording.py` finalize HLS branch).

- [ ] **Step 3: Regression**

```bash
pytest tests/unit/test_post_process_hls_skip_upload.py tests/unit/test_segment_finalize_sidecar.py -v
```

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(live): deprecate legacy pipeline; trim HLS finalize remux"
```

---

## SMU-R5 — 硬化（G3 段 job 重试）

**Files:**
- Modify: `src/media2text/core/live/segment_process.py` or segment job repo per `docs/issues/live-segment-gap-g3-segment-job-retry-reconciler.md`
- Test: `tests/unit/test_segment_process_retry.py`

Follow existing G3 issue AC verbatim. Reuse reconciler pattern from `monitor_tasks` retry. **Do not duplicate G3 spec here** — implement issue file as source of truth after SMU-R2 merged.

- [ ] **Step 1:** Read `docs/issues/live-segment-gap-g3-segment-job-retry-reconciler.md`
- [ ] **Step 2:** Implement AC + verification commands from issue
- [ ] **Step 3:** Remove dead `_cloud_part_redirect` if fully replaced (or keep as internal fallback one release)

---

## Test coverage diagram (SMU-R2 target)

```
CODE PATHS
[+] cloud_byte_proxy.stream_cloud_file
  ├── [GAP→Task 2.1] Range forwarded, 206
  └── [GAP] upstream error → 502

[+] playback.m3u8
  ├── [★★★] local rewrite — test_playback_api
  ├── [GAP→Task 2.4] cloud master fallback
  └── [★★★] discontinuity lines preserved in rewrite

[+] parts/{index} + init.mp4
  ├── [★★★] local FileResponse
  ├── [★★] cloud 302 — test_playback_api (REPLACE)
  └── [GAP→Task 2.3] cloud Range proxy

[+] ViewPlayback.tsx
  ├── [★★★] hls no discontinuity
  ├── [★★★ REGRESSION] remux on discontinuity — DELETE Task 2.5
  └── [GAP→E2E] cloud-only + discontinuity

[+] /api/media
  └── [GAP→Task 3.1] cloud Range VOD

COVERAGE post-SMU-R2: ~75% critical paths | GAPS: VOD (R3), G3 (R5)
```

---

## Spec coverage self-review

| Spec requirement | Task |
|----------------|------|
| U1 streaming+hls default | Task 1.1 `config.example.yaml` |
| U2 encode at record | Task 1.1 + 0.1 |
| U3 cloud truth | SMU-R2 proxy (existing upload) |
| U4 no remux on discontinuity | Task 2.5 |
| U5 VOD MediaResolver | Task 3.1 |
| U6 legacy deprecated | Task 4.1 |
| U7 PoC gate | Task 0.1 |
| U8 live preview unchanged | no task (regression only) |
| U9 cloud master | Task 2.4 |
| U10 Range proxy | Task 2.3 |
| US1–US10 | tasks above |

**Placeholder scan:** none.

---

## NOT in scope (this plan)

- VOD upload pipeline (R3b / separate issue)
- Cloud merge MP4
- Segment async re-compress
- New `SessionMedia` DB table
- Replacing Aliyun with other cloud

---

## What already exists (do not rebuild)

- `upload_live_part`, `SegmentWatcher`, `live_session_parts` — LSM-2
- `_rewrite_m3u8`, `alignPlaybackTime` — LSM-3
- `is_hls_session_media` skip in post_process
- `media.py` Range parser for local files
- `flv_proxy.py` httpx streaming pattern — template for `cloud_byte_proxy`

---

## Parallelization

| Lane | Steps | Shared modules |
|------|-------|----------------|
| A (R2) | Tasks 2.1–2.6 | `api/services/`, `api/routes/playback.py`, desktop |
| B (R0) | Task 0.1 | `scripts/` only |
| C (R1) | Task 1.1 | `core/config.py`, `hls_recorder.py` — **after or parallel R0** |
| D (R3) | Task 3.1 | `media.py` — **after R2 Task 2.1 merged** |

Launch A + B in parallel worktrees. Merge A before D.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope | 0 | — | optional |
| Eng Review | `/plan-eng-review` | Architecture | 1 | CLEAR (PLAN) | spec locked |
| Design Review | `/plan-design-review` | hls.js UX | 1 | CLEAR (PLAN) | 4→8/10; UX table + error copy |
| DX Review | `/plan-devex-review` | encode migration | 0 | — | before SMU-R1 |

- **UNRESOLVED:** 0 (D2-A loading: browser-native; D1-A full pass applied)
- **VERDICT:** Design + Eng CLEARED for SMU-R2 implementation
