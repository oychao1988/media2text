import pytest

from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.skill_manage import handle_skill_manage
from media2text.agent.skill_provenance import BACKGROUND_REVIEW, FOREGROUND, write_origin_ctx
from media2text.agent.skill_usage import load_usage
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_foreground_create_not_agent_created(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    with write_origin_ctx(FOREGROUND):
        result = handle_skill_manage(
            {"action": "create", "name": "fg-skill", "content": "# FG\n"},
            profile,
        )
    assert result["ok"] is True
    data = load_usage(profile)
    assert data.get("fg-skill", {}).get("agent_created") is not True


def test_background_create_marks_agent_created(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate({"workspace": str(ws)})
    profile = resolve_profile(creator_id=None, cfg=cfg)

    with write_origin_ctx(BACKGROUND_REVIEW):
        result = handle_skill_manage(
            {"action": "create", "name": "bg-skill", "content": "# BG\n"},
            profile,
        )
    assert result["ok"] is True
    data = load_usage(profile)
    entry = data["bg-skill"]
    assert entry["agent_created"] is True
    assert entry["write_origin"] == BACKGROUND_REVIEW
