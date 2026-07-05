
from media2text.core.config import AppConfig, DesktopConfig
from media2text.core.runtime.serve_startup import (
    is_media2text_serve_pid,
    resolve_serve_conflicts,
)


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        desktop=DesktopConfig(auto_start_monitor=True),
    )


def test_resolve_serve_conflicts_manual_blocks_other(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    monkeypatch.setattr(
        "media2text.core.runtime.serve_startup.list_media2text_serve_pids",
        lambda: [4242],
    )
    monkeypatch.setattr(
        "media2text.core.runtime.serve_startup._pid_alive",
        lambda pid: pid == 4242,
    )
    result = resolve_serve_conflicts(cfg, 8765, managed=False, own_pid=9999)
    assert result["ok"] is False
    assert result["already_running"] is True
    assert result["pid"] == 4242


def test_resolve_serve_conflicts_managed_kills_others(tmp_path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.ensure_workspace()
    monkeypatch.setattr(
        "media2text.core.runtime.serve_startup.list_media2text_serve_pids",
        lambda: [1111, 2222],
    )
    killed: list[int] = []

    def _stop(pid: int, **_kwargs) -> bool:
        killed.append(pid)
        return True

    monkeypatch.setattr("media2text.core.runtime.serve_startup.stop_serve_pid", _stop)
    result = resolve_serve_conflicts(cfg, 8765, managed=True, own_pid=3333)
    assert result["ok"] is True
    assert sorted(killed) == [1111, 2222]


def test_is_media2text_serve_pid(monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.core.runtime.serve_startup._process_commandline",
        lambda pid: "/path/.venv/bin/python -m media2text serve --port 8765"
        if pid == 1
        else "python -m media2text monitor watch --daemon",
    )
    monkeypatch.setattr("media2text.core.runtime.serve_startup._pid_alive", lambda _pid: True)
    assert is_media2text_serve_pid(1) is True
    assert is_media2text_serve_pid(2) is False
