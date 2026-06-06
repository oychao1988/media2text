# m2t-desktop Agent Pane & Layout Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Cursor-style Agent pane (multi-tab + global history sidebar), three desktop layout presets (`full` / `transcript-chat` / `chat-only`), transcript session dropdown, and P0 backend history transcript/summary APIs per [spec](../specs/2026-06-06-m2t-desktop-agent-pane-design.md).

**Architecture:** Four incremental PRs: (1) Python history content service + routes + `display_label`; (2) Node sidecar `context.refresh` path/kind extension; (3) React layout presets + `TranscriptSelection` + conditional `TranscriptPane` slot; (4) Agent multi-thread UI with hook split. Locked decisions D1–D4 from spec §1.3.

**Tech Stack:** Python 3.12+ (FastAPI, pytest), Node 20+ (`m2t-agent-sidecar`), React 18 + Vitest, Tauri 2, existing `media2text.api` + `DesktopChatRepo`.

**Spec:** [2026-06-06-m2t-desktop-agent-pane-design.md](../specs/2026-06-06-m2t-desktop-agent-pane-design.md) · Prototype: [finalized.html](../designs/m2t-desktop/finalized.html)

**PR slices (merge order):** `feat/desktop-history-api` → `feat/agent-sidecar-context` → `feat/desktop-layout-presets` → `feat/agent-multi-thread-ui`

---

## Data flow (ASCII)

```
TranscriptSessionSelect
  └─► useLayoutStore.transcriptSelection
        └─► TranscriptPane
              ├─ mode=live  → GET/WS /api/sessions/{uuid}/transcript
              └─ mode=history
                    ├─ kind=live → GET .../history/live/{uuid}/transcript
                    └─ kind=vod  → GET .../history/vod/{aweme_id}/transcript

AgentHistorySidebar
  └─► GET /api/chat/threads (no filter)
        └─► useM2tAgent(activeThreadId)
              └─► sendAgentContextRefresh({ paths, sessionKind, contextMode })
                    └─► sidecar hydrateContextFromApi (paths first)
```

---

## File map

| Path | Responsibility |
|------|----------------|
| `src/media2text/api/services/history_content.py` | **Create** — resolve live/vod media + read transcript/summary (shared by routes) |
| `src/media2text/api/routes/creators.py` | **Modify** — `GET .../history/{kind}/{item_id}/transcript\|summary` |
| `src/media2text/api/services/sessions_list.py` | **Modify** — `display_label` on live items |
| `tests/unit/test_api_history_transcript.py` | **Create** — P0-A regression tests |
| `tests/unit/test_api_sessions_list.py` | **Modify** — assert `display_label` |
| `packages/m2t-agent-sidecar/src/context.ts` | **Modify** — extended refresh fields; path-first hydrate |
| `packages/m2t-agent-sidecar/src/main.ts` | **Modify** — parse refresh payload env + paths |
| `packages/m2t-agent-sidecar/src/context.test.ts` | **Create** — hydrate with paths, no session GET for vod |
| `apps/m2t-desktop/src/features/layout/layoutConstants.ts` | **Modify** — `desktopLayoutPreset`, `agentHistoryW`, persist |
| `apps/m2t-desktop/src/features/layout/useLayoutStore.ts` | **Modify** — preset + `TranscriptSelection` |
| `apps/m2t-desktop/src/features/layout/DesktopLayoutPresets.tsx` | **Create** — three preset buttons |
| `apps/m2t-desktop/src/features/layout/useAgentHistoryResize.ts` | **Create** — `--agent-history-w` drag |
| `apps/m2t-desktop/src/features/transcript/TranscriptSessionSelect.tsx` | **Create** — session dropdown |
| `apps/m2t-desktop/src/features/transcript/transcriptSelection.ts` | **Create** — types + helpers |
| `apps/m2t-desktop/src/features/transcript/TranscriptPane.tsx` | **Modify** — history API fetch paths |
| `apps/m2t-desktop/src/features/layout/AppShell.tsx` | **Modify** — conditional TranscriptPane slot, grid classes |
| `apps/m2t-desktop/src/features/layout/useColumnResize.ts` | **Modify** — 3-column clamp for `transcript-chat` |
| `apps/m2t-desktop/src/features/agent/useAgentThreads.ts` | **Create** — global thread CRUD |
| `apps/m2t-desktop/src/features/agent/useAgentTabs.ts` | **Create** — max-5 tab bar state |
| `apps/m2t-desktop/src/features/agent/AgentTabsBar.tsx` | **Create** |
| `apps/m2t-desktop/src/features/agent/AgentHistorySidebar.tsx` | **Create** |
| `apps/m2t-desktop/src/features/agent/AgentThreadContextMenu.tsx` | **Create** |
| `apps/m2t-desktop/src/features/agent/AgentPanel.tsx` | **Modify** — remove `.agent-header`, wire new hooks |
| `apps/m2t-desktop/src/features/agent/useM2tAgent.ts` | **Modify** — per-`threadId`, global threads |
| `apps/m2t-desktop/src/features/agent/agentSidecar.ts` | **Modify** — extended `AgentContext` |
| `apps/m2t-desktop/src/features/agent/*.test.ts(x)` | **Create/Modify** — tabs, threads, sidecar refresh |

