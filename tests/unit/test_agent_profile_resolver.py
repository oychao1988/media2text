import pytest

from media2text.agent.memory_store import (
    read_file_for_profile,
    write_file_for_profile,
)
from media2text.agent.model_tools import handle_function_call
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.prompt_builder import build_system_prompt
from media2text.agent.skills_index import build_skills_index
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.agent


def _seed_creator(workspace, *, sec_uid: str = "sec_profile_test") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name="Profile Test Creator",
    )
    conn.close()
    return cid


def test_workspace_profile_paths(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    assert profile.profile_id == "workspace"
    assert profile.creator_id is None
    assert profile.memory_paths.profile_dir == tmp_path / "data" / ".agent"
    assert (profile.memory_paths.profile_dir / "profile.yaml").is_file()


def test_creator_profile_lazy_template(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cid = _seed_creator(tmp_path / "data", sec_uid="sec_lazy")
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    assert profile.profile_id == "sec_lazy"
    assert profile.creator_id == cid
    agent_dir = tmp_path / "data" / "creators" / "sec_lazy" / ".agent"
    assert agent_dir.is_dir()
    yaml_path = agent_dir / "profile.yaml"
    assert yaml_path.is_file()
    assert profile.enabled_toolsets == ["m2t-core"]
    assert profile.profile_yaml.get("display_name") == "Profile Test Creator"


def test_dual_skills_roots_creator_scope(tmp_path, monkeypatch) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    global_root = tmp_path / "global-skills"
    global_skill = global_root / "shared-skill"
    global_skill.mkdir(parents=True)
    (global_skill / "SKILL.md").write_text("# Shared\n\nGlobal skill.\n", encoding="utf-8")

    cid = _seed_creator(tmp_path / "data", sec_uid="sec_skills")
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    creator_skill_dir = profile.memory_paths.profile_dir / "skills" / "creator-skill"
    creator_skill_dir.mkdir(parents=True)
    (creator_skill_dir / "SKILL.md").write_text("# Creator\n\nCreator skill.\n", encoding="utf-8")

    monkeypatch.setattr(
        "media2text.agent.profile_resolver.default_skills_root",
        lambda: global_root,
    )
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    names = {s.name for s in build_skills_index(profile)}
    assert "shared-skill" in names
    assert "creator-skill" in names

    # Creator override: same slug in both roots — creator wins
    dup_dir = profile.memory_paths.profile_dir / "skills" / "shared-skill"
    dup_dir.mkdir(parents=True)
    (dup_dir / "SKILL.md").write_text("# Override\n\nCreator override.\n", encoding="utf-8")
    skills = build_skills_index(profile)
    override = next(s for s in skills if s.name == "shared-skill")
    assert "Creator override" in override.description or "Override" in override.description


def test_volatile_snapshot_scoped_to_creator(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    workspace_profile = resolve_profile(creator_id=None, cfg=cfg)
    write_file_for_profile(cfg, workspace_profile, "user", "workspace-user-note")
    write_file_for_profile(cfg, workspace_profile, "memory", "workspace-memory-note")

    cid = _seed_creator(tmp_path / "data", sec_uid="sec_volatile")
    creator_profile = resolve_profile(creator_id=cid, cfg=cfg)
    write_file_for_profile(cfg, creator_profile, "user", "creator-user-note")
    write_file_for_profile(cfg, creator_profile, "memory", "creator-memory-note")

    creator_parts = build_system_prompt(
        cfg=cfg,
        profile_ctx=creator_profile,
        thread={"creator_id": cid},
    )
    assert "creator-user-note" in creator_parts.volatile
    assert "creator-memory-note" in creator_parts.volatile
    assert "workspace-user-note" not in creator_parts.volatile
    assert "workspace-memory-note" not in creator_parts.volatile

    workspace_parts = build_system_prompt(
        cfg=cfg,
        profile_ctx=workspace_profile,
        thread={"creator_id": None},
    )
    assert "workspace-user-note" in workspace_parts.volatile
    assert "creator-user-note" not in workspace_parts.volatile


def test_memory_tool_uses_creator_profile(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    cid = _seed_creator(tmp_path / "data", sec_uid="sec_mem_tool")
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    conn = open_db(cfg)
    ctx = ToolContext(cfg=cfg, conn=conn, creator_id=cid, profile=profile)
    out = handle_function_call(
        "memory",
        {"action": "write", "target": "memory", "content": "creator-only memory"},
        ctx,
    )
    assert out["ok"] is True
    assert read_file_for_profile(profile, "memory") == "creator-only memory"
    workspace = resolve_profile(creator_id=None, cfg=cfg)
    assert read_file_for_profile(workspace, "memory") == ""
    conn.close()
