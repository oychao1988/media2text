# 转注 Work E2E 截图

P0/P1 手动或 `e2e/gui-smoke.mjs` 验证时的参考截图目录。

| 文件 | 说明 |
|------|------|
| `01-electron-ready.png` | 聊天主界面就绪 |
| `02-composer-filled.png` | 输入测试消息 |
| `03-chat-reply.png` | 收到 assistant 回复 |

复现：`cd desktop/zhuanzhu-work && ZHUANZHU_SKIP_SPAWN=1 node e2e/gui-smoke.mjs`（需 Gateway 在 127.0.0.1:18789）。