---

## PR 1 — Backend P0 (history API + display_label)

### Task 1: `history_content` service — resolve media paths

**Files:**
- Create: `src/media2text/api/services/history_content.py`
- Test: `tests/unit/test_history_content.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_history_content.py
import json

import pytest
from fastapi import HTTPException

from media2text.api.services.history_content import (
    read_history_summary,
    read_history_transcript,
    resolve_history_media_path,
)
from media2text.core.config import AppConfig
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def test_resolve_live_media_path(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_hc",
        profile_url="https://www.douyin.com/user/sec_hc",
        platform="douyin",
    )
    live_dir = workspace / "creators" / "sec_hc" / "live"
    live_dir.mkdir(parents=True)
    flv = live_dir / "20260604T100000Z.flv"
    flv.write_bytes(b"x")
    sid = LiveSessionRepo(conn).create(creator_id=cid, room_id="r", temp_path=str(flv))

    media = resolve_history_media_path(conn, workspace=workspace, creator_id=cid, kind="live", item_id=sid)
    conn.close()
    assert media is not None
    assert media.name.endswith(".flv")


def test_read_history_transcript_vod(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_vod",
        profile_url="https://www.douyin.com/user/sec_vod",
        platform="douyin",
    )
    vid_dir = workspace / "creators" / "sec_vod" / "videos"
    vid_dir.mkdir(parents=True)
    mp4 = vid_dir / "7123456789.mp4"
    mp4.write_bytes(b"mp4")
    transcript = mp4.with_suffix(".transcript.json")
    transcript.write_text(json.dumps({"text": "hello", "segments": []}), encoding="utf-8")
    AwemeRepo(conn).upsert_listed(
        creator_id=cid,
        item=AwemeItem(
            aweme_id="7123456789",
            title="测试作品",
            create_time=1_700_000_000,
            media_type="video",
        ),
    )
    conn.execute(
        "UPDATE awemes SET local_path = ?, sync_status = 'downloaded' WHERE aweme_id = ?",
        (str(mp4.resolve()), "7123456789"),
    )
    conn.commit()

    payload = read_history_transcript(
        conn, workspace=workspace, creator_id=cid, kind="vod", item_id="7123456789"
    )
    conn.close()
    assert payload["text"] == "hello"
    assert payload["partial"] is False


def test_read_history_transcript_not_found(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_nf",
        profile_url="https://www.douyin.com/user/sec_nf",
        platform="douyin",
    )
    with pytest.raises(HTTPException) as exc:
        read_history_transcript(
            conn, workspace=workspace, creator_id=cid, kind="vod", item_id="missing"
        )
    conn.close()
    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/unit/test_history_content.py -v`  
Expected: FAIL (`ModuleNotFoundError: history_content`)

- [ ] **Step 3: Write minimal implementation**

