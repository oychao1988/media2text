# 个人阿里云盘 Web API 基础能力（登录 + 客户端 + 冒烟）

GitHub: [#65](https://github.com/oychao1988/media2text/issues/65)  
分支: `issue-65-aliyundrive-cloud-foundation`  
PR: [#66](https://github.com/oychao1988/media2text/pull/66)

## 背景

media2text 需要将直播/作品录制文件备份到用户个人阿里云盘（alipan.com）。官方未开放个人版密码登录的公开 API，社区普遍使用与 [foyoux/aligo](https://github.com/foyoux/aligo) 相同的 **Web API**（`auth.aliyundrive.com` + `api.aliyundrive.com`），通过 `refresh_token` 维持会话。

当前仓库尚无阿里云盘模块。本工单交付 **可复用的登录脚本 + httpx 客户端 + 冒烟验证**，为后续 `live.upload_on_complete` 等集成铺路。

已验证要点（开发机）：

- Playwright 登录：推荐 QR / 桌面快捷登录；密码模式需系统 Chrome（`--channel chrome`），内置 Chromium 易被滑块拦截。
- 容量须读 `getUserCapacityInfo`（账户总用量），勿用 `drive/get` 的 `used_size`（仅默认盘）。
- OSS 分片 PUT 不得带 API `Authorization`；下载 GET 须带 `Referer: https://www.aliyundrive.com/`。

## 验收标准

### 阶段 A — 本 PR（基础能力）

- [ ] `src/media2text/core/cloud/aliyundrive.py`：`AliyunDriveClient` 支持 refresh、列表、搜索（`name match` DSL）、元数据、下载、上传（`createWithFolders` + 10MiB 分片）、回收站删除、账户容量 `AccountCapacity`
- [ ] API 路径/请求头与 aligo `Config.UNI_HEADERS` 对齐；不强制运行时依赖 aligo
- [ ] `scripts/aliyundrive_login.py`：模式 `qr` / `desktop` / `password` / `token` / `auto`；token 写入 `data/sessions/aliyundrive.token.json`
- [ ] `scripts/aliyundrive_api_test.py`：端到端冒烟（容量、列表、上传、下载校验、删除）
- [ ] `pyproject.toml` 可选 extra：`aliyundrive = ["aligo>=6.2.8"]`；`from_aligo()` 桥接可选
- [ ] `docs/issues/` 本规格与索引更新；`CLAUDE.md` 增加登录/冒烟命令摘录

### 阶段 B — 后续工单（本 PR 不做）

- [ ] `config.yaml`：`live.upload_on_complete` 或独立 `aliyundrive` 配置块（目标目录 `parent_file_id`、最小剩余空间）
- [ ] 抖音/B 站 `_finalize_recording` 完成后可选上传 MP4
- [ ] `media2text auth login --platform aliyundrive` CLI 与 `--json` 输出

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"

# 静态检查（新模块）
ruff check src/media2text/core/cloud/ scripts/aliyundrive_*.py

# 需本地 token：先登录（任选其一）
# python scripts/aliyundrive_login.py --mode qr
# python scripts/aliyundrive_login.py --mode token   # .env ALIYUN_DRIVE_REFRESH_TOKEN

# API 冒烟（网络）
python scripts/aliyundrive_api_test.py

# 可选：与 aligo 对照
pip install -e ".[aliyundrive]"
python scripts/aliyundrive_aligo_demo.py

# 回归（不依赖阿里云盘网络）
pytest tests/ -v -q --ignore=tests/live
```

## 非目标范围

- 不使用阿里云盘 **Open API**（`openapi.aliyundrive.com`）OAuth 应用；与个人版 Web token 不通用
- 不实现分享链接、相册、福利码等 aligo 全量能力
- 不在本 PR 接入 `monitor watch` 守护进程或直播流水线自动上传
- 不提交 `data/`、`config.yaml`、`.env`、token 文件

## 待确认问题

- 上传目标目录：根目录 `root` 还是固定 `file_id` 文件夹（需产品默认值）
- 大文件上传是否需 aligo 的 `content_hash` / `proof_code` 秒传（当前仅 `pre_hash` 前 1KB）
