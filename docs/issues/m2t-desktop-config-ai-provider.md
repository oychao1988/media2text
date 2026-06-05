# m2t-desktop：系统配置 AI Provider 直连 Key、性能与 Agent 连通

## 背景

桌面端「系统配置 · AI」段需支持在 UI 内直接填写 / 保存 LLM Provider 的 API Key（写入项目 `.env`），并在列表与编辑表单中回显已保存 Key、展示连通性状态。联调中发现：

1. **配置页 / 编辑 Provider 极慢**：`GET /api/config` 对每个 Provider 同步做 LLM 连通性探测（可达数秒）。
2. **添加 Provider 后无法进入编辑**：`addProvider()` 触发全量 refresh，覆盖未保存草稿。
3. **直播 Tab 摘要模型下拉失效**：`config.yaml` 中 `default_provider` / `default_model` 为 `null` 时，下拉 `value` 与选项不匹配。
4. **Agent 报未配置 API Key**：Agent sidecar 为独立 Node 进程，`M2T_LLM_KEYS` 恒为空且未注入 `.env` 变量；与 AI Tab 已保存 Key 脱节。
5. **GET /api/creators 500**：误用 `LiveSessionRow.session_id`（应为 `id`）。
6. **Sidecar 稳定性**： stale `media2text serve` 缺少 `api_key` 字段时需重启；Agent sidecar EPIPE / tsx 路径问题。

**参考**

- Desktop 配置 IA：[config-manage-ia.md](../superpowers/specs/2026-06-04-m2t-desktop-config-manage-ia.md)
- Summarize LLM 配置：`config.yaml` → `summarize.llm`

## 验收标准

### A — AI Provider 配置 UX（P0）

- [x] AI Tab：Provider 编辑表单支持 API Key 明文输入与显示/隐藏；保存后写入 `.env` 对应 `api_key_env`。
- [x] `GET /api/config` 的 `llmProviders[]` 含 `api_key`（loopback 专用），重新打开编辑可回显已保存 Key。
- [x] 保存 Provider（PATCH）时执行连通性探测并更新 `connected`；**GET 默认不探测**（列表显示「未检测」直至保存）。
- [x] 添加 Provider 后立即可编辑草稿，不因 refresh 丢失新行。
- [x] Tauri Python sidecar：若 `:8765` 上已有 serve 但 `/api/config` 无 `api_key` 字段，自动 kill 并重启。

### B — 直播 Tab 摘要下拉（P0）

- [x] `default_provider` / `default_model` 为 null 时，API 与前端归一化为第一个 Provider 及其第一个 model。
- [x] 切换「摘要服务」时同步更新「摘要模型」选项；下拉可正常选择与保存。

### C — Agent LLM Key 注入（P0）

- [x] 启动 / 重启 Agent sidecar 时，从 `/api/config` 注入 `M2T_LLM_KEYS`（provider 名 → key）及 `api_key_envs` 环境变量。
- [x] AI Tab 已配置且保存 Key 后，Agent 输入框发消息不再报「未配置 API Key」（需 sidecar 重载或重启 Desktop）。

### D — API 修复与 Sidecar 稳定（P1）

- [x] `GET /api/creators` 不再 500（active session 字段 `id`）。
- [x] `read_env_var` 优先读 `.env` 文件，避免 stale `os.environ` 导致探测误报未连通。
- [x] Agent `start-sidecar.mjs`：pnpm tsx 路径回退、EPIPE 忽略；sidecar bundle 重建。

### 测试

- [x] `pytest tests/unit/test_api_config_dto.py tests/unit/test_api_creators_list.py -v -m desktop`
- [x] `pnpm --filter m2t-desktop test -- src/features/agent/agentSidecar.test.ts`

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_api_config_dto.py tests/unit/test_api_creators_list.py -v -m desktop

pnpm --filter m2t-desktop test -- src/features/agent/agentSidecar.test.ts

# 配置 GET 应秒级返回（无 probe）
curl -s http://127.0.0.1:8765/api/config | python3 -c "
import json,sys
p=json.load(sys.stdin)['config']['llmProviders'][0]
print('api_key' in p, p.get('connected'))
"

curl -s http://127.0.0.1:8765/api/creators | python3 -c "import json,sys; print(json.load(sys.stdin)['ok'])"

# 人工（Tauri）
pnpm --filter m2t-desktop tauri dev
# 1. 系统配置 · AI：编辑 Provider，保存 Key，重开可见；保存后见连通状态
# 2. 系统配置 · 直播：摘要服务/模型下拉可选
# 3. Agent 输入消息，无「未配置 API Key」错误
```

## 非目标范围

- 不在 GET `/api/config` 恢复全量连通性探测（避免拖慢配置页；可选后续加「检测连通性」按钮）。
- 不改造 CLI `summarize` / `auth` 子命令的 Key 管理流程。
- 不将 API Key 暴露到非 loopback 或提交到 git（`.env` 仍 gitignore）。
- 不在本单实现 Agent `context.refresh` 热更新 LLM Key（仍依赖 sidecar 重启 / `requestAgentReload`）。

## 待确认问题

无。