```python
# src/media2text/api/services/history_content.py
"""Resolve creator history items and read transcript/summary sidecars."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException

from media2text.api.security import safe_workspace_path, workspace_rel
from media2text.api.services.history_media import _resolve_media_path
from media2text.api.services.sessions_list import _load_manifest, _manifest_live_by_id, _manifest_vod_by_id
from media2text.api.services.transcript import read_summary_text, read_transcript_payload
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo

HistoryKind = Literal["live", "vod"]


def resolve_history_media_path(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
) -> Path | None:
    creator = CreatorRepo(conn).get(creator_id)
    if not creator:
        return None
    manifest = _load_manifest(workspace, creator.sec_uid)
    if kind == "live":
        session = LiveSessionRepo(conn).get(item_id)
        if not session or session.creator_id != creator_id:
            return None
        m_entry = _manifest_live_by_id(manifest).get(item_id)
        manifest_path = m_entry.get("media_path") if m_entry else None
        return _resolve_media_path(
            workspace,
            local_path=session.local_path,
            temp_path=session.temp_path,
            manifest_path=manifest_path,
        )
    aweme = AwemeRepo(conn).get(item_id)
    if not aweme or aweme.creator_id != creator_id:
        return None
    m_entry = _manifest_vod_by_id(manifest).get(item_id)
    manifest_path = m_entry.get("media_path") if m_entry else None
    return _resolve_media_path(workspace, local_path=aweme.local_path, manifest_path=manifest_path)


def read_history_transcript(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
) -> dict[str, Any]:
    media = resolve_history_media_path(
        conn, workspace=workspace, creator_id=creator_id, kind=kind, item_id=item_id
    )
    if media is None:
        raise HTTPException(status_code=404, detail="history item not found")
    try:
        return read_transcript_payload(media)
    except HTTPException:
        raise HTTPException(status_code=404, detail="transcript not found") from None


def read_history_summary(
    conn,
    *,
    workspace: Path,
    creator_id: str,
    kind: HistoryKind,
    item_id: str,
) -> dict[str, Any]:
    media = resolve_history_media_path(
        conn, workspace=workspace, creator_id=creator_id, kind=kind, item_id=item_id
    )
    if media is None:
        raise HTTPException(status_code=404, detail="history item not found")
    try:
        text = read_summary_text(media)
    except HTTPException:
        raise HTTPException(status_code=404, detail="summary not found") from None
    rel = workspace_rel(workspace, str(media.with_suffix(".summary.md")))
    return {"ok": True, "text": text, "summary_path": rel}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/unit/test_history_content.py -v`  
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/services/history_content.py tests/unit/test_history_content.py
git commit -m "feat(api): add history_content service for transcript/summary reads"
```

---

### Task 2: HTTP routes for history transcript/summary

**Files:**
- Modify: `src/media2text/api/routes/creators.py` (after existing `history/.../summarize` routes)
- Test: `tests/unit/test_api_history_transcript.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_api_history_transcript.py
import json

import pytest

from media2text.core.config import AppConfig
from media2text.core.platform.douyin.models import AwemeItem
from media2text.core.storage.repos import AwemeRepo, CreatorRepo, LiveSessionRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.desktop


def _seed_vod_with_transcript(workspace, api_client):
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_api_vod",
        profile_url="https://www.douyin.com/user/sec_api_vod",
        platform="douyin",
    )
    mp4 = workspace / "creators" / "sec_api_vod" / "videos" / "999.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"v")
    mp4.with_suffix(".transcript.json").write_text(
        json.dumps({"text": "vod text", "segments": []}), encoding="utf-8"
    )
    AwemeRepo(conn).upsert_listed(
        creator_id=cid,
        item=AwemeItem(
            aweme_id="999",
            title="VOD title",
            create_time=1_700_000_000,
            media_type="video",
        ),
    )
    conn.execute(
        "UPDATE awemes SET local_path = ?, sync_status = 'downloaded' WHERE aweme_id = ?",
        (str(mp4.resolve()), "999"),
    )
    conn.commit()
    conn.close()
    return cid


def test_history_vod_transcript(api_client, workspace) -> None:
    cid = _seed_vod_with_transcript(workspace, api_client)
    r = api_client.get(f"/api/creators/{cid}/history/vod/999/transcript")
    assert r.status_code == 200
    assert r.json()["text"] == "vod text"


