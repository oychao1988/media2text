import pytest

from media2text.agent.approval import ApprovalGate
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.tools.delegate import delegate_task
from media2text.agent.tools.m2t_handlers import ToolContext, m2t_start_recording
from media2text.agent.tools.toolsets import resolve_tool_names
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.agent


def _seed_creator(workspace, *, sec_uid: str = "sec_delegate") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name="Delegate Creator",
    )
    conn.close()
    return cid


def test_delegate_inherits_creator_profile(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cid = _seed_creator(ws)
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    profile_yaml = profile.memory_paths.profile_dir / "profile.yaml"
    profile_yaml.write_text(
        "enabled_toolsets:\n  - m2t-core\n  - m2t-delegation\n",
        encoding="utf-8",
    )
    profile = resolve_profile(creator_id=cid, cfg=cfg)

    class FakeAgent:
        def __init__(self, db, cfg, supervisor=None):
            self.creator_id = None

        def run_conversation(self, *, display_thread_id, user_text):
            return f"done:{display_thread_id}"

    monkeypatch.setattr("media2text.agent.ai_agent.AIAgent", FakeAgent)
    ctx = ToolContext(
        cfg=cfg,
        conn=open_db(cfg),
        creator_id=cid,
        profile=profile,
        display_thread_id="thread-1",
    )
    result = delegate_task(ctx, task="summarize latest live")
    assert result["ok"] is True
    assert result["data"]["creator_id"] == cid
    names = resolve_tool_names(profile, cfg)
    assert "delegate_task" in names


def test_m2t_start_recording_requires_approval(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cid = _seed_creator(ws, sec_uid="sec_rec")
    cfg = AppConfig.model_validate({"workspace": str(ws), "security": {"command_approval": "prompt"}})
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    gate = ApprovalGate(cfg, auto_approve=False, timeout_sec=0.1)
    ctx = ToolContext(cfg=cfg, conn=open_db(cfg), creator_id=cid, profile=profile, approval_gate=gate)

    monkeypatch.setattr(
        "media2text.agent.tools.m2t_handlers.recording_svc.start_recording",
        lambda *_a, **_k: {"ok": True},
    )
    result = m2t_start_recording(ctx)
    assert result["ok"] is False
    assert result["error"]["code"] == "DENIED"
