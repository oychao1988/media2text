---
epic: agent-context-attachments
issue: 259
github: 259
branch: issue-259-agent-context-epic-acceptance
depends_on: [254, 255, 256, 257]
spec: docs/superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md
acceptance: docs/superpowers/verification/2026-06-09-m2t-desktop-agent-context-attachments-acceptance.md
---

# m2t-desktop Agent 上下文 Epic 验收（P2c）

## 背景

Epic **Agent 身份联动与多文档上下文**（规格 2026-06-09）在 P0–P2 Issue 合并后，需填写验收表、跑 epic manifest，并对 spec §3–§6 验收项（A/B/C/D）签署。

**参考**

- 规格：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)
- 验收表（本 Epic 创建）：`docs/superpowers/verification/2026-06-09-m2t-desktop-agent-context-attachments-acceptance.md`
- Epic manifest：`docs/issues/epic-manifests/agent-context-attachments.yaml`

**依赖**：P0 [#254](https://github.com/oychao1988/media2text/issues/254)、P1 [#255](https://github.com/oychao1988/media2text/issues/255)、P1b [#256](https://github.com/oychao1988/media2text/issues/256)、P2 [#257](https://github.com/oychao1988/media2text/issues/257) 已合并；sidecar sync [#258](https://github.com/oychao1988/media2text/issues/258) 可选

## 验收标准

### 文档

- [x] 创建/更新 `docs/superpowers/verification/2026-06-09-m2t-desktop-agent-context-attachments-acceptance.md`
- [x] 勾选 spec **A1–A5、B1–B5、C1–C3、D1–D5**；标注自动/手工证据
- [x] `docs/issues/README.md` 本 Epic 表填 PR 链接
- [x] 各 Issue md 文件验收项 `[x]` 与 GitHub Issue 关闭状态一致

### Epic manifest

- [x] `docs/issues/epic-manifests/agent-context-attachments.yaml` 含 issues 列表与 verify steps
- [x] `python scripts/epic_verify.py agent-context-attachments` **PASS**

### 自动化闸门

- [x] `pnpm --filter m2t-desktop test` 全绿
- [x] `pytest tests/unit/test_api_agent_threads.py tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop` 全绿
- [x] 各 Issue `python scripts/issue_verify.py --issue N` 全 PASS（manifest 内 #254–#258）

### 手工冒烟（Tauri + sidecar，记录于验收表）

- [x] 左栏点博主 → draft 联动（A1–A4）（自动化覆盖；Tauri 发版前可补录）
- [x] 选场次 → chips；× 保留 sessionId（B1–B3）
- [x] 转写/摘要 Tab 过滤 turn（C1–C3）
- [x] `@` 跨博主选文档（D1–D3）
- [x] activate 失败 toast（E5，可选 fault injection）

### Epic 签署

- [x] 验收表 **VERDICT: PASS**（或列明 deferred 非目标）

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
python scripts/epic_verify.py agent-context-attachments
```

## 非目标范围

- 新功能开发（仅验收与文档）
- B 站 archive/dynamic `@` 列表
- Design review 未做项的 UI polish（除非 blocker）

## 依赖与顺序

- **依赖**：P0、P1、P1b、P2 均已 merge main
- **阻塞**：Epic 关单

## 实现备注

- 分支：`issue-259-agent-context-epic-acceptance`
- GitHub Issue: [#259](https://github.com/oychao1988/media2text/issues/259)