def test_history_vod_transcript_404(api_client, workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_empty",
        profile_url="https://www.douyin.com/user/sec_empty",
        platform="douyin",
    )
    conn.close()
    r = api_client.get(f"/api/creators/{cid}/history/vod/nope/transcript")
    assert r.status_code == 404


def test_sessions_transcript_404_for_aweme_id(api_client, workspace) -> None:
    """REGRESSION: vod aweme_id must not use /api/sessions/{id}/transcript."""
    cid = _seed_vod_with_transcript(workspace, api_client)
    r = api_client.get("/api/sessions/999/transcript")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `source .venv/bin/activate && pytest tests/unit/test_api_history_transcript.py -v`  
Expected: FAIL (404 on history route or 200 on wrong sessions route)

- [ ] **Step 3: Add routes to creators.py**

```python
from media2text.api.services import history_content as history_content_svc

@router.get("/{creator_id}/history/{kind}/{item_id}/transcript")
def get_history_transcript(
    creator_id: str,
    kind: Literal["live", "vod"],
    item_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if kind not in ("live", "vod"):
        raise HTTPException(status_code=422, detail="kind must be live or vod")
    payload = history_content_svc.read_history_transcript(
        conn, workspace=cfg.ensure_workspace(), creator_id=creator_id, kind=kind, item_id=item_id
    )
    return {"ok": True, **payload}


@router.get("/{creator_id}/history/{kind}/{item_id}/summary")
def get_history_summary(
    creator_id: str,
    kind: Literal["live", "vod"],
    item_id: str,
    cfg: AppConfig = Depends(get_cfg),
    conn=Depends(get_db),
) -> dict:
    if kind not in ("live", "vod"):
        raise HTTPException(status_code=422, detail="kind must be live or vod")
    return history_content_svc.read_history_summary(
        conn, workspace=cfg.ensure_workspace(), creator_id=creator_id, kind=kind, item_id=item_id
    )
```

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && pytest tests/unit/test_api_history_transcript.py tests/unit/test_api_sessions.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/routes/creators.py tests/unit/test_api_history_transcript.py
git commit -m "feat(api): add history transcript/summary routes for live and vod"
```

---

### Task 3: `display_label` on live session list items

**Files:**
- Modify: `src/media2text/api/services/sessions_list.py` (`_build_live_item`, add `_format_live_display_label`)
- Test: `tests/unit/test_api_sessions_list.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_api_sessions_list.py`:

```python
def test_list_sessions_live_display_label(workspace) -> None:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="sec_label",
        profile_url="https://www.douyin.com/user/sec_label",
        platform="douyin",
    )
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="r",
        started_at="2026-06-02T13:04:00+00:00",
    )
    payload = list_creator_sessions(conn, workspace=workspace, creator_id=cid)
    conn.close()
    live = next(s for s in payload["sessions"] if s["item_id"] == sid)
    assert live["display_label"]
    assert "直播" in live["display_label"]
```

- [ ] **Step 2: Run — expect FAIL**

Run: `source .venv/bin/activate && pytest tests/unit/test_api_sessions_list.py::test_list_sessions_live_display_label -v`  
Expected: FAIL (`KeyError: display_label`)

- [ ] **Step 3: Implement label helper**

```python
def _format_live_display_label(started_at: str | None) -> str:
    if not started_at:
        return "直播"
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        local = dt.astimezone()
        return f"{local.strftime('%Y-%m-%d %H:%M')} 直播"
    except ValueError:
        return "直播"
```

Add `"display_label": _format_live_display_label(data.get("started_at")),` to `_build_live_item` return dict. VOD items: set `"display_label": row.title or row.aweme_id`.

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && pytest tests/unit/test_api_sessions_list.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/api/services/sessions_list.py tests/unit/test_api_sessions_list.py
git commit -m "feat(api): add display_label to creator session list items"
```

---

## PR 2 — Sidecar context.refresh (D2)

### Task 4: Extend sidecar context hydration

