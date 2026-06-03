## 背景

Live Pipeline v2 Spec §0 / §8 锁定 **LiveTick 10s**（配合 G1 P95≤30s），但代码与 `config.example.yaml` 默认仍为 **20s**（`LiveConfig.live_poll_interval_sec`）。

Spec 文首仍写「v1 worker 未实现、可 P0 开工」；引用的 plan `plans/2026-06-03-live-pipeline-v2.md` **不存在**（死链）。

`docs/issues/README.md` 仍将 Archive #18–#20 标为「待开 PR」，GitHub 已 CLOSED。

## 验收标准

### 配置默认值

- [ ] `LiveConfig.live_poll_interval_sec` 默认改为 **10**（`config.py`）
- [ ] `config.example.yaml` § live 注释说明：仅 LiveTick 使用；`monitor.live_poll_interval_sec` 仍为回退
- [ ] `tests/unit/test_config.py` 断言更新
- [ ] `CLAUDE.md` / `README.md` daemon 段落默认间隔与 spec 一致

### Spec / plan 卫生

- [ ] 更新 [2026-06-03-live-pipeline-v2-design.md](../specs/2026-06-03-live-pipeline-v2-design.md)：
  - 状态改为「P0–P3 已交付；本单为收尾」
  - 删除或修正「v1 worker 未实现」过时表述
  - plan 链接：补简短 stub plan **或** 改为指向 `2026-06-02-live-recording-pipeline.md` + 本收尾 issue 列表
- [ ] 更新 [docs/issues/README.md](../../issues/README.md)：Archive #18–#20 标为已交付；新增「Live v2 收尾」小节

## 验证命令

```bash
pytest tests/unit/test_config.py -v
rg 'live_poll_interval_sec' config.example.yaml CLAUDE.md README.md
```

## 非目标

- 改 SlowTick / VOD 间隔
- 生产环境强制覆盖用户已有 `config.yaml`（仅改默认与文档）
