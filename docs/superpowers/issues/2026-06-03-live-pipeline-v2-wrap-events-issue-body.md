## 背景

P2（#85）已交付 `live timeline` 与大部分 pipeline events。对照 Spec §6.2，仍缺：

1. **`stream_resolve` 阶段** — 拉流 URL 解析起止未打点
2. **`platform_live_started_at`** — 列已迁移（v3），源码未从平台 API 写入

影响 G7 全链路可视与事后对齐平台真实开播时刻。

**参考**

- [docs/superpowers/specs/2026-06-03-live-pipeline-v2-design.md](../specs/2026-06-03-live-pipeline-v2-design.md) §6.2、§7
- `src/media2text/core/live/recording.py`
- `tests/unit/test_pipeline_events.py`（扩展）

## 验收标准

### stream_resolve 事件

- [ ] 在 `LiveRecordingCore` 解析 `stream_flv_url` 成功/失败路径使用 `stage_event` / `record_event`：`stage=stream_resolve`，`status=started|completed|failed`
- [ ] 失败时 `detail_json` 含可诊断原因（不含密钥）
- [ ] 单元或集成测试：mock 解析失败 timeline 含 `stream_resolve` failed

### platform_live_started_at

- [ ] 若 Douyin/B 站 live room 响应含可解析的开播时间字段，写入 `live_sessions.platform_live_started_at`（ISO8601 TEXT）
- [ ] 无字段时保持 NULL（不伪造）
- [ ] 测试：fixture JSON 解析写入；缺失字段不报错

### 文档

- [ ] Spec §6.2 事件表与实现一致；或注明平台不支持时为 NULL

## 验证命令

```bash
pytest tests/unit/test_pipeline_events.py tests/unit/test_live_recording_core.py -v
media2text live timeline <session_id> --json   # 应含 stream_resolve
```

## 非目标

- 新平台适配
- 改 remux / offline 墙钟逻辑
