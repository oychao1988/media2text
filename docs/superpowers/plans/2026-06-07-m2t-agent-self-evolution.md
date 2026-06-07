# m2t Agent 自进化闭环 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 Hermes 聊天驱动自进化闭环：Memory Hermes 契约、post-turn background review、skill_manage + provenance/usage、Curator（Phase C），与既有 Creator distill/evolve 并存。

**Architecture:** 分三期 M7a→M7b→M7c。Nudge 计数与 prompt 缓存持久化于 `sessions.agent_state_json`（per session_id）；review 在 `turn_end` 后 daemon thread 运行，压缩前 deepcopy 快照、独立 `open_db()`；M7a 仅 memory review（skill nudge 门控至 M7b）。

**Tech Stack:** Python 3.12+、SQLite SessionDB、FastAPI agent routes、pytest `-m agent`、OpenAI-compatible LLM（复用 `summarize.llm.providers`）。

**Spec:** [2026-06-07-m2t-agent-self-evolution-design.md](../specs/2026-06-07-m2t-agent-self-evolution-design.md)  
**Epic manifest（M7c 末）:** `docs/issues/epic-manifests/agent-self-evolution.yaml`  
**前置:** Hermes M0–M6 已 merge（`AIAgent`、`memory_store.py`、`skills_index.py`）

---

## 目标架构（ASCII）

```
User turn
  → AIAgent.run_conversation
      · hydrate agent_state_json (nudge + prompt cache)
      · tool loop (memory add/replace/remove; M7b+ skill_manage)
      · snapshot messages BEFORE maybe_post_turn_compress
      · finally: compress → title → turn_end → maybe_spawn_background_review
  → [daemon] background_review thread
      · open_db() 新连接
      · AIAgent(quiet, write_origin=background_review, whitelist tools)
      · run_conversation(review_prompt, history=snapshot)
  → [M7c idle tick] maybe_run_curator
```

---

## 文件地图

| 路径 | 阶段 | 职责 |
|------|------|------|
| `src/media2text/core/config.py` | M7a+ | `MemoryConfig.nudge_interval`、`SkillsConfig`、`CuratorConfig`、`AgentLoopConfig.review_*` |
| `src/media2text/core/storage/db.py` | M7a | `_migrate_hermes_v4` → `sessions.agent_state_json` |
| `src/media2text/agent/agent_state.py` | M7a | JSON hydrate/persist、compression handoff、`review_in_flight` |
| `src/media2text/agent/memory_store.py` | M7a | `MemoryStore` § 条目级 API + legacy 惰性归一化 |
| `src/media2text/agent/model_tools.py` | M7a/M7b | `add/replace/remove`；`write_origin`；`skill_manage` 分发 |
| `src/media2text/agent/background_review.py` | M7a | vendored prompts + `spawn_background_review_thread` |
| `src/media2text/agent/agent_turn_hooks.py` | M7a | nudge 判定、`maybe_spawn_background_review` |
| `src/media2text/agent/ai_agent.py` | M7a | 计数器、快照顺序、prompt cache、review spawn |
| `src/media2text/agent/context_compressor.py` | M7a | fork 时复制 `agent_state_json` |
| `src/media2text/agent/skill_manage.py` | M7b | create/patch/edit/delete/write_file/remove_file |
| `src/media2text/agent/skill_provenance.py` | M7b | `write_origin`、`mark_agent_created` |
| `src/media2text/agent/skill_usage.py` | M7b | `.usage.json` 读写、pin、telemetry |
| `src/media2text/agent/curator.py` | M7c | stale/archive + LLM review fork |
| `src/media2text/agent/tools/registry.py` | M7b | `skill_manage` schema |
| `src/media2text/agent/tools/toolsets.py` | M7b | `_HERMES_NAMES` 加 `skill_manage` |
| `src/media2text/agent/creator_distill/bootstrap.py` | M7b | distill 完成时 `skill_usage.pin` |
| `src/media2text/cli/agent.py` | M7c | `media2text agent curator …` |
| `config.example.yaml` | M7a/M7c | `memory.nudge_interval`、`skills.*`、`curator.*` |
| `tests/unit/test_memory_store_entries.py` | M7a | S1、legacy 归一化 |
| `tests/unit/test_agent_state_persistence.py` | M7a | SQLite hydrate、fork 复制 |
| `tests/unit/test_agent_nudge_counters.py` | M7a | S2、M7a skill nudge 禁用 |
| `tests/unit/test_background_review.py` | M7a | S3–S5 |
| `tests/unit/test_review_snapshot_order.py` | M7a | ER2 压缩前快照 |
| `tests/unit/test_skill_manage.py` | M7b | S7–S9 |
| `tests/unit/test_skill_provenance.py` | M7b | S8 |
| `tests/unit/test_curator_transitions.py` | M7c | S12–S14 |
| `tests/unit/test_api_agent_review_e2e.py` | M7a | mock LLM 集成 |

