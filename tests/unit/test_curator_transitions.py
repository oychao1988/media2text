from datetime import datetime, timedelta, timezone

import pytest

from media2text.agent.curator import phase1_auto_transitions, run_curator
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.skill_usage import load_usage, mark_agent_created, save_usage
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def _seed_agent_skill(profile, name: str, *, idle_days: float) -> None:
    skills_root = profile.memory_paths.profile_dir / "skills"
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n# {name}\n",
        encoding="utf-8",
    )
    mark_agent_created(profile, name, write_origin="background_review")
    data = load_usage(profile)
    entry = data[name]
    stamp = (
        datetime.now(timezone.utc) - timedelta(days=idle_days)
    ).replace(microsecond=0).isoformat()
    entry["last_used_at"] = stamp
    entry["state"] = "active"
    save_usage(profile, data)


def test_stale_transition_at_30_days(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    _seed_agent_skill(profile, "old-skill", idle_days=31)

    now = datetime.now(timezone.utc)
    result = phase1_auto_transitions(profile, dry_run=False, now=now)
    assert "old-skill" in result.stale

    usage = load_usage(profile)
    assert usage["old-skill"]["state"] == "stale"


def test_archive_transition_at_90_days(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    _seed_agent_skill(profile, "ancient-skill", idle_days=95)

    now = datetime.now(timezone.utc)
    result = phase1_auto_transitions(profile, dry_run=False, now=now)
    assert "ancient-skill" in result.archived

    archive = profile.memory_paths.profile_dir / "skills" / ".archive" / "ancient-skill"
    assert archive.is_dir()
    assert not (profile.memory_paths.profile_dir / "skills" / "ancient-skill").exists()


def test_skips_non_agent_created(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    skills_root = profile.memory_paths.profile_dir / "skills"
    name = "foreground-skill"
    (skills_root / name / "SKILL.md").parent.mkdir(parents=True)
    (skills_root / name / "SKILL.md").write_text("# fg\n", encoding="utf-8")
    data = {name: {"state": "active", "agent_created": False, "last_used_at": "2000-01-01T00:00:00+00:00"}}
    save_usage(profile, data)

    result = phase1_auto_transitions(profile, dry_run=False)
    assert name not in result.stale
    assert name not in result.archived


def test_dry_run_does_not_mutate(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    _seed_agent_skill(profile, "dry-skill", idle_days=40)

    run_curator(cfg, dry_run=True, profile=profile, run_llm=False)
    usage = load_usage(profile)
    assert usage["dry-skill"]["state"] == "active"


def test_run_curator_writes_report(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    report = run_curator(cfg, dry_run=True, profile=profile, run_llm=False)
    report_path = report["profiles"][0]["report_path"]
    path = profile.memory_paths.profile_dir / "logs" / "curator" / report["run_id"] / "REPORT.md"
    assert path.is_file()
    assert str(path) == report_path
    assert "Phase 1" in path.read_text(encoding="utf-8")
