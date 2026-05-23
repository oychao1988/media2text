# P8：转注 Work 分发（签名、公证、自动更新）

> **GitHub**：[#47](https://github.com/oychao1988/media2text/issues/47)  
> **建议分支**：`issue-47-zhuanzhu-p8-distribution`  
> **依赖**：P7 bundled runtime 建议先合并

## 背景

P2 产出未签名 dmg，用户需右键打开。本单完善 **可公开发布** 的分发链路（可先用 ad-hoc / Developer ID，CI 文档化）。

## 验收标准

### 签名与公证

- [ ] `electron-builder` mac 配置支持 `CSC_*` / Apple 证书（env 驱动，**不**提交证书）。
- [ ] README 说明本地签名与 `notarize` 步骤；无证书时构建仍可通过 `CSC_IDENTITY_AUTO_DISCOVERY=false` 产出未签名包。
- [ ] CI workflow（可选）：tag 触发 build artifact upload（secrets 缺失时 skip 并文档说明）。

### 自动更新

- [ ] 集成 `electron-updater` + GitHub Releases provider（或 generic URL）；`package.json` publish 配置。
- [ ] 应用内「升级」入口（侧栏底部占位可激活）或启动时 silent check（PR 说明策略）。

### 文档

- [ ] 发布 checklist：版本号、`CHANGELOG` 片段、上传 Release assets。

## 验证命令

```bash
cd desktop/zhuanzhu-work
npm run package:mac
# 有证书：spctl -a -vv -t install dist/mac/转注\ Work.app
# 无证书：确认文档路径可构建未签名 dmg
```

## 非目标范围

- Microsoft Store / Mac App Store
- 差分更新优化
- 多 channel（beta/stable）完整 UI
