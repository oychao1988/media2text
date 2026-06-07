import json
from unittest.mock import MagicMock

import pytest

from media2text.agent.model_tools import handle_function_call
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.skill_usage import (
    is_pinned,
    load_usage,
    pin,
    record_patch,
    record_view,
)
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_record_view_and_patch(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    skills_root = profile.memory_paths.profile_dir / "skills"
    skill_dir = skills_root / "my-flow"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-flow\ndescription: test\n---\n# My Flow\n",
        encoding="utf-8",
    )

    ctx = ToolContext(cfg=cfg, conn=MagicMock(), profile=profile)
    handle_function_call("skill_view", {"name": "my-flow"}, ctx)
    record_patch(profile, "my-flow")

    data = load_usage(profile)
    assert data["my-flow"]["view_count"] == 1
    assert data["my-flow"]["patch_count"] == 1


def test_bundled_skill_skips_telemetry(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    record_view(profile, "media2text")
    record_patch(profile, "media2text")

    usage_path = profile.memory_paths.profile_dir / "skills" / ".usage.json"
    assert not usage_path.is_file() or "media2text" not in load_usage(profile)


def test_pin_sets_flag(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)
    pin(profile, "distill-creator-perspective")
    assert is_pinned(profile, "distill-creator-perspective")

    usage_path = profile.memory_paths.profile_dir / "skills" / ".usage.json"
    assert usage_path.is_file()
    data = json.loads(usage_path.read_text(encoding="utf-8"))
    assert data["distill-creator-perspective"]["pinned"] is True
