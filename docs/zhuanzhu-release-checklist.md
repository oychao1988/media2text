# 转注 Work 发布 Checklist（P8）

GitHub Issue：[#47](https://github.com/oychao1988/media2text/issues/47)

## 1. 版本与变更

- [ ] 更新 `desktop/zhuanzhu-work/package.json` 的 `version`
- [ ] 在仓库 `CHANGELOG.md`（或 Release Notes）写该版本要点
- [ ] 确认 `resources/bundle-manifest.json` pin 版本与 prepare-bundle 一致

## 2. 本地构建

```bash
cd desktop/zhuanzhu-work
npm install
npm run prepare-bundle
npm run verify-bundle
```

**未签名（默认 CI / 无证书）**

```bash
npm run package:mac:unsigned
# 产出 dist/转注 Work-<version>.dmg + latest-mac.yml + *.blockmap
```

**签名 + 公证（Developer ID）**

```bash
export CSC_LINK="$HOME/certs/zhuanzhu.p12"          # 或 base64 解码后的路径
export CSC_KEY_PASSWORD="***"
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="****"
export APPLE_TEAM_ID="XXXXXXXXXX"

npm run package:mac
spctl -a -vv -t install "dist/mac/转注 Work.app"
```

## 3. GitHub Release

推荐 tag：`zhuanzhu-v<version>`（例 `zhuanzhu-v0.1.1`）。

上传资产（electron-updater 需要 yml + blockmap）：

| 文件 | 说明 |
|------|------|
| `zhuanzhu-work-<version>.dmg` | 安装包（ASCII 文件名，供 auto-updater） |
| `zhuanzhu-work-<version>.dmg.blockmap` | 差分块映射 |
| `latest-mac.yml` | 自动更新元数据 |

```bash
gh release create "zhuanzhu-v0.1.1" \
  --title "转注 Work 0.1.1" \
  --notes-file /tmp/release-notes.md \
  desktop/zhuanzhu-work/dist/zhuanzhu-work-0.1.1.dmg \
  desktop/zhuanzhu-work/dist/zhuanzhu-work-0.1.1.dmg.blockmap \
  desktop/zhuanzhu-work/dist/latest-mac.yml
```

或 push tag 触发 [`.github/workflows/zhuanzhu-release.yml`](../.github/workflows/zhuanzhu-release.yml)（无 Apple secrets 时产出**未签名**包）。

## 4. 发布后验证

- [ ] 全新机器 / 虚拟机：安装 dmg，无全局 openclaw 可启动 Gateway
- [ ] 侧栏「升级」：旧版启动后应检测到新版本（或显示已是最新）
- [ ] `~/Library/Logs/转注Work/gateway.log` 无异常
- [ ] OpenClaw 配置 `~/.openclaw` 升级后仍保留

## 5. CI Secrets（可选）

| Secret | 用途 |
|--------|------|
| `ZHUANZHU_MAC_CERT_BASE64` | Developer ID `.p12` base64 |
| `ZHUANZHU_MAC_CERT_PASSWORD` | 证书密码 |
| `APPLE_ID` | 公证 Apple ID |
| `APPLE_APP_SPECIFIC_PASSWORD` | 应用专用密码 |
| `APPLE_TEAM_ID` | Team ID |

缺失时 workflow 自动 `CSC_IDENTITY_AUTO_DISCOVERY=false`，仍上传未签名 dmg。
