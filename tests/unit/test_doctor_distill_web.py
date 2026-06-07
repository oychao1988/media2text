import pytest

from media2text.core.config import AppConfig
from media2text.core.doctor_checks import build_doctor_report
from media2text.core.storage.db import connect

pytestmark = pytest.mark.desktop


def test_doctor_web_search_tavily_when_bootstrap_web_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("TAVILY_API_KEY=tvly-test\n", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.agent.creator_distill.tavily_client.env_file_path",
        lambda: env_path,
    )
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "desktop": {"agent": {"distill": {"bootstrap_web_research": True}}},
        }
    )
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    report = build_doctor_report(cfg, conn)

    tavily = next(c for c in report["checks"] if c["name"] == "web_search_tavily")
    assert tavily["ok"] is True
    assert tavily["relevant"] is True


def test_doctor_web_search_tavily_reads_env_file_not_stale_environ(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("TAVILY_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr(
        "media2text.agent.creator_distill.tavily_client.env_file_path",
        lambda: env_path,
    )
    monkeypatch.setenv("TAVILY_API_KEY", "stale-process")

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "desktop": {"agent": {"distill": {"bootstrap_web_research": True}}},
        }
    )
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    report = build_doctor_report(cfg, conn)

    tavily = next(c for c in report["checks"] if c["name"] == "web_search_tavily")
    assert tavily["ok"] is True


def test_doctor_web_search_tavily_missing_key(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    monkeypatch.setattr(
        "media2text.agent.creator_distill.tavily_client.env_file_path",
        lambda: env_path,
    )
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "desktop": {"agent": {"distill": {"bootstrap_web_research": True}}},
        }
    )
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    report = build_doctor_report(cfg, conn)

    tavily = next(c for c in report["checks"] if c["name"] == "web_search_tavily")
    assert tavily["ok"] is False
    assert "TAVILY_API_KEY" in (tavily.get("hint") or "")


def test_doctor_skips_web_search_when_bootstrap_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "desktop": {"agent": {"distill": {"bootstrap_web_research": False}}},
        }
    )
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    report = build_doctor_report(cfg, conn)

    assert not any(c["name"] == "web_search_tavily" for c in report["checks"])


def test_doctor_summarize_llm_when_bootstrap_web_without_summarize_enabled(
    tmp_path, monkeypatch
) -> None:
    import sys
    import types

    monkeypatch.setitem(sys.modules, "openai", types.ModuleType("openai"))
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("NVIDIA_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr("media2text.core.env_file.env_file_path", lambda: env_path)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    cfg = AppConfig.model_validate(
        {
            "workspace": str(tmp_path / "data"),
            "summarize": {
                "enabled": False,
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://example.com/v1",
                            "api_key_envs": ["NVIDIA_API_KEY"],
                            "models": ["m1"],
                        }
                    ]
                },
            },
            "desktop": {"agent": {"distill": {"bootstrap_web_research": True}}},
        }
    )
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    report = build_doctor_report(cfg, conn)

    llm = next(c for c in report["checks"] if c["name"] == "summarize_llm")
    assert llm["ok"] is True