---

## 阶段与 Success Criteria 映射

| 阶段 | 内容 | 验收 ID |
|------|------|---------|
| **M7a** | Memory § 契约；`agent_state_json`；nudge + background review；config | S1–S6 |
| **M7b** | `skill_manage` + provenance + usage；distill pin；skill review | S7–S11 |
| **M7c** | Curator + idle tick + CLI + backup | S12–S15 |

**并行 Lane（spec §20.4）：** A=`memory_store` · B=`agent_state`+migration · C=`background_review`+hooks（依赖 B）· D=`ai_agent`（依赖 A+C）。M7b 顺序依赖 M7a；M7c 依赖 M7b。

---

# M7a — Memory 契约 + Background Review

### Task 1: 配置项（nudge / review 总开关）

**Files:**
- Modify: `src/media2text/core/config.py`
- Modify: `config.example.yaml`
- Test: `tests/unit/test_agent_config_self_evolution.py`（新建）

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_config_self_evolution.py
import pytest

from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_memory_nudge_interval_default() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.memory.nudge_interval == 10


def test_agent_review_enabled_default() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.agent.review_enabled is True
    assert cfg.agent.review_max_iterations == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_config_self_evolution.py -v`  
Expected: FAIL — `MemoryConfig` has no attribute `nudge_interval`

- [ ] **Step 3: Write minimal implementation**

在 `config.py` 扩展：

```python
class MemoryConfig(BaseModel):
    max_chars: int = 2200
    user_max_chars: int = 1375
    soul_max_chars: int = 4000
    memory_enabled: bool = True
    user_profile_enabled: bool = True
    soul_enabled: bool = True
    nudge_interval: int = 10  # 0 = disable memory review


class SkillsConfig(BaseModel):
    creation_nudge_interval: int = 10
    agent_skills_subdir: str = "skills"


class CuratorConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = 168
    min_idle_hours: int = 2
    backup_keep: int = 5


class AgentLoopConfig(BaseModel):
    max_turns: int = 25
    review_enabled: bool = True
    review_max_iterations: int = 16
```

`AppConfig` 增加 `skills: SkillsConfig`、`curator: CuratorConfig`。

`config.example.yaml` 在现有 `memory:` / `agent:` 块追加 spec §5.4 字段。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_config_self_evolution.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/config.py config.example.yaml tests/unit/test_agent_config_self_evolution.py
git commit -m "feat(agent): add self-evolution config keys for nudge and review"
```

---

### Task 2: SQLite migration — `sessions.agent_state_json`

**Files:**
- Modify: `src/media2text/core/storage/db.py`
- Test: `tests/unit/test_agent_state_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_state_persistence.py
import json

import pytest

from media2text.agent.agent_state import AgentState, load_agent_state, save_agent_state
from media2text.agent.hermes_state import SessionDB
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def test_agent_state_column_exists(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "agent_state_json" in cols
    conn.close()


def test_save_and_load_agent_state(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    db = SessionDB(conn)
    sid = db.create_session(display_thread_id="t1", title="hi")
    state = AgentState(turns_since_memory=3, review_in_flight=False)
    save_agent_state(db, sid, state)
    loaded = load_agent_state(db, sid)
    assert loaded.turns_since_memory == 3
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_state_persistence.py::test_agent_state_column_exists -v`  
Expected: FAIL — column missing; `agent_state` module not found

- [ ] **Step 3: Write minimal implementation**

`db.py` 追加：

```python
def _migrate_hermes_v4(conn: sqlite3.Connection) -> None:
    """Agent self-evolution: nudge counters + prompt cache (M7a)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "agent_state_json" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN agent_state_json TEXT")
        conn.commit()
```

在 `connect()` 迁移链 `_migrate_hermes_v3(conn)` 之后调用 `_migrate_hermes_v4(conn)`。

