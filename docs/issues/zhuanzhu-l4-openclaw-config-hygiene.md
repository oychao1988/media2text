# L4：OpenClaw 配置卫生检查（agents 膨胀 + skills symlink）

> **GitHub**：[#59](https://github.com/oychao1988/media2text/issues/59)  
> **建议分支**：`issue-59-zhuanzhu-openclaw-hygiene`  
> **依赖**：无（可独立）；建议与 L1 联调验证 Gateway 启动时间  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

本机 `~/.openclaw/openclaw.json` 中 `agents.list` 约 **729** 条（大量历史 `ozon-user-*`），Gateway 冷启动 ~5–7s。每条聊天消息触发 **skills 目录 symlink 扫描**（gateway.log 中 20+ 条 `symlink-escape` skip），增加每轮 ~0.3–0.5s 固定开销。

此问题位于 **用户配置**，但转注 Work 作为 OpenClaw 桌面壳应提供 **doctor / 向导** 帮助发现与修复，而不是要求用户手工编辑 JSON。

## 验收标准

### CLI / 应用内 doctor

- [ ] 新增检查项（`media2text doctor --json` **或** `desktop/zhuanzhu-work` bootstrap/doctor IPC，PR 选型并统一 `--json` 字段）：
  - `openclaw_agents_count`：> 阈值（默认 50）时 `warn: true`，附 `hint`
  - `openclaw_skills_symlink_escape`：扫描 `~/.openclaw/skills` 下指向 `~/.agents/skills` 等的 symlink，列出前 N 个路径
- [ ] JSON 示例字段：

  ```json
  {
    "openclaw_config_hygiene": {
      "agents_list_count": 729,
      "agents_list_warn": true,
      "skills_symlink_issues": 23,
      "hints": ["…"]
    }
  }
  ```

### 修复指引（文档 + 可选脚本）

- [ ] `docs/openclaw-integration.md` 或 `desktop/zhuanzhu-work/README.md` 增加「配置卫生」：
  - 如何备份 `openclaw.json`
  - 如何归档/移除不再使用的 `agents.list` 条目（**不**自动删用户数据，仅文档 + 可选 `--dry-run` 脚本）
  - skills：建议将 skill 复制到 `~/.openclaw/skills/` 或移除逃逸 symlink
- [ ] 可选：`scripts/openclaw-config-hygiene.sh --dry-run` 输出 JSON 报告（与 doctor 字段对齐）。

### 转注 Work UI（最小）

- [ ] 若 bootstrap 已展示 doctor 警告，增加上述 warn 的 **一行摘要**（可点击打开配置目录）；不要求完整修复向导。

## 验证命令

```bash
media2text doctor --json | jq '.openclaw_config_hygiene // .checks'

# 或
cd desktop/zhuanzhu-work && npm run dev
# bootstrap 面板可见 agents/skills 警告（在故意膨胀的配置上）

bash scripts/openclaw-config-hygiene.sh --dry-run  # 若实现
```

## 非目标范围

- **不**自动修改 `~/.openclaw/openclaw.json`（无用户确认不写盘）
- **不**删除 `~/.openclaw/agents/` 下用户 workspace
- 不解决 OpenClaw 上游「每轮全量 skills rescan」（可记 `hints` 建议升级 openclaw）
- 不包含模型切换

## 待确认问题

- doctor 放在 `media2text` CLI 还是仅 zhuanzhu IPC？（建议 CLI 可独立跑，zhuanzhu 复用同一 lib）
