# P1：转注 Work 一键启动（自动 Gateway + 首次向导）

> **GitHub**：[#37](https://github.com/oychao1988/media2text/issues/37)  
> **建议分支**：`issue-37-zhuanzhu-p1-gateway`  
> **依赖**：[#35](https://github.com/oychao1988/media2text/issues/35) 已合并  
> **依赖**：`desktop/zhuanzhu-work`（Issue #35）已合入 `main`

## 背景

P0 开发壳要求用户手动 `openclaw gateway run`。P1 目标：**双击应用即可聊天**，无需终端。参考 [openclaw-desktop](https://github.com/agentkernel/openclaw-desktop) 与 [docs/openclaw-integration.md](../openclaw-integration.md) P1 里程碑。

## 验收标准

### 自动 Gateway

- [ ] 应用启动时检测 `127.0.0.1:18789` 是否已有健康 Gateway；若无则 **子进程启动** `openclaw gateway run --port 18789 --bind loopback`。
- [ ] 子进程使用 **Node ≥22.14**（优先：`desktop/zhuanzhu-work/resources/node` 若存在；否则 `which node` / `nvm` 当前 node；文档说明开发态要求）。
- [ ] 设置子进程环境：`OPENCLAW_CONFIG_PATH` 指向 `~/.openclaw/openclaw.json`（或 Application Support 路径，见实现注释）。
- [ ] 启动界面显示「正在启动 OpenClaw Gateway…」直至 `openclaw health` 或 HTTP probe 成功（超时 60s 可读错误）。
- [ ] 应用退出（macOS 全关窗口 / quit）时 **终止** 由本应用拉起的 Gateway 子进程（勿误杀用户独立启动的 gateway，可用 PID 文件或父进程标记）。

### 首次运行向导

- [ ] 若 `~/.openclaw/openclaw.json` 不存在或缺少 `gateway.auth.token` / 模型 API 配置，显示 **向导页**（可单独 `wizard.html` 或内嵌路由）。
- [ ] 向导最少一步：说明需配置模型 Provider API Key（文案 + 链接官方文档）；提供「打开配置文件目录」或「稍后配置」。
- [ ] 「稍后配置」仍进入主界面，但聊天失败时 banner 提示配置路径。
- [ ] 合规：勾选「已阅读免责声明」后写入 `data/.compliance-accepted` 等价文件（路径与 `media2text compliance accept` 一致，相对未来 workspace）。

### 主界面

- [ ] Gateway ready 后加载现有聊天 UI；行为与 P0 一致（HTTP chat）。
- [ ] `desktop/zhuanzhu-work/README.md` 更新为「普通用户」与「开发者」两节。

### 测试

- [ ] 保留或扩展 `e2e/gui-smoke.mjs`：可选环境变量 `ZHUAZHU_SKIP_SPAWN=1` 当 Gateway 已手动运行时跳过 spawn。
- [ ] 文档记录：无系统 `openclaw` 时的降级提示（安装 YonClaw 或 `npm i -g openclaw`）。

## 验证命令

```bash
source ~/.nvm/nvm.sh
# 确保 18789 无占用或允许应用重启
cd desktop/zhuanzhu-work && npm run dev
# 应自动起 Gateway，窗口内发送「回复两个字：收到」成功

# E2E（Gateway 已起时可 SKIP_SPAWN）
ZHUAZHU_SKIP_SPAWN=1 node e2e/gui-smoke.mjs
```

## 非目标范围

- 安装包 `.dmg` / `.exe`（P2）
- 内置完整 OpenClaw npm 包到 `resources/`（P2 可做 `prepare-bundle` 脚本占位）
- WebSocket 流式、media2text CLI 集成（P3）
- Apple 签名 / 公证

## 实现提示

- 复用 `main.js` 的 `readGatewayToken` / `openclawChat`。
- `child_process.spawn` + `detached: false`；日志写入 `~/Library/Logs/转注Work/gateway.log`（可选）。
- 参考 YonClaw LaunchAgent 的 Node 版本坑：子进程 PATH 前置 bundled node。
