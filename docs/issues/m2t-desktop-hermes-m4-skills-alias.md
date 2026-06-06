# m2t-desktop Hermes M4：Skills 渐进披露 + /api/chat 兼容层收尾

## 背景

M3 完成记忆与压缩。M4 落地 **agentskills.io 三级披露**（`skills_list` / `skill_view`），禁止 startup 全量注入 SKILL.md；并完成 `/api/chat/*` → `/api/agent/*` **文档与测试**收尾（6 个月 deprecated alias）。

**参考**：Hermes §11、H12（workspace profile 路径）、规格 M4

**依赖**：M1 tool 拦截骨架；M3 推荐已合并。

## 验收标准

### Task 1 — Skills 索引

- [x] `build_skills_index()` 扫描 `packages/agent-skills/`（M4 仅全局根；博主根 M5a 扩展）
- [x] stable tier 仅 Level-0 name + description；全文经 `skill_view` 按需
- [x] 废弃 v1 sidecar startup 全量 `SKILL.md` 注入

### Task 2 — skill_view 路径

- [x] `skill_view(name)` / `skill_view(name, path)` 读 references/
- [x] 单测：stable prompt token 不含完整 SKILL 正文

### Task 3 — API 兼容

- [x] 全部 chat routes alias 测试覆盖；OpenAPI/README 标记 deprecated
- [x] `media2text` CLI help 指向 `/api/agent/*`

### Task 4 — 文档

- [x] 更新 [m2t-desktop-design](../superpowers/specs/2026-06-04-m2t-desktop-design.md) §4.6 指向 Hermes 规格

### 测试

- [x] `pytest tests/unit/test_agent_skills.py -v -m agent`

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_agent_skills.py tests/unit/test_api_agent_threads.py -v -m "agent or desktop"
```

## 非目标范围

- 博主 `.agent/skills/` 双根索引（M5a）
- nuwa 蒸馏产物（M5b）
- Terminal / delegate（M6）

## 实现备注

- 分支：`issue-184-hermes-m4-skills`
- GitHub Issue: [#184](https://github.com/oychao1988/media2text/issues/184)