创建 `src/media2text/agent/agent_state.py`：

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from media2text.agent.hermes_state import SessionDB


@dataclass
class AgentState:
    turns_since_memory: int = 0
    iters_since_skill: int = 0
    review_in_flight: bool = False
    cached_system_prompt: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "turns_since_memory": self.turns_since_memory,
                "iters_since_skill": self.iters_since_skill,
                "review_in_flight": self.review_in_flight,
                "cached_system_prompt": self.cached_system_prompt,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | None) -> AgentState:
        if not raw:
            return cls()
        data = json.loads(raw)
        return cls(
            turns_since_memory=int(data.get("turns_since_memory") or 0),
            iters_since_skill=int(data.get("iters_since_skill") or 0),
            review_in_flight=bool(data.get("review_in_flight")),
            cached_system_prompt=data.get("cached_system_prompt"),
        )


def load_agent_state(db: SessionDB, session_id: str) -> AgentState:
    row = db.get_session_row(session_id)
    if row is None:
        raise KeyError(session_id)
    return AgentState.from_json(row["agent_state_json"])


def save_agent_state(db: SessionDB, session_id: str, state: AgentState) -> None:
    db.update_agent_state_json(session_id, state.to_json())


def hydrate_turns_since_memory(
    db: SessionDB,
    session_id: str,
    *,
    nudge_interval: int,
) -> AgentState:
    """Replay-safe: prior user turns mod interval when column was empty."""
    state = load_agent_state(db, session_id)
    if nudge_interval <= 0:
        return state
    prior = db.count_user_messages(session_id)
    if prior > 0 and state.turns_since_memory == 0:
        # exclude current turn caller will increment separately if needed
        state.turns_since_memory = prior % nudge_interval
    return state
```

`SessionDB` 新增 `update_agent_state_json`、`count_user_messages`、`copy_agent_state(parent_id, child_id)`（fork 用）。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_state_persistence.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/core/storage/db.py src/media2text/agent/agent_state.py tests/unit/test_agent_state_persistence.py
git commit -m "feat(agent): persist nudge counters in sessions.agent_state_json"
```

---

### Task 3: MemoryStore § 条目 API

**Files:**
- Modify: `src/media2text/agent/memory_store.py`
- Test: `tests/unit/test_memory_store_entries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_memory_store_entries.py
import pytest

from media2text.agent.memory_store import MemoryStore
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_add_entry_uses_section_delimiter(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    store = MemoryStore(cfg)
    store.add("memory", "likes blue widgets")
    raw = (tmp_path / "data" / ".agent" / "MEMORY.md").read_text(encoding="utf-8")
    assert raw.startswith("§")
    assert "likes blue widgets" in raw


def test_replace_unique_match(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    store = MemoryStore(cfg)
    store.add("memory", "alpha")
    store.add("memory", "beta")
    store.replace("memory", old_text="alpha", content="alpha revised")
    entries = store.list_entries("memory")
    assert any("alpha revised" in e for e in entries)
    assert not any(e.strip() == "alpha" for e in entries)


def test_legacy_whole_file_normalized_on_add(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    path = tmp_path / "data" / ".agent" / "MEMORY.md"
    path.parent.mkdir(parents=True)
    path.write_text("- evolve bullet one\n- evolve bullet two", encoding="utf-8")
    store = MemoryStore(cfg)
    store.add("memory", "new fact")
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("§")
    assert "new fact" in raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory_store_entries.py -v`  
Expected: FAIL — `MemoryStore` not defined

- [ ] **Step 3: Write minimal implementation**

在 `memory_store.py` 追加 `MemoryStore` 类（保留现有 `read_file`/`write_file` 供兼容）：

