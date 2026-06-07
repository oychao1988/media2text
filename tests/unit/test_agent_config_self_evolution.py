import pytest

from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_memory_nudge_interval_default() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.memory.nudge_interval == 10
    assert cfg.memory.memory_enabled is True
    assert cfg.memory.soul_max_chars == 4000


def test_agent_review_enabled_default() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.agent.review_enabled is True
    assert cfg.agent.review_max_iterations == 16


def test_skills_and_curator_defaults() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.skills.creation_nudge_interval == 10
    assert cfg.curator.enabled is False


def test_auxiliary_defaults() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.auxiliary.review.provider == "auto"
    assert cfg.auxiliary.review.model == "auto"
    assert cfg.auxiliary.curator.provider == "auto"
