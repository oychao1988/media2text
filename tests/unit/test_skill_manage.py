import pytest

from media2text.agent.profile_resolver import resolve_profile, save_profile_yaml
from media2text.agent.skill_manage import SkillManageError, handle_skill_manage
from media2text.agent.skills_index import handle_skills_list
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def _profile(tmp_path):
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    return cfg, resolve_profile(creator_id=None, cfg=cfg)


def test_create_and_patch_skill(tmp_path) -> None:
    cfg, profile = _profile(tmp_path)
    create = handle_skill_manage(
        {"action": "create", "name": "my-workflow", "content": "# Workflow\nstep one\n"},
        profile,
    )
    assert create["ok"] is True

    patch = handle_skill_manage(
        {
            "action": "patch",
            "name": "my-workflow",
            "old_string": "step one",
            "new_string": "step two",
        },
        profile,
    )
    assert patch["ok"] is True

    listed = handle_skills_list(profile)
    names = [s["name"] for s in listed["data"]["skills"]]
    assert "my-workflow" in names

    skill_md = profile.memory_paths.profile_dir / "skills" / "my-workflow" / "SKILL.md"
    assert "step two" in skill_md.read_text(encoding="utf-8")


def test_bundled_skill_protected(tmp_path) -> None:
    _, profile = _profile(tmp_path)
    with pytest.raises(SkillManageError) as exc:
        handle_skill_manage(
            {"action": "patch", "name": "media2text", "old_string": "x", "new_string": "y"},
            profile,
        )
    assert exc.value.code == "PROTECTED_SKILL"


def test_distill_perspective_delete_blocked(tmp_path) -> None:
    cfg, profile = _profile(tmp_path)
    slug = "creator-perspective"
    save_profile_yaml(profile, {"distill": {"skill_slug": slug}})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    skill_dir = profile.memory_paths.profile_dir / "skills" / slug
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: creator-perspective\ndescription: d\n---\n# X\n",
        encoding="utf-8",
    )

    from media2text.agent.skill_usage import pin

    pin(profile, slug)

    with pytest.raises(SkillManageError) as exc:
        handle_skill_manage({"action": "delete", "name": slug}, profile)
    assert exc.value.code == "PROTECTED_SKILL"


def test_distill_research_path_write_blocked(tmp_path) -> None:
    cfg, profile = _profile(tmp_path)
    slug = "foo-perspective"
    save_profile_yaml(profile, {"distill": {"skill_slug": slug}})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    skill_dir = profile.memory_paths.profile_dir / "skills" / slug
    refs = skill_dir / "references" / "research"
    refs.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: foo-perspective\ndescription: d\n---\n# X\n",
        encoding="utf-8",
    )
    (refs / "00-local-corpus.md").write_text("corpus", encoding="utf-8")

    with pytest.raises(SkillManageError) as exc:
        handle_skill_manage(
            {
                "action": "write_file",
                "name": slug,
                "path": "references/research/00-local-corpus.md",
                "content": "tampered",
            },
            profile,
        )
    assert exc.value.code == "PROTECTED_SKILL"


def test_distill_perspective_patch_allowed(tmp_path) -> None:
    cfg, profile = _profile(tmp_path)
    slug = "bar-perspective"
    save_profile_yaml(profile, {"distill": {"skill_slug": slug}})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    skill_dir = profile.memory_paths.profile_dir / "skills" / slug
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: bar-perspective\ndescription: d\n---\n# Pitfall\nold tip\n",
        encoding="utf-8",
    )

    result = handle_skill_manage(
        {
            "action": "patch",
            "name": slug,
            "old_string": "old tip",
            "new_string": "new tip",
        },
        profile,
    )
    assert result["ok"] is True
    assert "new tip" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
