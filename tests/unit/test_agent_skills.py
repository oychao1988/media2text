import json

import pytest

from media2text.agent.model_tools import handle_function_call
from media2text.agent.prompt_builder import build_system_prompt
from media2text.agent.skills_index import (
    build_skills_index,
    default_skills_root,
    handle_skill_view,
    read_skill_body,
)
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent

_FULL_SKILL_MARKER = "## 常见任务"
_REF_SAMPLE = "cli-cheatsheet.md"


@pytest.fixture
def skills_tree(tmp_path):
    root = tmp_path / "agent-skills"
    skill_dir = root / "demo-skill"
    ref_dir = skill_dir / "references"
    ref_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Demo Skill\n\nShort index blurb for Level 0.\n\n"
        f"{_FULL_SKILL_MARKER}\n\n| col | val |\n|-----|-----|\n| a | b |\n",
        encoding="utf-8",
    )
    (ref_dir / _REF_SAMPLE).write_text("# Cheatsheet\n\nfetch /api/agent/threads\n", encoding="utf-8")
    return root


def test_build_skills_index_scans_packages_root() -> None:
    skills = build_skills_index({"skills_roots": [str(default_skills_root())]})
    names = {s.name for s in skills}
    assert "media2text" in names
    assert all(s.description for s in skills)


def test_build_skills_index_custom_root(skills_tree) -> None:
    skills = build_skills_index({"skills_roots": [str(skills_tree)]})
    assert len(skills) == 1
    assert skills[0].name == "demo-skill"
    assert "Short index blurb" in skills[0].description


def test_stable_prompt_excludes_full_skill_body(skills_tree) -> None:
    profile = {"skills_roots": [str(skills_tree)]}
    cfg = AppConfig.model_validate({"workspace": str(skills_tree / "data")})
    parts = build_system_prompt(profile_ctx=profile, cfg=cfg)
    assert "demo-skill" in parts.stable
    assert "Short index blurb" in parts.stable
    assert _FULL_SKILL_MARKER not in parts.stable
    assert "| col | val |" not in parts.stable


def test_skill_view_full_document(skills_tree) -> None:
    profile = {"skills_roots": [str(skills_tree)]}
    payload = handle_skill_view({"name": "demo-skill"}, profile_ctx=profile)
    assert payload["ok"] is True
    body = payload["data"]["content"]
    assert _FULL_SKILL_MARKER in body
    assert read_skill_body("demo-skill", profile_ctx=profile) == body


def test_skill_view_reference_path(skills_tree) -> None:
    profile = {"skills_roots": [str(skills_tree)]}
    payload = handle_skill_view(
        {"name": "demo-skill", "path": _REF_SAMPLE},
        profile_ctx=profile,
    )
    assert payload["ok"] is True
    assert "/api/agent/threads" in payload["data"]["content"]


def test_skills_list_tool_via_model_tools(skills_tree, tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    profile = {"skills_roots": [str(skills_tree)]}
    ctx = ToolContext(cfg=cfg, conn=None, creator_id=None, profile=profile)
    result = handle_function_call("skills_list", "{}", ctx)
    assert result["ok"] is True
    names = [s["name"] for s in result["data"]["skills"]]
    assert "demo-skill" in names


def test_skill_view_tool_missing_name(tmp_path) -> None:
    from media2text.agent.skills_index import default_skills_root

    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    ctx = ToolContext(
        cfg=cfg,
        conn=None,
        creator_id=None,
        profile={"skills_roots": [str(default_skills_root())]},
    )
    result = handle_function_call(
        "skill_view",
        json.dumps({"name": "does-not-exist"}),
        ctx,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGS"