**Files:**
- Modify: `packages/m2t-agent-sidecar/src/context.ts`
- Modify: `packages/m2t-agent-sidecar/src/main.ts`
- Create: `packages/m2t-agent-sidecar/src/context.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// packages/m2t-agent-sidecar/src/context.test.ts
import { describe, expect, it, vi } from 'vitest';
import { applyRefreshPayload, hydrateContextFromApi, type RuntimeContext } from './context.js';

describe('applyRefreshPayload', () => {
  it('sets paths and skips session GET when transcriptPath provided', async () => {
    const ctx: RuntimeContext = {
      apiBaseUrl: 'http://127.0.0.1:8765',
      workspace: './data',
      creatorId: 'c1',
      sessionId: '999',
      threadId: 't1',
      creatorName: null,
      creatorPlatform: null,
      sessionStartedAt: null,
      transcriptPath: null,
      summaryPath: null,
    };
    applyRefreshPayload(ctx, {
      creatorId: 'c1',
      sessionId: '999',
      sessionKind: 'vod',
      transcriptPath: 'creators/x/videos/999.transcript.json',
      summaryPath: 'creators/x/videos/999.summary.md',
    });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await hydrateContextFromApi(ctx);
    expect(ctx.transcriptPath).toBe('creators/x/videos/999.transcript.json');
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/sessions/999'),
      expect.anything(),
    );
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pnpm --filter m2t-agent-sidecar test`  
Expected: FAIL (`applyRefreshPayload` not exported)

- [ ] **Step 3: Implement in context.ts + main.ts**

Export `applyRefreshPayload(ctx, payload)` setting `ctx.transcriptPath`, `ctx.summaryPath`, env vars `M2T_SESSION_KIND`, `M2T_CONTEXT_MODE`. Update `hydrateContextFromApi`: if `ctx.transcriptPath` or `ctx.summaryPath` set, skip `GET /api/sessions/{id}`. In `main.ts` `context.refresh` handler, call `applyRefreshPayload` before `reloadContext()`.

- [ ] **Step 4: Run tests**

Run: `pnpm --filter m2t-agent-sidecar test`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/m2t-agent-sidecar/src/context.ts packages/m2t-agent-sidecar/src/main.ts packages/m2t-agent-sidecar/src/context.test.ts
git commit -m "feat(sidecar): extend context.refresh with paths and sessionKind"
```

---

### Task 5: Desktop `sendAgentContextRefresh` payload

**Files:**
- Modify: `apps/m2t-desktop/src/features/agent/agentSidecar.ts`
- Modify: `apps/m2t-desktop/src/features/agent/agentSidecar.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
// append to agentSidecar.test.ts
import { buildContextRefreshPayload } from './agentSidecar';

it('buildContextRefreshPayload includes paths and kind', () => {
  expect(
    buildContextRefreshPayload({
      creatorId: 'c1',
      sessionId: '999',
      threadId: 't1',
      sessionKind: 'vod',
      transcriptPath: 'creators/x/videos/999.transcript.json',
      summaryPath: null,
      contextMode: 'transcript',
    }),
  ).toEqual({
    creatorId: 'c1',
    sessionId: '999',
    threadId: 't1',
    sessionKind: 'vod',
    transcriptPath: 'creators/x/videos/999.transcript.json',
    summaryPath: null,
    contextMode: 'transcript',
  });
});
```

- [ ] **Step 2–4:** Implement `AgentContext` extension + `buildContextRefreshPayload`; update `sendAgentContextRefresh` invoke payload; run `pnpm --filter m2t-desktop test -- agentSidecar`.

- [ ] **Step 5: Commit**

```bash
git add apps/m2t-desktop/src/features/agent/agentSidecar.ts apps/m2t-desktop/src/features/agent/agentSidecar.test.ts
git commit -m "feat(desktop): pass transcript paths in agent context refresh"
```

---

## PR 3 — React layout presets + transcript session select

### Task 6: Layout persist — `desktopLayoutPreset` + `agentHistoryW`

**Files:**
- Modify: `apps/m2t-desktop/src/features/layout/layoutConstants.ts`
- Test: `apps/m2t-desktop/src/features/layout/layoutPresets.test.ts` (create)

- [ ] **Step 1: Write failing test**

```typescript
import { describe, expect, it, beforeEach } from 'vitest';
import { loadLayout, saveLayout, LAYOUT_STORAGE_KEY, type LayoutPersist } from './layoutConstants';