```python
_SECTION = "§"


def _split_entries(text: str) -> list[str]:
    if not text.strip():
        return []
    if _SECTION not in text:
        return [text.strip()]
    parts = [p.strip() for p in text.split(_SECTION) if p.strip()]
    return parts


def _join_entries(entries: list[str]) -> str:
    if not entries:
        return ""
    return "\n\n".join(f"{_SECTION}\n{e.strip()}" for e in entries if e.strip())


class MemoryStore:
    def __init__(self, cfg: AppConfig, profile: AgentProfileContext | None = None) -> None:
        self._cfg = cfg
        self._profile = profile

    def _read_raw(self, target: MemoryTarget) -> str:
        if self._profile:
            return read_file_for_profile(self._profile, target)
        return read_file(self._cfg, target)

    def _write_raw(self, target: MemoryTarget, content: str) -> None:
        if self._profile:
            write_file_for_profile(self._cfg, self._profile, target, content, mode="replace")
        else:
            write_file(self._cfg, target, content, mode="replace")

    def list_entries(self, target: MemoryTarget) -> list[str]:
        return _split_entries(self._read_raw(target))

    def add(self, target: MemoryTarget, content: str) -> dict[str, Any]:
        entries = self.list_entries(target)
        entries.append(content.strip())
        joined = _join_entries(entries)
        self._write_raw(target, joined)
        return {"target": target, "entries": len(entries), "chars": len(joined)}

    def replace(self, target: MemoryTarget, *, old_text: str, content: str) -> dict[str, Any]:
        entries = self.list_entries(target)
        matches = [i for i, e in enumerate(entries) if old_text in e]
        if len(matches) != 1:
            raise ValueError(f"old_text must match exactly one entry, got {len(matches)}")
        entries[matches[0]] = entries[matches[0]].replace(old_text, content, 1)
        joined = _join_entries(entries)
        self._write_raw(target, joined)
        return {"target": target, "entries": len(entries), "chars": len(joined)}

    def remove(self, target: MemoryTarget, *, old_text: str) -> dict[str, Any]:
        entries = self.list_entries(target)
        matches = [i for i, e in enumerate(entries) if old_text in e]
        if len(matches) != 1:
            raise ValueError(f"old_text must match exactly one entry, got {len(matches)}")
        del entries[matches[0]]
        joined = _join_entries(entries)
        self._write_raw(target, joined)
        return {"target": target, "entries": len(entries), "chars": len(joined)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_memory_store_entries.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/agent/memory_store.py tests/unit/test_memory_store_entries.py
git commit -m "feat(agent): MemoryStore section-delimited entries"
```

---

### Task 4: memory tool — add/replace/remove + write/append 兼容

**Files:**
- Modify: `src/media2text/agent/model_tools.py`
- Modify: `tests/unit/test_agent_memory.py`

- [ ] **Step 1: Write the failing test**

在 `tests/unit/test_agent_memory.py` 追加：

```python
def test_memory_add_replace_remove(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    conn = connect(tmp_path / "media2text.db")
    ctx = ToolContext(cfg=cfg, conn=conn)
    out = handle_function_call(
        "memory",
        {"action": "add", "target": "memory", "content": "fact A"},
        ctx,
    )
    assert out["ok"] is True
    out2 = handle_function_call(
        "memory",
        {"action": "replace", "target": "memory", "old_text": "fact A", "content": "fact A2"},
        ctx,
    )
    assert out2["ok"] is True
    read = handle_function_call("memory", {"action": "read", "target": "memory"}, ctx)
    assert "fact A2" in read["data"]["content"]
    conn.close()


def test_memory_write_append_deprecated(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    conn = connect(tmp_path / "media2text.db")
    ctx = ToolContext(cfg=cfg, conn=conn)
    out = handle_function_call(
        "memory",
        {"action": "write", "target": "memory", "content": "legacy whole file"},
        ctx,
    )
    assert out["ok"] is True
    assert out["data"].get("deprecated") is True
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_memory.py::test_memory_add_replace_remove -v`  
Expected: FAIL — `action must be read, write, or append`

- [ ] **Step 3: Write minimal implementation**

更新 `_handle_memory`：

```python
from media2text.agent.memory_store import MemoryStore

def _handle_memory(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    action = str(params.get("action") or "").lower()
    target = _resolve_target(params)
    profile = _active_profile(ctx)
    store = MemoryStore(ctx.cfg, profile=profile)

    if action == "read":
        content = read_file_for_profile(profile, target)
        return {"ok": True, "data": {"target": target, "content": content}}

    if action == "add":
        text = str(params.get("content") or "")
        meta = store.add(target, text)
        return {"ok": True, "data": {**meta, "content": read_file_for_profile(profile, target)}}

    if action == "replace":
        meta = store.replace(
            target,
            old_text=str(params.get("old_text") or ""),
            content=str(params.get("content") or ""),
        )
        return {"ok": True, "data": {**meta, "content": read_file_for_profile(profile, target)}}

    if action == "remove":
        meta = store.remove(target, old_text=str(params.get("old_text") or ""))
        return {"ok": True, "data": {**meta, "content": read_file_for_profile(profile, target)}}

    if action in ("write", "append"):
        # ... existing write_file_for_profile path ...
        resp = {"ok": True, "data": {**meta, "content": read_file_for_profile(profile, target), "deprecated": True}}
        return resp

    raise AgentToolError("action must be read, add, replace, remove, write, or append")
```

