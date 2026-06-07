# m2t Agent 自进化闭环（Hermes Closed Learning Loop）

**日期:** 2026-06-07  
**状态:** 已审（可实施）  
**审阅:** §19 已确认；`/plan-eng-review` 2026-06-07  
**前置:** [Hermes 模式重构](./2026-06-06-m2t-desktop-agent-hermes-refactor-design.md)（M0–M6）、[Hermes Agent](https://github.com/NousResearch/hermes-agent)、上游文档 [Skills — self-improvement](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)、[Curator](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator)、[Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)  
**范围:** 补齐 Hermes **聊天驱动**的自进化管线；与既有 **媒体驱动** `CreatorAgentBootstrap` / `CreatorAgentEvolve`（§24.4）并存互补。

---

## 0. 摘要

Hermes 的「Agent 会成长」来自一条 **闭环学习管线**，而非单一功能：

| 层 | 机制 | m2t 现状 |
|----|------|----------|
| Turn 内 | `memory` + `skill_manage` 工具即时写盘 | `memory` 有（API 与 Hermes 不完全一致）；**无 `skill_manage`** |
| Turn 后 | **Background review fork**（daemon thread 复盘本轮） | **无** |
| 周期 | **Curator**（skill 库 stale/archive/LLM 整理） | 父规格标为可选；**未实现** |
| 检索 | `session_search` FTS | **已有** |
| 媒体 | — | **m2t 特有** distill/evolve（摘要完成后 patch） |

本规格目标：**最大程度复制** Hermes 上述三层逻辑，落盘路径与 profile 隔离遵循既有 `resolve_profile()` 语义；不引入 Gateway / Honcho / 外部 memory provider（v3 可选）。

---

## 1. 问题陈述

### 1.1 缺口

| ID | 缺口 | 用户可见影响 |
|----|------|--------------|
| G1 | 无 post-turn background review | 用户纠正偏好、workflow 教训不会自动沉淀；仅靠 turn 内 agent 自觉调 `memory` |
| G2 | 无 `skill_manage` | Agent 无法把「怎么做这类事」写成可复用 SKILL；蒸馏 skill 只能媒体 job 改 |
| G3 | 无 memory/skill **nudge 计数** | 不会周期性触发复盘 |
| G4 | `memory` tool 非 Hermes 契约（`write`/`append` vs `add`/`replace`/`remove`） | 与 upstream prompt / review fork 提示词不兼容；难以 vendor 拷贝 |
| G5 | 无 skill **provenance**（`background_review` vs `foreground`） | 无法实现 Curator「只治理 agent 自写 skill」 |
| G6 | 无 `.usage.json` 遥测 | Curator 无法判断 stale / LRU |
| G7 | distill/evolve 与聊天进化 **未打通** | 用户聊天中对博主口吻的纠正不会进 perspective skill（仅摘要进化会） |

### 1.2 与 Creator distill/evolve 的关系

两条进化轨 **互补、不合并**：

```
                    ┌─────────────────────────────────────┐
                    │         Active Agent Profile          │
                    │  workspace .agent/  OR  creator .agent/ │
                    └─────────────────────────────────────┘
                                      ▲
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
   Chat-driven (本规格)          Media-driven (§24.4)         User manual
   · memory / USER / SOUL         · bootstrap SOUL+SKILL       · 设置页编辑
   · skill_manage patch           · evolve MEMORY+SKILL+SOUL
   · background review fork       · summarize_completed 触发
   · curator 整理 skill 库
```

**规则：**

- Background review **可 patch** `{slug}-perspective`（用户当场纠正口吻/分析框架时），但 **不得** 覆盖 distill 写入的 `references/research/` 调研档案（只增 `references/session/` 或 SKILL 正文 pitfall）。
- `CreatorAgentEvolve` **不得** 删除 chat 写入的 MEMORY 条目；合并策略仅处理 evolve job 自己的 `memory_facts`。
- 蒸馏产物 skill 默认 **pinned**（见 §8.3），Curator 不得 archive；可 patch 正文。

---

## 2. 方案比选

### 方案 A — Vendor 拷贝 + 薄适配层（**推荐**）

从 `nousresearch/hermes-agent` 拷贝并适配：

- `agent/background_review.py`（已基本独立）
- `tools/skill_manage*.py`（或等价实现）
- `tools/skill_provenance.py`
- `agent/curator.py`（Phase C）
- Review prompt 原文保留（class-first rubric）

适配点：`get_hermes_home()` → `AgentProfileContext` 路径；`MemoryStore` → `memory_store.py`；`AIAgent` 构造参数对齐 m2t 已有 `run_conversation`。

| 优点 | 缺点 |
|------|------|
| 与 upstream 行为一致；后续 `hermes update` 可 diff 合并 | 首次移植工作量中等 |
| Review prompt / Curator 规则已 battle-tested | 需处理 m2t 双 profile 根目录 |

### 方案 B — 仅实现最小 fork（无 skill_manage / curator）

只做 background review + memory nudge，skill 侧仍靠 distill/evolve。

| 优点 | 缺点 |
|------|------|
| 实现快 | **不符合**「最大程度复制」；用户 workflow 教训无法变 skill |
| 风险面小 | 与 Hermes 差距大，后续补 skill_manage 要改 review prompt |

### 方案 C — 单 LLM 摘要 job 替代 fork

每 turn 结束后用一次 aux LLM 调用（无 tool loop）输出 JSON patch。

| 优点 | 缺点 |
|------|------|
| 无第二 agent loop | 失去 Hermes 的 `skill_view` / 多步 consolidate；难处理 references/ 包 |
| 实现简单 | **不推荐** — 偏离 upstream，难维护 |

**锁定：方案 A，分三期交付（§12）。**

---

## 3. 已锁定决策

| ID | 决策 | 理由 |
|----|------|------|
| SE1 | 模块名与 Hermes 对齐：`background_review.py`、`skill_manage`、`skill_provenance` | D11 Strict 命名延伸 |
| SE2 | Post-turn review 在 **`run_conversation` 返回用户可见结果之后** 异步 spawn | 不抢主 turn 延迟；对齐 upstream |
| SE3 | Review fork **仅** whitelist `memory` + `skill_manage`（经 `skills` toolset 子集） | 禁止 shell / m2t_* 写操作 |
| SE4 | Review fork 继承主 turn 的 **provider / model / cached system prompt** | Prefix cache + 认证一致（#25322） |
| SE5 | Review fork `skip_external_memory=True`（m2t 无 Honcho；内置 memory store 共享引用） | 避免污染外部 provider |
| SE6 | Skill 写入 **active profile** 的 `skills/` 根（workspace 或 creator） | 与 `resolve_skills_roots()` 一致 |
| SE7 | `write_origin=background_review` 的 **新** skill 标记 `agent_created`；foreground `skill_manage` **不**标记 | 对齐 Curator 管辖范围 |
| SE8 | 蒸馏 skill `{slug}-perspective` **默认 pinned** | 防止 Curator 误归档核心 persona |
| SE9 | `memory` tool 升级为 Hermes 契约：`add` / `replace` / `remove`；保留 `read` 为 m2t 扩展 | Review prompt 与 tool schema 一致 |
| SE10 | Curator 为 **Phase C**；A/B 阶段可手动 `media2text agent curator run` | 降低首期风险 |
| SE11 | 配置键 Hermes 同名：`memory.nudge_interval`、`skills.creation_nudge_interval`、`curator.*` | 便于对照 upstream 文档 |
| SE12 | Desktop **无** Gateway cron ticker；Curator 触发点 = **API 进程 idle tick** + CLI | 对齐 m2t 单 sidecar 模型 |

---

## 4. 目标架构

### 4.1 闭环时序

```
User send
  → AIAgent.run_conversation (foreground)
      · tool loop: m2t_* , memory, session_search, skills_list/view, skill_manage
      · persist trajectory
      · emit turn_end
  → [async] maybe_spawn_background_review
      · if memory nudge OR skill nudge
      · threading.Thread(daemon=True)
      · fork AIAgent(quiet, toolsets=memory+skills, skip_external_memory)
      · run_conversation(review_prompt, conversation_history=snapshot)
      · summarize actions → log / optional WS hint
  → [idle tick, Phase C] maybe_run_curator
```

### 4.2 模块映射

| Hermes | m2t 路径 | 阶段 |
|--------|----------|------|
| `agent/background_review.py` | `src/media2text/agent/background_review.py` | A |
| `agent/conversation_loop.py`（nudge + spawn 片段） | `src/media2text/agent/ai_agent.py` + `agent_turn_hooks.py` | A |
| `tools/memory_tool.py`（entry 语义） | `src/media2text/agent/memory_store.py` + `model_tools.py` | A |
| `tools/skill_manage*.py` | `src/media2text/agent/skill_manage.py` | B |
| `tools/skill_provenance.py` | `src/media2text/agent/skill_provenance.py` | B |
| `skills/.usage.json` 遥测 | `src/media2text/agent/skill_usage.py` | B |
| `agent/curator.py` | `src/media2text/agent/curator.py` | C |
| CLI `hermes curator` | `media2text agent curator …` | C |

### 4.3 Review fork 约束（与 upstream 一致）

- `max_iterations`: 16（可配置 `agent.review_max_iterations`）
- `suppress_status_output`: true
- Tool deny message: 非 whitelist 工具拒绝
- `summarize_background_review_actions`: 跳过 snapshot 中已有 tool 消息（#14944）
- stdout/stderr → devnull；失败 `logger.warning`，**不**影响主 turn 成功
- 主 turn **cancelled** 或 **无 final assistant 文本** → 不 spawn review

---

## 5. Nudge 触发逻辑

与 `hermes-agent/agent/conversation_loop.py` 对齐：

### 5.1 Memory nudge（按 user turn）

- 计数器：`_turns_since_memory`（**per `session_id`**，持久化于 SQLite，见 §10.1）
- 每收到一条 user message：`+= 1`
- 当 `_turns_since_memory >= memory.nudge_interval`（默认 **10**）且 `memory` 在 valid tools 且 memory enabled → `review_memory=True`，计数器归零
- Session 恢复：从 SQLite replay 时 **hydrate** 计数（`prior_user_turns % interval`），避免 CLI/Desktop 续聊永不触发

### 5.2 Skill nudge（按 tool iteration）

- 计数器：`_iters_since_skill`（per turn）
- 主 loop 每进入一次 tool-calling iteration：`+= 1`
- 若本轮调用了 `skill_manage`：`归零`（`tool_executor` 路径）
- Turn 结束：若 `_iters_since_skill >= skills.creation_nudge_interval`（默认 **10**）且 `skill_manage` 可用 → `review_skills=True`

### 5.3 合并 review

两者同轮触发 → 使用 `_COMBINED_REVIEW_PROMPT`（upstream 原文 vendored）。

### 5.4 配置

```yaml
memory:
  memory_enabled: true          # 已有；启用 MEMORY 注入 + tool
  user_profile_enabled: true    # USER.md
  soul_enabled: true            # m2t 扩展；SOUL 参与 volatile + memory target
  max_chars: 2200
  user_max_chars: 1375
  soul_max_chars: 4000          # 与 distill SOUL 体量一致；可 profile 覆盖
  nudge_interval: 10            # 0 = 禁用 memory review

skills:
  creation_nudge_interval: 10   # 0 = 禁用 skill review
  agent_skills_subdir: skills   # 相对 profile_dir

agent:
  review_max_iterations: 16
  review_enabled: true          # 总开关；false 跳过所有 background review
```

---

## 6. Memory 工具（Hermes 契约）

### 6.1 存储格式

- 文件：Markdown；逻辑条目以 **`§`** 分隔（与 Hermes 一致）
- 注入 prompt 时展示 `usage%` 与 char 计数

### 6.2 Actions

| action | 参数 | 行为 |
|--------|------|------|
| `add` | `target`, `content` | 追加条目；超限返回错误 + 当前 entries |
| `replace` | `target`, `old_text`, `content` | 子串唯一匹配条目后替换 |
| `remove` | `target`, `old_text` | 子串唯一匹配后删除 |
| `read` | `target` | **m2t 扩展**；Hermes 无 read（靠 prompt 注入） |

`target`: `memory` | `user` | `soul` — 均写入 **active profile**（§24.1.5）。

### 6.3 迁移

- 现有 `write` / `append`：**保留 6 个月兼容**，内部映射为 `replace` 整文件或 `add`；deprecated 字段写入 tool 返回 `deprecated: true`
- `memory_store.py` 实现 `MemoryStore` 类（条目级），与 Hermes API 对齐
- **Legacy 文件**：无 `§` 的现有 `MEMORY.md`（含 evolve 写入的 bullet）在首次 `add`/`replace`/`read` 时 **惰性归一化**为单条目或按空行拆条（实现选「整文件包一条 `§` 前缀」最小风险）；pytest 覆盖 evolve 产物

### 6.4 安全

保留现有 `scan_content`；SOUL 同样扫描。

---

## 7. skill_manage 工具

### 7.1 Actions（与 upstream 一致）

| action | 用途 |
|--------|------|
| `create` | 新 SKILL.md + frontmatter |
| `patch` | `old_string` / `new_string` |
| `edit` | 全文替换 SKILL.md |
| `delete` | 删除 skill 目录（**拒绝** pinned / bundled / distill 受保护名） |
| `write_file` | `references/`、`templates/`、`scripts/` 下子文件 |
| `remove_file` | 删除子文件 |

### 7.2 路径与命名

- 写入根：`{profile_dir}/skills/{name}/SKILL.md`
- `name`：kebab-case；与 `skills_list` 一致
- **Bundled**（`packages/agent-skills/`）：**只读**；任何写操作返回 `PROTECTED_SKILL`
- **Distill** `{slug}-perspective`：可 `patch` / `edit` / `write_file`（**禁止** `references/research/*`）；**不可** `delete`；默认 **pinned**
- **Pinned**（`.usage.json`）：同 distill 写删规则；**不可** `delete`

### 7.3 Provenance

```python
# skill_provenance.py
BACKGROUND_REVIEW = "background_review"

# skill_manage create 时：
if get_current_write_origin() == BACKGROUND_REVIEW:
    mark_agent_created(skill_name, profile_dir)
```

Foreground（用户对话中明确要求「写个 skill」）：`write_origin=foreground`，**不** `agent_created`。

### 7.4 Usage 遥测（`skills/.usage.json`）

Per skill entry:

```json
{
  "my-workflow": {
    "use_count": 0,
    "view_count": 12,
    "last_used_at": null,
    "last_viewed_at": "2026-06-07T12:00:00Z",
    "patch_count": 2,
    "state": "active",
    "pinned": false,
    "created_by": "agent",
    "agent_created": true,
    "write_origin": "background_review"
  }
}
```

递增点：

- `skill_view` → `view_count`
- skill 加载进 prompt（default_skills / slash）→ `use_count`
- `skill_manage` 写操作 → `patch_count`

Bundled / `packages/agent-skills` **不写** telemetry。

---

## 8. Background review

### 8.1 入口

```python
# agent/background_review.py — vendored from Hermes, adapted imports
def spawn_background_review_thread(
    agent: AIAgent,
    messages_snapshot: list[dict],
    *,
    review_memory: bool = False,
    review_skills: bool = False,
) -> Callable[[], None]: ...
```

`agent_turn_hooks.py` 在 `turn_end` emit **之后**、主 DB 连接关闭**之前** spawn；review 线程 **独立** `open_db()`。Nudge 计数持久化于 `sessions.agent_state_json`（见 §10.1）。

### 8.2 Prompts

- 完整 vendored：`_MEMORY_REVIEW_PROMPT`、`_SKILL_REVIEW_PROMPT`、`_COMBINED_REVIEW_PROMPT`
- m2t 附加一段 **scope hint**（追加在 prompt 末尾，不改动 core rubric）：

```text
Active profile: {workspace|creator:{sec_uid}}. All memory and skill writes
target this profile only. The distilled perspective skill "{slug}-perspective"
may be patched but do not delete or replace references/research/*.
```

### 8.3 Distill skill 保护

- Bootstrap 完成时：`skill_usage.pin("{slug}-perspective")`
- `metadata.hermes.protected: distill` 写入 frontmatter（自定义字段，skill_manage 检查）

### 8.4 用户可见反馈

- 默认：**仅** `logger.info` + 可选 `data/agent-review.log` 滚动日志
- Desktop v1：**不**弹 toast（避免打扰）；设置页可展示最近 review 摘要（Phase B+ UI，非阻塞）

### 8.5 Aux 模型（可选）

```yaml
auxiliary:
  review:
    provider: auto              # auto = 主模型
    model: auto
    timeout: 300
```

---

## 9. Curator（Phase C）

行为复制 [Hermes Curator 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator)：

### 9.1 触发

- `curator.enabled: true`（默认 **false** 直至 Phase C 稳定）
- `interval_hours: 168`（7 天）
- `min_idle_hours: 2`
- 触发点：`MonitorSupervisor` 或 API 后台 **idle tick**（无 in-flight agent turn ≥ `min_idle_hours` 且距上次 curator ≥ `interval_hours`）
- 首次安装：seed `last_run_at=now`，defer 一整 interval

### 9.2 两阶段

1. **Auto transition**：30d 未用 → `stale`；90d → `archive` 至 `skills/.archive/`
2. **LLM review fork**：`skill_view` + `skill_manage` + archive terminal；`max_iterations=8`；aux slot `auxiliary.curator`

### 9.3 管辖范围

- **仅** `agent_created: true` skills
- **不** touch：bundled、distill pinned、foreground-created

### 9.4 CLI

```bash
media2text agent curator status
media2text agent curator run [--dry-run] [--background]
media2text agent curator pin <skill>
media2text agent curator unpin <skill>
media2text agent curator restore <skill>
media2text agent curator rollback [--list]
```

### 9.5 备份

- 每次 mutating run 前：`skills/.curator_backups/{ts}/skills.tar.gz`
- `curator.backup.keep: 5`

---

## 10. AIAgent 改造要点

### 10.1 状态持久化（**非** AIAgent 实例字段）

m2t 每 turn 新建 `AIAgent`（`api/routes/agent.py::_run_turn`），计数器 **不得** 仅存于进程内存。

**SQLite**（`sessions` 表新增列，迁移脚本）：

```json
// sessions.agent_state_json
{
  "turns_since_memory": 3,
  "iters_since_skill": 0,
  "review_in_flight": false,
  "cached_system_prompt": null
}
```

- Scope：**per `session_id`**（O1 锁定）；compression 产生 child session 时 **复制** 计数到新 session 或按 product 决策归零（v1：**复制**，避免续聊永不触发）
- Hydrate：`prior_user_turns % nudge_interval` 写入 `turns_since_memory`（首 turn 或列缺失时）
- `_iters_since_skill`：仅本 turn 有效，**不**跨 turn 持久化

**Turn 内缓存**（SE4）：`cached_system_prompt` 存于 `agent_state_json` 或 turn 局部变量；`build_system_prompt` 在 binding/profile 未变时复用。Compression 或 profile 切换后 **invalidate**。

**Review 并发**：spawn 前若 `review_in_flight` → 跳过（或 coalesce 到下一轮）；线程 `finally` 清标志。

### 10.2 `run_conversation` 变更

1. Turn 开始：从 `agent_state_json` hydrate；user message 持久化后 `turns_since_memory += 1`；若达阈值且 `memory` 可用 → 置 `review_memory` 标志
2. Tool loop：每次 **LLM 返回 tool_calls**（非每个并行 tool worker）`_iters_since_skill += 1`；`skill_manage` 成功执行后归零
3. **压缩前**快照：`messages_snapshot = copy.deepcopy(messages)`（在 `maybe_post_turn_compress` **之前**）
4. `finally` 顺序：`maybe_post_turn_compress` → `maybe_auto_title` → `turn_end` emit → `maybe_spawn_background_review(snapshot)` → return
5. Review 线程：`open_db(cfg)` 新连接；`AIAgent(quiet=True, write_origin=background_review)`；禁止复用 foreground `SessionDB`（连接已 close）

**M7a 限制**：`skill_manage` 未交付前，skill nudge **永不触发**（`"skill_manage" in valid_tool_names` 为 false，对齐 Hermes）。

### 10.3 Tool whitelist

```python
REVIEW_TOOL_NAMES = {"memory", "skill_manage", "skills_list", "skill_view"}
```

Review fork 注册 OpenAI tools 仅上述子集；`handle_function_call` 层拒绝其它。

### 10.4 Toolset 变更

```python
_HERMES_NAMES = [
    "memory", "session_search",
    "skills_list", "skill_view", "skill_manage",
]
```

`m2t-core` 默认包含 `skill_manage`（可通过 profile `disabled_tools` 关闭）。

---

## 11. 数据布局

```
data/.agent/                          # workspace profile
  MEMORY.md USER.md SOUL.md
  skills/
    .usage.json
    .archive/
    .curator_backups/
    {agent-created-skill}/SKILL.md
  logs/curator/{run_id}/REPORT.md     # Phase C

data/creators/{sec_uid}/.agent/       # creator profile（同上）
  skills/
    {slug}-perspective/               # distill；pinned
    {agent-created-skill}/
```

---

## 12. 交付分期

| 阶段 | 内容 | 验收 |
|------|------|------|
| **M7a** | Memory Hermes 契约；nudge 计数 + hydrate；`background_review.py`；`ai_agent` hooks；配置项 | S1–S6 |
| **M7b** | `skill_manage` + provenance + usage telemetry；review 可 patch skill；distill pin | S7–S11 |
| **M7c** | `curator.py` + idle tick + CLI + backup/rollback | S12–S15 |

**Epic：** 建议新增 `agent-self-evolution` manifest，或作为 `agent-hermes` 的 M7 追加 issue 系列。

---

## 13. Success Criteria

| ID | 标准 | 验证 |
|----|------|------|
| S1 | `memory(action=add)` 条目以 `§` 分隔；下一会话 volatile 可见 | pytest |
| S2 | 第 10 个 user turn 后 spawn review（`nudge_interval=10`） | mock LLM + thread join |
| S3 | Review fork **不**调用 `m2t_*` 工具（whitelist deny） | pytest |
| S4 | Review fork 使用与主 turn 相同 model/provider | 断言 mock 调用参数 |
| S5 | 主 turn cancelled → 无 review thread | pytest |
| S6 | Memory review 写入 active creator profile；另一 creator 不可见 | H11 扩展 |
| S7 | `skill_manage patch` 在 creator `skills/` 落盘；`skills_list` 可见 | pytest |
| S8 | Foreground `create` 不标 `agent_created`；background `create` 标记 | `.usage.json` 断言 |
| S9 | `skill_manage delete` 拒绝 pinned distill skill | pytest |
| S10 | 用户纠正口吻后 review patch `{slug}-perspective` 的 pitfall 段 | 集成 mock |
| S11 | `write`/`append` 仍可用且 deprecation 提示 | pytest |
| S12 | Curator dry-run 不修改磁盘 | CLI |
| S13 | 90d 未用 agent skill → `.archive/` | 时间 mock |
| S14 | Curator 不 touch bundled / distill pinned | pytest |
| S15 | `curator rollback` 恢复备份 | CLI 集成 |

---

## 14. 非目标

- Honcho / Mem0 / 其它 external memory provider（v3）
- Gateway 式 `/curator` slash command（Desktop 用 CLI + 设置页）
- 将 distill/evolve 合并进 background review（保持 job 队列）
- 自动 evolution 触发 **跨博主** 写盘
- Node sidecar 任何逻辑
- 用户消息附件进 review（follow Agent Pane defer）

---

## 15. 安全与合规

- Review fork **无** network 写权限超出主 agent（仅 LLM API + 本地文件）
- `skill_manage` 路径遍历检查：拒绝 `..`、绝对路径
- Curator archive **不** delete；仅移动至 `.archive/`
- 日志不落盘用户全文；review 摘要仅 tool action 一行
- 与既有 `scan_content` 一致

---

## 16. 测试策略

| 层 | 文件 |
|----|------|
| Unit | `tests/unit/test_memory_store_entries.py` |
| Unit | `tests/unit/test_background_review.py`（vendored tests 适配） |
| Unit | `tests/unit/test_skill_manage.py` |
| Unit | `tests/unit/test_skill_provenance.py` |
| Unit | `tests/unit/test_agent_nudge_counters.py` |
| Unit | `tests/unit/test_agent_state_persistence.py`（SQLite hydrate / compression handoff） |
| Unit | `tests/unit/test_review_snapshot_order.py`（压缩前快照） |
| Unit | `tests/unit/test_curator_transitions.py`（Phase C） |
| Integration | `tests/unit/test_api_agent_review_e2e.py`（mock LLM） |

命令：

```bash
pytest tests/unit/test_memory_store_entries.py \
       tests/unit/test_background_review.py \
       tests/unit/test_skill_manage.py \
       tests/unit/test_agent_nudge_counters.py -v
```

---

## 17. 开放项（已锁定）

| ID | 问题 | 决定 |
|----|------|------|
| O1 | Nudge 计数 scope | **per `session_id`** + `sessions.agent_state_json` 持久化 |
| O2 | Review 失败是否 WS 通知 | **v1 仅日志**；后续设置页 |
| O3 | `soul` 是否参与 memory review prompt | **是** |
| O4 | Workspace profile 是否默认开启 skill review | **是**（M7b 起 `skill_manage` 可用后） |
| O5 | Curator 默认 `enabled` | **false** 至 Phase C |

---

## 18. 文档与变更联动

落地后更新：

- [CLAUDE.md](../../../CLAUDE.md) Desktop Agent 小节（自进化 + CLI）
- [config.example.yaml](../../../config.example.yaml) `memory.nudge_interval`、`skills.*`、`curator.*`
- [x] [2026-06-06-m2t-desktop-agent-hermes-refactor-design.md](./2026-06-06-m2t-desktop-agent-hermes-refactor-design.md) §4.2 Curator 非目标一行 → 指向本规格 §9（父规格合入 main 时同步）
- 新 epic manifest `docs/issues/epic-manifests/agent-self-evolution.yaml`

---

## 19. 审阅清单（已确认 2026-06-07）

| # | 问题 | 结论 |
|---|------|------|
| 1 | 方案 A 三期 M7a→c | **同意** |
| 2 | Distill skill 可 patch、不可删 + 默认 pin | **同意** |
| 3 | Memory 契约 add/replace/remove + write/append 兼容 | **同意** |
| 4 | Curator 默认关闭至 Phase C | **同意** |

下一步：生成 [`2026-06-07-m2t-agent-self-evolution.md`](../plans/2026-06-07-m2t-agent-self-evolution.md) 实施计划。

---

## 20. 工程审阅修订（/plan-eng-review）

### 20.1 架构结论

| ID | 严重度 | 问题 | 修订 |
|----|--------|------|------|
| ER1 | P1 | `AIAgent` 每 turn 新建，§10.1 实例字段无法跨 turn 保留 nudge | §10.1 改为 `sessions.agent_state_json` |
| ER2 | P1 | `finally` 内先 `maybe_post_turn_compress` 再 `turn_end`，review 若用压缩后会话会丢上下文 | §10.2 压缩**前** deepcopy 快照 |
| ER3 | P1 | `_run_turn` `finally: conn.close()` 与 review 线程竞态 | review 独立 `open_db()`，spawn 在 close 前排队 |
| ER4 | P2 | 无 `_cached_system_prompt`；每 turn 重建 system（`ai_agent.py:100-110`） | M7a 增加 session 级 prompt 缓存 + invalidate 规则 |
| ER5 | P2 | M7a 无 `skill_manage` 时不应触发 skill review | §10.2 M7a 门控 |
| ER6 | P2 | §7.2「distill 只读」与 §1.2/8.2「可 patch」矛盾 | §7.2 分层：bundled 只读；distill 可写 SKILL、禁删 research |
| ER7 | P3 | 并行 `ThreadPoolExecutor` 跑 tool；nudge 按 **iteration** 计非 per-tool | §10.2 明确按 LLM tool_call 轮次 |
| ER8 | P3 | 连续快速 turn 可能叠多个 review 线程 | `review_in_flight` 锁 |

### 20.2 已有代码复用

| 能力 | 路径 | 本规格用法 |
|------|------|------------|
| Memory 写盘 + scan | `memory_store.py` | 扩展 `MemoryStore` § 条目 |
| Tool 分发 | `model_tools.py` | add/replace/remove；`write_origin` |
| Aux 摘要 | `auxiliary_client.py` | 可选 review/curator aux（§8.5） |
| 压缩 | `context_compressor.py` | 快照须在 `maybe_post_turn_compress` 前 |
| Profile 根 | `profile_resolver.py` | review scope hint |
| Turn 后台 | `api/routes/agent.py` | hooks 注入点 |
| Distill pin | evolve/bootstrap 落盘时 | `skill_usage.pin`（M7b） |

### 20.3 明确不做（审阅补充）

- Review 使用独立 cheap model（v1 与主模型一致，S4；`auxiliary.review` 仅配置预留）
- 跨 `session_id` 合并 nudge 计数
- M7a 交付 `skill_manage` 或 Curator
- Gateway / WS review toast（O2）

### 20.4 并行实施建议

| Lane | 阶段 | 模块 | 依赖 |
|------|------|------|------|
| A | M7a | `memory_store` § + migration | — |
| B | M7a | `hermes_state` migration + `agent_state_json` | — |
| C | M7a | `background_review.py` + `agent_turn_hooks.py` | B |
| D | M7a | `ai_agent.py` 挂钩 + prompt cache | A, C |
| E | M7b | `skill_manage` + provenance + usage | M7a |
| F | M7c | `curator.py` + idle tick + CLI | M7b |

Lane A+B 可并行；C 依赖 B；D 依赖 A+C。M7b/M7c 顺序执行。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | not run |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | CLEAR | 8 issues, 0 critical gaps (post-revision) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | backend-only |
| DX Review | `/plan-devex-review` | Developer experience | 0 | — | not run |

- **UNRESOLVED:** 0（§19 + ER1–ER8 已写入规格）
- **VERDICT:** ENG CLEARED — ready for implementation plan
