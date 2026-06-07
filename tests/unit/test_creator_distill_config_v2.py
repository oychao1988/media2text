import pytest

from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_bootstrap_web_research_default_true() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    assert cfg.desktop.agent.distill.bootstrap_web_research is True


def test_allow_web_research_maps_to_bootstrap() -> None:
    cfg = AppConfig.model_validate(
        {
            "workspace": "/tmp/ws",
            "desktop": {"agent": {"distill": {"allow_web_research": True}}},
        }
    )
    assert cfg.desktop.agent.distill.bootstrap_web_research is True


def test_local_scan_globs_default() -> None:
    cfg = AppConfig.model_validate({"workspace": "/tmp/ws"})
    ls = cfg.desktop.agent.distill.local_scan
    assert ls.enabled is True
    assert "live/**/*.summary.md" in ls.globs