describe('desktopLayoutPreset persist', () => {
  beforeEach(() => localStorage.clear());

  it('round-trips desktopLayoutPreset and agentHistoryW', () => {
    const layout: LayoutPersist = {
      leftCollapsed: false,
      rightCollapsed: false,
      sidebarW: 240,
      rightW: 360,
      agentH: 320,
      desktopLayoutPreset: 'transcript-chat',
      agentHistoryW: 220,
    };
    saveLayout(layout);
    expect(loadLayout().desktopLayoutPreset).toBe('transcript-chat');
    expect(loadLayout().agentHistoryW).toBe(220);
  });
});
```

- [ ] **Step 2–4:** Extend `LayoutPersist` with `desktopLayoutPreset?: 'full' | 'transcript-chat' | 'chat-only'` (default `'full'`), `agentHistoryW` (default 200, clamp 140–340); `applyLayoutCssVars` sets `--agent-history-w`; run Vitest.

- [ ] **Step 5: Commit**

---

### Task 7: `DesktopLayoutPresets` + grid classes

**Files:**
- Create: `apps/m2t-desktop/src/features/layout/DesktopLayoutPresets.tsx`
- Modify: `apps/m2t-desktop/src/features/layout/SidePanelHeader.tsx` (or RightRail header)
- Modify: `apps/m2t-desktop/src/features/layout/AppShell.tsx`
- Test: `apps/m2t-desktop/src/features/layout/uiParity.test.tsx` (extend)

- [ ] **Step 1: Write failing test** — render presets, click `transcript-chat`, assert `#app` has class `desktop-layout-transcript`.

- [ ] **Step 2–4:** Implement component; `setDesktopLayoutPreset` in store; `chat-only` auto `setRightCollapsed(false)`; hide `#collapse-right` in chat-only via class on `#app`.

- [ ] **Step 5: Commit**

---

### Task 8: `TranscriptSelection` + `TranscriptSessionSelect`

**Files:**
- Create: `apps/m2t-desktop/src/features/transcript/transcriptSelection.ts`
- Create: `apps/m2t-desktop/src/features/transcript/TranscriptSessionSelect.tsx`
- Modify: `apps/m2t-desktop/src/features/layout/useLayoutStore.ts`
- Test: `apps/m2t-desktop/src/features/transcript/transcriptSelection.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
import { describe, expect, it } from 'vitest';
import { selectionFromSessionRow, type SessionListItem } from './transcriptSelection';

describe('selectionFromSessionRow', () => {
  it('maps live row to history selection', () => {
    const row: SessionListItem = { kind: 'live', item_id: 'uuid-1', has_transcript: true };
    expect(selectionFromSessionRow(row)).toEqual({
      mode: 'history',
      kind: 'live',
      itemId: 'uuid-1',
    });
  });
});
```

- [ ] **Step 2–4:** Store holds `transcriptSelection`; dropdown loads `GET /api/creators/{id}/sessions`; first synthetic option `{ mode: 'live', liveSessionId: active_session_id }`; on change update store + toast if no transcript.

- [ ] **Step 5: Commit**

---

### Task 9: Conditional `TranscriptPane` slot (D4)

**Files:**
- Modify: `apps/m2t-desktop/src/features/layout/AppShell.tsx`
- Modify: `apps/m2t-desktop/src/features/transcript/TranscriptPane.tsx`
- Modify: `apps/m2t-desktop/src/features/layout/useColumnResize.ts`

- [ ] **Step 1: Write failing test** — in `uiParity.test.tsx`, with preset `transcript-chat`, assert transcript pane renders under `.center` not `.right-split`.

- [ ] **Step 2–4:** Single `<TranscriptPane key={stableKey} .../>` rendered in exactly one branch:

