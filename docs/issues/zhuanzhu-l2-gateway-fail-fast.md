# L2：转注 Work Gateway 子进程 fail-fast（避免无效等待）

> **GitHub**：[#57](https://github.com/oychao1988/media2text/issues/57)  
> **建议分支**：`issue-57-zhuanzhu-gateway-fail-fast`  
> **依赖**：P1/P7 Gateway 打包路径（`lib/gateway.js`）  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

`lib/gateway.js` 在 spawn `openclaw gateway run` 后调用 `waitForGatewayReady()`，默认超时 **60s**。若 bundled Node 版本不满足、openclaw 二进制缺失或子进程秒退，UI 会长时间卡在 splash/「等待 Gateway」，用户误以为「聊天慢」或应用卡死。

PR #55 已修复 Node 22.14 → 22.22.3，但 **fail-fast** 仍未实现：应在子进程 **exit / error** 时立即 reject，并给出可行动错误（Node 版本、路径、stderr 摘要）。

## 验收标准

### 行为

- [ ] `spawnGateway` / `ensureGateway`：监听 `child.on('exit')` / `error`；若在未 ready 前退出，**立即**失败（不再等到 60s 超时）。
- [ ] 错误信息包含：exit code、最近若干行 `gateway.log` 或 stderr（脱敏 token）。
- [ ] Node 版本低于 `MIN_NODE`（22.16）时，在 spawn **前** fail（已有检测则补测试/文档）。
- [ ] 正常启动路径不变：`/health` ready 后 resolve；`GATEWAY_START_TIMEOUT_MS` 仍作为「慢启动」上限（可保留 60s 或 PR 建议降至 30s 并说明）。

### 测试

- [ ] 单元测试：mock child 立即 exit → `ensureGateway` 在 <2s 内 reject（`desktop/zhuanzhu-work/test/` 或现有 test 目录）。
- [ ] 文档：`desktop/zhuanzhu-work/README.md`「排错」增加 fail-fast 错误样例。

## 验证命令

```bash
cd desktop/zhuanzhu-work
npm test 2>/dev/null || node --test test/gateway*.test.js  # 以 PR 实际路径为准

# 手工：故意指向无效 openclaw 路径（dev 文档步骤）
ZHUANZHU_SKIP_SPAWN=0 npm run dev
# 观察 <5s 内 splash 报错而非 60s
```

## 非目标范围

- 不实现 Gateway 自动重启/看门狗（另开单）
- 不修改 OpenClaw gateway 启动参数
- 不优化 Gateway 正常冷启动耗时（~5–7s）
