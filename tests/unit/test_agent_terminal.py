import pytest

from media2text.agent.approval import ApprovalGate, shell_needs_approval
from media2text.agent.path_guard import resolve_under_cwd
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.agent.tools.terminal_handlers import read_file, terminal
from media2text.agent.vendor.hermes.local import LocalRunResult
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.agent


def _seed_creator(workspace, *, sec_uid: str = "sec_term") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name="Terminal Creator",
    )
    conn.close()
    return cid


def test_terminal_runs_in_creator_cwd(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cid = _seed_creator(ws, sec_uid="sec_term")
    cfg = AppConfig.model_validate({"workspace": str(ws), "security": {"command_approval": "off"}})
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    creator_dir = ws / "creators" / "sec_term"
    marker = creator_dir / "agent-marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)

    def fake_run(*, command, cwd, shell, timeout_sec):
        assert cwd == creator_dir.resolve()
        marker.write_text("ok", encoding="utf-8")
        return LocalRunResult(exit_code=0, stdout="done", stderr="")

    monkeypatch.setattr(
        "media2text.agent.tools.terminal_handlers.run_local_command",
        fake_run,
    )
    ctx = ToolContext(
        cfg=cfg,
        conn=object(),
        creator_id=cid,
        profile=profile,
        approval_gate=ApprovalGate(cfg, auto_approve=True),
    )
    result = terminal(ctx, command=f"echo ok > {marker.name}")
    assert result["ok"] is True
    assert marker.is_file()


def test_path_guard_blocks_escape(tmp_path) -> None:
    ws = tmp_path / "data"
    cid = _seed_creator(ws)
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    cwd = profile.terminal_cwd
    with pytest.raises(ValueError, match="escapes"):
        resolve_under_cwd(cwd, "../../../etc/passwd")


def test_dangerous_shell_requires_approval(tmp_path) -> None:
    assert shell_needs_approval("rm -rf /tmp/foo") is True
    assert shell_needs_approval("echo hello") is False


def test_terminal_denied_without_approval(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cid = _seed_creator(ws, sec_uid="sec_deny")
    cfg = AppConfig.model_validate(
        {"workspace": str(ws), "security": {"command_approval": "prompt"}}
    )
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    gate = ApprovalGate(cfg, auto_approve=False, timeout_sec=0.1)

    monkeypatch.setattr(
        "media2text.agent.tools.terminal_handlers.run_local_command",
        lambda **_: LocalRunResult(0, "", ""),
    )
    ctx = ToolContext(cfg=cfg, conn=object(), creator_id=cid, profile=profile, approval_gate=gate)
    result = terminal(ctx, command="rm -rf .")
    assert result["ok"] is False
    assert result["error"]["code"] == "DENIED"


def test_read_file_under_cwd(tmp_path) -> None:
    ws = tmp_path / "data"
    cid = _seed_creator(ws, sec_uid="sec_read")
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    note = profile.terminal_cwd / "note.txt"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("hello", encoding="utf-8")
    ctx = ToolContext(cfg=cfg, conn=object(), creator_id=cid, profile=profile)
    result = read_file(ctx, path="note.txt")
    assert result["ok"] is True
    assert result["data"]["content"] == "hello"