```tsx
const transcriptPane = (
  <TranscriptPane
    sessionId={resolvedLiveSessionId}
    summaryPath={resolvedSummaryPath}
    transcriptPath={resolvedTranscriptPath}
    playbackItem={historyPlaybackItem}
    mode={transcriptMode}
  />
);
// preset === 'transcript-chat' ? <div className="transcript-center-slot">{transcriptPane}</div>
// : preset !== 'chat-only' ? <div className="right-split">{transcriptPane}…</div> : null
```

Extend `TranscriptPane` fetch: when `playbackItem.kind === 'vod'`, use `/api/creators/{id}/history/vod/{itemId}/transcript`; when history live, use `/history/live/{id}/transcript`. **Never** call `/api/sessions/{aweme_id}` for vod.

Extend `maxRightWForViewport` → add `maxCenterRightWForTranscriptLayout()` splitting remaining width between center and right when `.desktop-layout-transcript`.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(desktop): layout presets and transcript session dropdown"
```

---

## PR 4 — Agent multi-thread UI

### Task 10: `useAgentThreads` + `useAgentTabs`

**Files:**
- Create: `apps/m2t-desktop/src/features/agent/useAgentThreads.ts`
- Create: `apps/m2t-desktop/src/features/agent/useAgentTabs.ts`
- Test: `apps/m2t-desktop/src/features/agent/useAgentTabs.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
import { describe, expect, it } from 'vitest';
import { pushAgentTab, closeAgentTab } from './useAgentTabs';

describe('useAgentTabs helpers', () => {
  it('caps at 5 tabs dropping oldest', () => {
    let ids = ['a', 'b', 'c', 'd', 'e'];
    ids = pushAgentTab(ids, 'f');
    expect(ids).toEqual(['b', 'c', 'd', 'e', 'f']);
  });

  it('close tab does not delete thread id from API', () => {
    const { tabIds, activeId } = closeAgentTab(['a', 'b'], 'a', 'a');
    expect(tabIds).toEqual(['b']);
    expect(activeId).toBe('b');
  });
});
```

- [ ] **Step 2–4:** `useAgentThreads` loads `GET /api/chat/threads` (no filter), groups by `updated_at`; `useAgentTabs` manages `agentTabIds` (not persisted). Export pure helpers for tests.

- [ ] **Step 5: Commit**

---

### Task 11: Agent UI components

**Files:**
- Create: `AgentTabsBar.tsx`, `AgentHistorySidebar.tsx`, `AgentThreadContextMenu.tsx`, `useAgentHistoryResize.ts`
- Modify: `AgentPanel.tsx` — remove `.agent-header` / `model-pill`
- Modify: CSS in desktop styles for `.agent-tabs-bar`, `.agent-history`, `.agent-col-resize`

- [ ] **Step 1–4:** Implement per spec §3–§4; wire `useAgentHistoryResize` to `--agent-history-w`; persist collapse in `m2t-agent-history-collapsed` localStorage key.

- [ ] **Step 5: Commit**

---

### Task 12: Refactor `useM2tAgent` + creator mismatch toast (A10, D3)

**Files:**
- Modify: `apps/m2t-desktop/src/features/agent/useM2tAgent.ts`
- Modify: `apps/m2t-desktop/src/features/agent/AgentPanel.tsx`

- [ ] **Step 1: Write failing test** (Vitest + mock API): activating thread with mismatched `creator_id` calls `showToast` with switch action.

- [ ] **Step 2–4:** Change signature to `useM2tAgent({ threadId, creatorId, sessionContext })`; remove auto-filter threads by creator; on history item click: if `thread.creator_id !== selectedId`, toast + optional `setSelectedId`; on transcript session change: `PATCH /api/chat/threads/{id}` `{ sessionId }` + `sendAgentContextRefresh` with paths from session row.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(desktop): agent multi-tab UI and global history sidebar"
```

---

## Verification (full suite)

Run after each PR and before merge:

```bash
source .venv/bin/activate
pytest tests/unit/test_api_history_transcript.py tests/unit/test_api_sessions_list.py tests/unit/test_api_sessions.py tests/unit/test_api_chat.py -v -m desktop
pnpm --filter m2t-desktop test
pnpm --filter m2t-agent-sidecar test
```

Manual (Tauri): `pnpm --filter m2t-desktop tauri dev` — verify L1–L6, A1–A10 against spec §11.