同步更新 `tools/registry.py` 中 `memory` tool schema 的 `action` enum。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_memory.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/agent/model_tools.py src/media2text/agent/tools/registry.py tests/unit/test_agent_memory.py
git commit -m "feat(agent): Hermes memory actions add/replace/remove with legacy compat"
```

---

### Task 5: background_review + agent_turn_hooks

**Files:**
- Create: `src/media2text/agent/background_review.py`
- Create: `src/media2text/agent/agent_turn_hooks.py`
- Test: `tests/unit/test_background_review.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_background_review.py
import threading
from unittest.mock import MagicMock, patch

import pytest

from media2text.agent.agent_turn_hooks import ReviewFlags, maybe_spawn_background_review
from media2text.agent.background_review import REVIEW_TOOL_NAMES, build_review_prompt
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_review_tool_whitelist() -> None:
    assert REVIEW_TOOL_NAMES == {"memory", "skill_manage", "skills_list", "skill_view"}


def test_build_review_prompt_memory_only() -> None:
    p = build_review_prompt(review_memory=True, review_skills=False, scope_hint="creator:abc")
    assert "memory" in p.lower()
    assert "creator:abc" in p


@patch("media2text.agent.agent_turn_hooks.spawn_background_review_thread")
def test_spawn_skips_when_review_in_flight(mock_spawn, tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    agent = MagicMock()
    from media2text.agent.agent_state import AgentState

    state = AgentState(review_in_flight=True)
    maybe_spawn_background_review(
        agent,
        cfg,
        session_id="s1",
        db=MagicMock(),
        messages_snapshot=[],
        flags=ReviewFlags(review_memory=True),
        agent_state=state,
        cancelled=False,
        has_final_text=True,
    )
    mock_spawn.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_background_review.py -v`  
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

`background_review.py`（核心骨架；prompt 正文从 Hermes vendored 常量，末尾 append scope hint）：

```python
REVIEW_TOOL_NAMES = frozenset({"memory", "skill_manage", "skills_list", "skill_view"})

_MEMORY_REVIEW_PROMPT = """..."""  # vendored from hermes-agent
_SKILL_REVIEW_PROMPT = """..."""
_COMBINED_REVIEW_PROMPT = """..."""

def build_review_prompt(*, review_memory: bool, review_skills: bool, scope_hint: str) -> str:
    if review_memory and review_skills:
        base = _COMBINED_REVIEW_PROMPT
    elif review_skills:
        base = _SKILL_REVIEW_PROMPT
    else:
        base = _MEMORY_REVIEW_PROMPT
    return f"{base}\n\nActive profile scope:\n{scope_hint}"


def spawn_background_review_thread(
    *,
    cfg: AppConfig,
    session_id: str,
    display_thread_id: str,
    binding: dict,
    creator_id: str | None,
    messages_snapshot: list[dict],
    review_memory: bool,
    review_skills: bool,
    provider_name: str,
    model: str,
    cached_system_prompt: str | None,
) -> threading.Thread:
    def _run() -> None:
        from media2text.core.workspace import open_db
        from media2text.agent.ai_agent import AIAgent
        from media2text.agent.agent_state import load_agent_state, save_agent_state, AgentState

        conn = open_db(cfg)
        try:
            db = SessionDB(conn)
            # ... build scope_hint from profile_resolver ...
            prompt = build_review_prompt(
                review_memory=review_memory,
                review_skills=review_skills,
                scope_hint=scope_hint,
            )
            agent = AIAgent(
                db, cfg,
                toolset="review",  # new toolset: memory + skills only
                write_origin="background_review",
                quiet=True,
            )
            agent.run_review_conversation(
                display_thread_id=display_thread_id,
                user_text=prompt,
                conversation_history=messages_snapshot,
                binding=binding,
                creator_id=creator_id,
                max_iterations=cfg.agent.review_max_iterations,
                cached_system_prompt=cached_system_prompt,
            )
        finally:
            st = load_agent_state(db, session_id)
            st.review_in_flight = False
            save_agent_state(db, session_id, st)
            conn.close()

    t = threading.Thread(target=_run, daemon=True, name=f"bg-review-{session_id[:8]}")
    t.start()
    return t
```

`agent_turn_hooks.py`：

```python
@dataclass(frozen=True)
class ReviewFlags:
    review_memory: bool = False
    review_skills: bool = False


def maybe_spawn_background_review(
    foreground_agent,
    cfg: AppConfig,
    *,
    session_id: str,
    db: SessionDB,
    messages_snapshot: list[dict],
    flags: ReviewFlags,
    agent_state: AgentState,
    cancelled: bool,
    has_final_text: bool,
    binding: dict,
    creator_id: str | None,
    display_thread_id: str,
    provider_name: str,
    model: str,
) -> None:
    if not cfg.agent.review_enabled:
        return
    if cancelled or not has_final_text:
        return
    if not flags.review_memory and not flags.review_skills:
        return
    if agent_state.review_in_flight:
        return
    agent_state.review_in_flight = True
    save_agent_state(db, session_id, agent_state)
    spawn_background_review_thread(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_background_review.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/agent/background_review.py src/media2text/agent/agent_turn_hooks.py tests/unit/test_background_review.py
git commit -m "feat(agent): background review spawn and whitelist toolset"
```

---

### Task 6: AIAgent hooks — nudge、快照顺序、prompt cache

**Files:**
- Modify: `src/media2text/agent/ai_agent.py`
- Modify: `src/media2text/agent/context_compressor.py`
- Modify: `src/media2text/agent/tools/toolsets.py`（`review` toolset）
- Test: `tests/unit/test_agent_nudge_counters.py`
- Test: `tests/unit/test_review_snapshot_order.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_nudge_counters.py
import pytest
from unittest.mock import patch, MagicMock

from media2text.agent.agent_turn_hooks import compute_review_flags
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_memory_nudge_fires_at_interval() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws", "memory": {"nudge_interval": 3}})
    flags = compute_review_flags(
        cfg,
        turns_since_memory=3,
        iters_since_skill=0,
        valid_tool_names={"memory", "skills_list"},
    )
    assert flags.review_memory is True
    assert flags.review_skills is False


def test_skill_nudge_disabled_without_skill_manage() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws", "skills": {"creation_nudge_interval": 2}})
    flags = compute_review_flags(
        cfg,
        turns_since_memory=0,
        iters_since_skill=99,
        valid_tool_names={"memory", "skills_list"},
    )
    assert flags.review_skills is False
```

```python
# tests/unit/test_review_snapshot_order.py
from unittest.mock import patch, MagicMock
import pytest

pytestmark = pytest.mark.agent


@patch("media2text.agent.ai_agent.maybe_spawn_background_review")
@patch("media2text.agent.ai_agent.maybe_post_turn_compress", side_effect=lambda *a, **k: k["session_id"])
def test_snapshot_taken_before_compress(mock_compress, mock_spawn, tmp_path) -> None:
    # integration-style: assert maybe_spawn receives snapshot with pre-compress message count
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_nudge_counters.py -v`  
Expected: FAIL — `compute_review_flags` not defined

- [ ] **Step 3: Write minimal implementation**

`ai_agent.py` 变更要点（spec §10.2）：

1. Turn 开始：`state = hydrate_turns_since_memory(...)`；非 retry 时 user message 已 append 后 `state.turns_since_memory += 1`
2. 每次 LLM 返回 `tool_calls`：`state.iters_since_skill += 1`；若任一 tool 为 `skill_manage` 则归零（M7b 前不会命中）
3. `try` 块成功路径末尾、`finally` 之前：`messages_snapshot = copy.deepcopy(messages)`
4. `finally` 顺序不变，但在 `turn_end` **之后**调用 `maybe_spawn_background_review(...)`
5. `compute_review_flags` 在 `agent_turn_hooks.py`：memory 达阈值且 `"memory" in valid_tool_names`；skill 需 `"skill_manage" in valid_tool_names`（M7a 门控）
6. Prompt cache：binding/profile hash 未变且 `state.cached_system_prompt` 非空 → 复用 volatile 段；否则 rebuild 并写回

`context_compressor.apply_fork_compression` 末尾：

```python
db.copy_agent_state(parent_session_id, child_id)
```

`toolsets.py` 增加：

```python
REVIEW_TOOLSET = "review"
_REVIEW_NAMES = ["memory", "skills_list", "skill_view", "skill_manage"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_nudge_counters.py tests/unit/test_review_snapshot_order.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media2text/agent/ai_agent.py src/media2text/agent/agent_turn_hooks.py src/media2text/agent/context_compressor.py src/media2text/agent/tools/toolsets.py tests/unit/test_agent_nudge_counters.py tests/unit/test_review_snapshot_order.py
git commit -m "feat(agent): nudge counters, pre-compress review snapshot, prompt cache"
```

---

### Task 7: M7a 集成测试 + S6 profile 隔离

**Files:**
- Create: `tests/unit/test_api_agent_review_e2e.py`

- [ ] **Step 1: Write the failing test**

Mock LLM：第 N 次 turn 返回 final text；断言 review thread 调用了 `memory` add 且写入 creator A 的 `.agent/MEMORY.md`，creator B 不可见（S6）。

- [ ] **Step 2–4:** 实现 `run_review_conversation` on `AIAgent`（无 emit、deny 非 whitelist tools）；跑通 e2e。

Run: `pytest tests/unit/test_api_agent_review_e2e.py -v -m agent`

- [ ] **Step 5: Commit**

```bash
git commit -m "test(agent): background review e2e with profile isolation"
```

**M7a Gate:**

```bash
pytest tests/unit/test_memory_store_entries.py \
       tests/unit/test_agent_state_persistence.py \
       tests/unit/test_agent_nudge_counters.py \
       tests/unit/test_background_review.py \
       tests/unit/test_review_snapshot_order.py \
       tests/unit/test_agent_memory.py -v -m agent
ruff check src/media2text/agent/
```

---

# M7b — skill_manage + Provenance + Usage

### Task 8: skill_usage.py

**Files:**
- Create: `src/media2text/agent/skill_usage.py`
- Test: `tests/unit/test_skill_usage.py`

- [ ] **Step 1: Write failing test** — `record_view` / `record_patch` / `pin` 读写 `skills/.usage.json`
- [ ] **Step 2–4:** 实现 + 在 `skills_index.handle_skill_view` 调用 `record_view`
- [ ] **Step 5: Commit** — `feat(agent): skill usage telemetry`

---

### Task 9: skill_provenance.py

**Files:**
- Create: `src/media2text/agent/skill_provenance.py`
- Test: `tests/unit/test_skill_provenance.py`

- [ ] **Step 1: Write failing test**

```python
def test_background_review_marks_agent_created(tmp_path) -> None:
    from media2text.agent.skill_provenance import write_origin_ctx, BACKGROUND_REVIEW, mark_agent_created

    with write_origin_ctx(BACKGROUND_REVIEW):
        mark_agent_created("my-flow", profile_dir=tmp_path / "skills")
    usage = json.loads((tmp_path / "skills" / ".usage.json").read_text())
    assert usage["my-flow"]["agent_created"] is True
```

- [ ] **Step 3:** `contextvars.ContextVar` for `write_origin`; foreground 默认 `"foreground"`
- [ ] **Step 5: Commit**

---

### Task 10: skill_manage.py

**Files:**
- Create: `src/media2text/agent/skill_manage.py`
- Modify: `src/media2text/agent/model_tools.py`
- Modify: `src/media2text/agent/tools/registry.py`
- Modify: `src/media2text/agent/tools/toolsets.py`
- Test: `tests/unit/test_skill_manage.py`

- [ ] **Step 1: Write failing tests** — S7 create/patch；S9 delete pinned distill `{slug}-perspective` → `PROTECTED_SKILL`；`references/research/*` write_file 拒绝
- [ ] **Step 3:** 实现 actions；路径遍历拒绝 `..`；bundled `packages/agent-skills/` 只读
- [ ] **Step 4:** `pytest tests/unit/test_skill_manage.py -v`
- [ ] **Step 5: Commit** — `feat(agent): skill_manage tool with distill protection`

---

### Task 11: Distill pin + skill nudge 启用

**Files:**
- Modify: `src/media2text/agent/creator_distill/bootstrap.py`（或 evolve 落盘点）
- Modify: `tests/unit/test_creator_distill*.py`

- [ ] **Step 1:** bootstrap 完成写 `{slug}-perspective` 后调用 `skill_usage.pin(name)` + frontmatter `metadata.hermes.protected: distill`
- [ ] **Step 2:** 确认 M7b 后 `compute_review_flags` 在 `skill_manage` 可用时 skill nudge 可触发
- [ ] **Step 5: Commit** — `feat(agent): pin distilled perspective skills`

**M7b Gate:** S7–S11 pytest + 更新 `tests/unit/test_agent_memory.py` deprecation case

---

# M7c — Curator + CLI + Idle Tick

### Task 12: curator.py 核心

**Files:**
- Create: `src/media2text/agent/curator.py`
- Test: `tests/unit/test_curator_transitions.py`

- [ ] **Step 1:** stale 30d / archive 90d 仅 `agent_created: true` skills（S13–S14）
- [ ] **Step 3:** LLM review fork（`skill_view` + `skill_manage` + archive terminal）；`max_iterations=8`
- [ ] **Step 5: Commit**

---

### Task 13: CLI + idle tick

**Files:**
- Create/Modify: `src/media2text/cli/agent.py`
- Modify: `src/media2text/core/runtime/supervisor.py`（或 API lifespan idle hook）
- Test: CLI 集成 `tests/unit/test_cli_agent_curator.py`

- [ ] **Step 1:** `media2text agent curator status|run|pin|unpin|restore|rollback`
- [ ] **Step 3:** `curator.enabled: false` 默认；idle tick 检查 `min_idle_hours` + `interval_hours`
- [ ] **Step 5: Commit**

---

### Task 14: Epic manifest + 文档

**Files:**
- Create: `docs/issues/epic-manifests/agent-self-evolution.yaml`
- Create: `docs/superpowers/verification/2026-06-07-m2t-agent-self-evolution-acceptance.md`
- Modify: `CLAUDE.md`、`config.example.yaml`
- Modify: `docs/superpowers/specs/2026-06-06-m2t-desktop-agent-hermes-refactor-design.md`（Curator 一行指向本规格）

- [ ] **Step 1:** epic manifest 含 M7a/M7b/M7c issue 占位与 pytest gate
- [ ] **Step 5: Commit** — `docs: agent self-evolution epic and acceptance`

**M7c Gate:**

```bash
pytest tests/unit/test_curator_transitions.py tests/unit/test_cli_agent_curator.py -v
python scripts/epic_verify.py agent-self-evolution  # manifest 落地后
```

---

## 验证命令（全阶段）

```bash
source .venv/bin/activate
pytest tests/unit/test_memory_store_entries.py \
       tests/unit/test_background_review.py \
       tests/unit/test_skill_manage.py \
       tests/unit/test_agent_nudge_counters.py \
       tests/unit/test_agent_state_persistence.py \
       tests/unit/test_curator_transitions.py -v -m agent
ruff check src/media2text/agent/
pyright src/media2text/agent/
```

---

## Self-Review（plan vs spec）

**1. Spec coverage**

| Spec § | Task |
|--------|------|
| §5 Nudge | Task 2, 6 |
| §6 Memory 契约 | Task 3, 4 |
| §7 skill_manage | Task 10 |
| §7.3 Provenance | Task 9 |
| §7.4 Usage | Task 8 |
| §8 Background review | Task 5, 6, 7 |
| §9 Curator | Task 12, 13 |
| §10 agent_state / hooks | Task 2, 6 |
| §13 S1–S15 | 各阶段 Gate |
| §17 O1–O5 | Task 2 (O1), Task 5 (O2/O3), Task 10 (O4), Task 13 (O5) |
| §20 ER1–ER8 | Task 2 (ER1), Task 6 (ER2,4,5,7,8), Task 5 (ER3) |

**2. Placeholder scan:** 无 TBD；Task 7 e2e 与 Task 12–13 保留「实现要点」因篇幅依赖 M7a 骨架，执行时按 Task 5–6 同一模式补全 mock 细节。

**3. Type consistency:** `AgentState` 字段、`ReviewFlags`、`REVIEW_TOOL_NAMES`、`spawn_background_review_thread` 参数在 Task 2/5/6 一致；`write_origin` 经 `skill_provenance` ContextVar 贯穿 Task 9–10。

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-07-m2t-agent-self-evolution.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
