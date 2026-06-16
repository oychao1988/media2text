# issue_verify：monitor-watch-daemon 阻塞冒烟自动化

GitHub Issue: [#322](https://github.com/oychao1988/media2text/issues/322)  
**Depends on:** [#315](https://github.com/oychao1988/media2text/issues/315)（SH-3 运维脚本；本单为验证/CI 跟进）  
**关联 PR：** [#321](https://github.com/oychao1988/media2text/pull/321)（embedded 锁修复，独立）

## 背景

`python scripts/issue_verify.py --issue 315` 曾在验证块含 `bin/monitor-watch-daemon.sh` 时**挂起数小时**后异常退出：该脚本 `exec` 进 `monitor watch --daemon`，永不返回。Agent/CI 无法区分「通过」与「卡住」。

SH-3 文档已将 shell 冒烟标为手动，但 `issue_verify.py` 仍缺少对**阻塞型守护进程命令**的防护；#315 的手动 AC（假锁 + 脚本清锁）也无可自动化、秒级结束的替代路径。

## 验收标准

- [x] `scripts/verify_monitor_watch_daemon_smoke.py`：在**临时目录**写入假锁 `581`，执行与 `bin/monitor-watch-daemon.sh` 相同的 `clear_invalid_monitor_lock` 前置逻辑，断言锁已清除；**不**启动长期 daemon
- [x] `issue_verify.py` 自动 **SKIP** 已知阻塞命令（`bin/monitor-watch-daemon.sh`、`monitor watch --daemon`、`media2text serve` 等），打印 `SKIP (blocking)` 且 exit 0
- [x] `docs/issues/monitor-self-heal-sh3-ops-docs.md` 的 `## 验证命令` 块加入 smoke 脚本；手动 `bin/monitor-watch-daemon.sh` 仍保留在单独小节
- [x] `pytest tests/unit/test_issue_verify.py -v` 覆盖 skip 与 extract 行为
- [x] `python scripts/issue_verify.py --issue 315` 在 60s 内完成且 exit 0

## 验证命令

```bash
source .venv/bin/activate

pytest tests/unit/test_issue_verify.py tests/unit/test_monitor_lock.py tests/unit/test_process_lock.py -v
python scripts/verify_monitor_watch_daemon_smoke.py
python scripts/issue_verify.py --issue 315
```

## 非目标范围

- 修改 `bin/monitor-watch-daemon.sh` 的 `exec` 语义（仍为运维长期 daemon 入口）
- 在 CI 中启动真实 `monitor watch --daemon` 并连抖音网络
- embedded 模式下自动 `pkill` 遗留 CLI daemon（另开 issue）

## 依赖与顺序

- **建议分支**：`issue-322-issue-verify-daemon-smoke`
- **可并行**：与 #321 无冲突