---

## Spec coverage self-review

| Spec § | Task |
|--------|------|
| §2 layout presets | Task 6–7 |
| §2.3 session dropdown | Task 8–9 |
| §3 Agent pane | Task 11–12 |
| §4 history list | Task 10–11 |
| §5 state model | Task 6, 8, 10 |
| §14.3 A history API | Task 1–2 |
| §14.3 B display_label | Task 3 |
| §14.3 C sidecar refresh | Task 4–5, 12 |
| §11 L1–L6 | Task 7, 9 + manual |
| §11 A1–A10 | Task 10–12 + manual |

**Gaps intentionally deferred (spec §12):** tab drag reorder, open-tabs persist, delete confirm dialog, B站 archive in dropdown (P2).

---

## Eng review amendments (2026-06-06)

Applied during `/plan-eng-review`:

1. **Single TranscriptPane instance:** Only one branch renders `TranscriptPane` per preset (never duplicate mount). Preset switch may remount; acceptable for v1 — document that live WS reconnects on preset change (existing reducer handles refetch).
2. **Shared resolve logic:** Task 1 centralizes path resolution; routes must not duplicate `history_media` DB lookups.
3. **Live «当前»:** Keep `GET/WS /api/sessions/{uuid}` for active partial live; history live entries use history route (Task 9).
4. **Delete thread confirm:** Add simple `window.confirm` in Task 11 (spec recommends; not blocking v1 prototype parity).
5. **Regression test:** Task 2 `test_sessions_transcript_404_for_aweme_id` is **CRITICAL**.

---

## NOT in scope

| Item | Rationale |
|------|-----------|
| Pi tool semantics changes | Spec §0.3 |
| Agent tab open-state persistence | Spec §12 — refresh clears tabs |
| History filter by creator | Spec §12 |
| B站 archive/dynamic in dropdown | Spec §14.5 P2 |
| P1 thread search/pagination API | Spec §14.4 — follow-up PR |
| Attachment/context buttons | Toast only |

---

## What already exists

| Capability | Reuse in plan |
|------------|---------------|
| `GET /api/chat/threads` global list | Task 10 — no backend change |
| `GET /api/creators/{id}/sessions` | Task 8 dropdown |
| `history_media` live/vod DB lookup pattern | Task 1 mirrors `_resolve_media_path` |
| `read_transcript_payload` / `read_summary_text` | Task 1 |
| `TranscriptPane` + WS live stream | Task 9 extends fetch only |
| `sendAgentContextRefresh` | Task 5 extends payload |
| `AgentPanel` + `useM2tAgent` single-thread | Task 12 refactors |

---

## Parallelization

| Step | Modules | Depends on |
|------|---------|------------|
| PR1 backend | `api/services`, `api/routes` | — |
| PR2 sidecar | `packages/m2t-agent-sidecar`, `agentSidecar.ts` | PR1 (paths in API responses) |
| PR3 layout | `apps/m2t-desktop/layout`, `transcript` | PR1 for vod fetch |
| PR4 agent UI | `apps/m2t-desktop/agent` | PR2 + PR3 |

**Lanes:** PR1 first. PR2 and PR3 can run in parallel worktrees after PR1 merges. PR4 after PR2+PR3.

---

## Failure modes

| Path | Failure | Test? | User sees |
|------|---------|-------|-----------|
| history vod transcript | aweme deleted | Task 2 | 404 → toast |
| history vod via `/api/sessions/{aweme}` | wrong route | Task 2 **CRITICAL** | 404 (must not use) |
| sidecar hydrate vod | missing paths in refresh | Task 4 | wrong system prompt |
| preset switch during live WS | unmount | manual | brief reconnect |
| thread creator mismatch | user ignores toast | Task 12 | toast + switch button |

**Critical gap if missing:** Task 2 regression test (vod → sessions route).

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | CLEAR (PLAN) | 5 amendments applied; 0 unresolved |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | Recommend before PR4 merge |
| DX Review | `/plan-devex-review` | — | 0 | — | — |

- **UNRESOLVED:** 0
- **VERDICT:** Eng review CLEAR — ready to implement PR1
