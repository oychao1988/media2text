# 直播录制完成后备份阿里云盘（阶段 B）

GitHub: [#67](https://github.com/oychao1988/media2text/issues/67)  
依赖: [#65](https://github.com/oychao1988/media2text/issues/65) 阶段 A（[#66](https://github.com/oychao1988/media2text/pull/66)）  
分支: `issue-67-aliyundrive-live-upload`  
PR: （创建后填写）

## 背景

阶段 A 已提供 `AliyunDriveClient` 与登录脚本。阶段 B 在抖音/B 站 `_finalize_recording` 收尾链路上，将 **MP4 + 转写 sidecar** 备份到个人阿里云盘，并支持空间不足时的 **滚动清理**、上传后 **默认删除本地**（可配置）。

**产品决策（已确认）**

| # | 决策 |
|---|------|
| 1 | 云路径 `creator_key` 使用 **nickname**（`creators.display_name`）；**上传前强制 `creator sync` profile**；无 nickname 则 `upload_skipped`，**不得**用 `sec_uid` 作云目录名 |
| 2 | `delete_local_after_upload` 默认 **true** |
| 3 | 空间不足时 **滚动清理**云盘 `media2text/` 子树内本工具上传的最旧记录；**须先完成转写**（若开启 `transcribe_on_complete`）再上传/删云 |
| 4 | 云盘重名：**内容相同则覆盖**，**内容不同则重命名**（`auto_rename`） |
| 6 | Profile：**云备份前必须 profile 已同步**（无 `display_name` 则自动调 `sync_creator_profile`；仍失败则 skip） |
| 7 | 滚动清理：**飞书通知**汇总列出本轮删除的云盘文件名 |

## 流水线顺序

```text
remux → mp4
  → refresh_manifest + recording_completed 通知
  → [若 live.transcribe_on_complete] 转写 → .transcript.json / .md
  → [若 aliyundrive.enabled] 云备份（见下）
  → [若 delete_local_after_upload] 删除已成功上传的本地文件
  → refresh_manifest（含 cloud_* / 本地路径空）
```

云备份步骤（`_maybe_upload_live_to_aliyundrive`）：

0. **Profile 门禁**：若 `display_name` 为空或 `is_profile_stale(...)` → 调用 `sync_creator_profile(cfg, creator_id)`；仍无 `display_name` → `upload_skipped`（`profile_not_synced`），不建云目录。
1. 若 `transcribe_on_complete` 且 `upload_transcripts: true`：必须已有 sidecar 或明确 `transcribe_skipped`，否则不上传、不删本地。
2. `getUserCapacityInfo`：若 `free < min_free_bytes` → 执行 **滚动清理**（仅删「已完整备份」条目，见下）→ 仍不足则 `upload_skipped`。
3. `ensure_folder_path` → `media2text/{platform}/{creator_key}/live/`（`creator_key` = 消毒后的 `display_name`）。
4. 上传 `mp4`，再上传 sidecar（若存在）。
5. 校验（远程 `size` == 本地；可选 `sha1` 前 1KB `pre_hash` 与云端一致）→ 写 DB/manifest → 删本地。

## 云路径规范

| 段 | 规则 |
|----|------|
| `root_folder` | 默认 `media2text`（`config.aliyundrive.root_folder`） |
| `platform` | `douyin` / `bilibili` |
| `creator_key` | **仅** `sanitize(display_name)`；无 nickname 不上传（见 Profile 门禁） |
| `sanitize` | 去掉 `/\:*?"<>|` 与首尾空格；过长截断 |
| `live` | 固定目录名 |
| 文件名 | 与本地一致，如 `20260601T081043Z.mp4` |

示例：`media2text/douyin/ TonyC /live/20260601T081043Z.mp4`（消毒后无空格问题）

## 重名策略（同目录同名）

上传前对 `parent_file_id` 下 **精确文件名** 查询（`list` / `search` DSL `name = "..."`）：

| 情况 | 行为 |
|------|------|
| 不存在 | 新建上传 |
| 存在且 **size 相同** 且 **pre_hash（sha1 前 1KB）相同** | 视为同一文件 → **覆盖**（`check_name_mode: overwrite` 或先 `trash` 再上传，以实现为准） |
| 存在但哈希/大小不同 | **不同文件** → `check_name_mode: auto_rename` |

实现须在 Issue 中记录实际可用的 `check_name_mode` 枚举；若 Web API 无可靠 overwrite，则：删云端旧文件再上传（仅当判定为「同内容」或用户配置允许覆盖）。

## 大文件上传

1. **首选**：单次 `createWithFolders` + `part_info_list` 长度为 1（整文件一次 PUT），避免无谓分片。
2. **失败且错误可归类为** 分片大小/数量/请求体限制（维护 `RETRY_AS_CHUNKED_MARKERS` 列表）→ 用现有 10MiB `UPLOAD_CHUNK_SIZE` 重试。
3. **禁止** 阶段 B 仍将整个文件 `read_bytes()` 进内存；应用 **按块读盘** 上传（与分片重试共用逻辑）。
4. 上传超时、网络错误：可配置 `upload_retries`，不计入「同文件覆盖」逻辑。

## 滚动清理（空间不足）

**仅作用于** 本工具在 `media2text/` 下上传且 **DB 表 `cloud_uploads`**（或 `live_sessions.cloud_*`）有记录的文件。

**可删除候选**（同时满足）：

- `upload_status = done`
- 若该条目需要转写：`transcribe_status = done` 或 `transcribe_skipped` 且配置允许无 sidecar
- 若 `upload_transcripts: true`：云端备份记录含 `transcript_json` / `transcript_md` 的 `file_id`（或本地当时无 sidecar 且已记录 `transcripts_not_required`）
- 按 `uploaded_at ASC` 排序，删最旧直至 `free >= min_free_bytes` 或达到 `rolling_cleanup.max_delete_per_round`

**禁止删除**：

- 未完成转写（`transcribe_on_complete` 且 pending/failed 且无 skip）
- 非本工具上传的云文件
- 本地仍依赖且 `delete_local_after_upload` 尚未成功过的条目（若本地已删、仅云留存，则可作为清理候选）

清理后 **重试上传**；仍失败 → `upload_skipped` + 日志 + 飞书通知。

**飞书（滚动清理）**：当 `notify.enabled` 且本轮删除数 > 0，发送 `EventKind.UPLOAD_CLEANUP`（或 `upload_skipped` 子类型），正文 **逐行列出** 已删云文件名（及可选 `cloud_relative_path`），便于审计。

## 本地删除（默认开启）

`delete_local_after_upload: true`（默认）时，在云端校验通过后删除：

- 已成功上传的 `mp4`
- 已成功上传的 sidecar

**不得删除** 上传失败或未纳入上传包的文件。转写失败且未配置 `delete_local_if_transcribe_failed` 时保留 mp4。

## 配置草案（`config.example.yaml`）

```yaml
aliyundrive:
  enabled: false
  token_path: sessions/aliyundrive.token.json
  parent_file_id: root
  root_folder: media2text
  creator_key: nickname          # 固定 nickname → display_name + sanitize
  min_free_bytes: 5368709120     # 5 GiB
  upload_on_live_complete: true
  upload_transcripts: true
  delete_local_after_upload: true
  on_insufficient_space: rolling_cleanup
  rolling_cleanup:
    max_delete_per_round: 20
  upload_retries: 2

# notify.events 增加 upload_cleanup: true 时，滚动清理飞书正文列举删除文件名
```

`live.transcribe_on_complete` 保持独立，与云备份正交。

## 验收标准

### 配置与 CLI
- [ ] `AliyunDriveConfig` + `config.example.yaml` 字段如上
- [ ] `media2text auth login --platform aliyundrive`；`auth status --json` / `doctor` 检查 token

### 路径与元数据
- [ ] 云备份前 **强制 profile sync**（`sync_creator_profile`）；无 `display_name` → `upload_skipped: profile_not_synced`
- [ ] `creator_key` 仅来自消毒后的 `display_name`（nickname）
- [ ] `ensure_folder_path(parent, [root, platform, creator_key, "live"])`
- [ ] `agent-manifest.json` live 项：`cloud_file_id`、`cloud_relative_path`、`cloud_upload_status`
- [ ] DB：`live_sessions` 或 `cloud_uploads` 表记录上传结果与 `uploaded_at`（供滚动清理）

### 流水线
- [ ] 抖音 `douyin/live.py`、B 站 `bilibili/live.py`：转写后再云上传
- [ ] 上传 mp4 + 可选 sidecar；`monitor watch --json` 含 `upload_*` / `upload_skipped`
- [ ] 默认 `delete_local_after_upload: true` 行为符合上文约束

### 重名与上传
- [ ] 同内容覆盖、不同内容 `auto_rename`（见「重名策略」）
- [ ] 大文件：整文件优先，限制错误后分块；**流式读盘**不上 whole-RAM

### 滚动清理
- [ ] `free < min_free_bytes` 时按 `uploaded_at` 删最旧 **已完整备份** 记录
- [ ] **未转写完成**的会话不参与清理、不上传（当 `transcribe_on_complete` + `upload_transcripts`）

### 通知（可选）
- [ ] `EventKind`: `upload_completed`, `upload_failed`, `upload_skipped`
- [ ] 滚动清理：`upload_cleanup` 飞书正文 **列举删除的文件名**（`notify.events.upload_cleanup: true`）

### 测试
- [ ] 单元测试：sanitize、重名判定、清理候选过滤、skip 逻辑（mock client）
- [ ] `pytest tests/ -v -q --ignore=tests/live` 全绿

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src/media2text/core/cloud/ src/media2text/core/platform/
pytest tests/ -v -q --ignore=tests/live

# 人工
# media2text auth login --platform aliyundrive
# 配置 aliyundrive.enabled: true, delete_local_after_upload: true
# 短直播 + monitor watch --daemon 一轮，检查云盘路径与本地是否删除
```

## 非目标范围

- 作品 `videos/`、B 站投稿/动态自动上传（另开工单）
- 多阿里云账号 / 切换 backup 盘
- 自动购买扩容套餐
- 秒传 `content_hash` / `proof_code` 全量优化（可后续增强「同内容」判定）

## 已确认问题（2026-06-01）

- [x] **Profile**：云备份前 **强制 `creator sync` profile**（实现内自动调 `sync_creator_profile`）；仍无 nickname 则 skip，不用 `sec_uid` 作云目录
- [x] **滚动清理飞书**：启用 notify 时，清理后 **汇总列举** 删除的云盘文件名
- [ ] `rolling_cleanup.max_delete_per_round` 默认值 20 是否合适？（实现可先 20）
