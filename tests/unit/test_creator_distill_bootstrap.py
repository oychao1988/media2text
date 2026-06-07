import json
from pathlib import Path

import pytest
import yaml

from media2text.agent.creator_distill.bootstrap import run_bootstrap_job
from media2text.agent.creator_distill.deferred import maybe_promote_bootstrap
from media2text.agent.creator_distill.enqueue import enqueue_bootstrap
from media2text.agent.profile_resolver import resolve_profile
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.agent


def _seed_creator(workspace: Path, *, sec_uid: str = "sec_distill") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name="Distill Creator",
    )
    conn.close()
    return cid


def _fake_distill() -> dict:
    return {
        "mental_models": [{"title": "节奏", "body": "短线看情绪", "limitation": "样本少"}],
        "decision_heuristics": ["先看大盘"],
        "expression_dna": "直白、口语",
        "honest_boundaries": "非本人，非投资建议",
        "anti_patterns": ["编造语录"],
        "sources": ["local"],
    }


def test_bootstrap_deferred_low_corpus(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "defer_until_min_chars": 2000,
                        "bootstrap_web_research": False,
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws)
    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")
    assert job_id

    result = run_bootstrap_job(cfg, conn, job_id=job_id)
    assert result["ok"] is True
    assert result.get("deferred") is True

    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job is not None
    assert job.status == "deferred"

    profile = resolve_profile(creator_id=cid, cfg=cfg)
    assert profile.memory_paths.profile_dir.is_dir()
    conn.close()


def test_bootstrap_writes_skill(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "defer_until_min_chars": 100,
                        "bootstrap_web_research": False,
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws, sec_uid="sec_writes")
    creator_dir = ws / "creators" / "sec_writes"
    manifest = {
        "live": [
            {
                "summary_path": str(creator_dir / "live" / "a.summary.md"),
            }
        ]
    }
    summary = creator_dir / "live" / "a.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("x" * 500, encoding="utf-8")
    (creator_dir / "agent-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")

    def fake_llm(_cfg, *, display_name, corpus_text):
        assert display_name
        assert len(corpus_text) >= 100
        return _fake_distill()

    result = run_bootstrap_job(cfg, conn, job_id=job_id, llm_fn=fake_llm)
    assert result["ok"] is True
    assert result.get("skill_slug")

    profile = resolve_profile(creator_id=cid, cfg=cfg)
    skill_slug = result["skill_slug"]
    skill_md = profile.memory_paths.profile_dir / "skills" / skill_slug / "SKILL.md"
    assert skill_md.is_file()
    assert profile.memory_paths.soul.is_file()

    data = yaml.safe_load((profile.memory_paths.profile_dir / "profile.yaml").read_text())
    assert skill_slug in (data.get("default_skills") or [])

    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job is not None
    assert job.status == "done"
    conn.close()


def test_deferred_watcher_promotes(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "defer_until_min_chars": 200,
                        "bootstrap_web_research": False,
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws, sec_uid="sec_promote")
    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")
    run_bootstrap_job(cfg, conn, job_id=job_id)
    assert CreatorAgentJobRepo(conn).get(job_id).status == "deferred"

    creator_dir = ws / "creators" / "sec_promote"
    summary = creator_dir / "live" / "b.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("y" * 400, encoding="utf-8")
    manifest = {"live": [{"summary_path": str(summary)}]}
    (creator_dir / "agent-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert maybe_promote_bootstrap(cfg, conn, creator_id=cid) is True
    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job is not None
    assert job.status == "pending"
    conn.close()


def test_distill_atomic_write(tmp_path) -> None:
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "defer_until_min_chars": 50,
                        "bootstrap_web_research": False,
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws, sec_uid="sec_atomic")
    creator_dir = ws / "creators" / "sec_atomic"
    summary = creator_dir / "live" / "c.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("z" * 300, encoding="utf-8")
    (creator_dir / "agent-manifest.json").write_text(
        json.dumps({"live": [{"summary_path": str(summary)}]}),
        encoding="utf-8",
    )

    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    skill_dir = profile.memory_paths.profile_dir / "skills" / "distill-creator-perspective"
    skill_path = skill_dir / "SKILL.md"

    def failing_writer(path: Path, content: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("partial", encoding="utf-8")
        raise RuntimeError("simulated interrupt")

    result = run_bootstrap_job(
        cfg,
        conn,
        job_id=job_id,
        llm_fn=lambda _c, *, display_name, corpus_text: _fake_distill(),
        write_skill_fn=failing_writer,
    )
    assert result["ok"] is False
    assert not skill_path.is_file()
    assert not profile.memory_paths.soul.is_file()
    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job is not None
    assert job.status == "failed"
    conn.close()


def test_bootstrap_failed_missing_tavily_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.agent.creator_distill.bootstrap.resolve_tavily_api_key",
        lambda **_: None,
    )
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "bootstrap_web_research": True,
                        "web_search_provider": "tavily",
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws, sec_uid="sec_no_tavily")
    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")
    result = run_bootstrap_job(cfg, conn, job_id=job_id)
    assert result["ok"] is False
    assert result["error"] == "tavily_api_key_missing"
    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job is not None
    assert job.status == "failed"
    conn.close()


def test_bootstrap_proceeds_when_web_ok_local_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.agent.creator_distill.bootstrap.resolve_tavily_api_key",
        lambda **_: "tvly-test",
    )
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "bootstrap_web_research": True,
                        "defer_until_min_chars": 5000,
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws, sec_uid="sec_web_only")

    from media2text.agent.creator_distill.web_research import WebResearchResult

    def fake_web(**_kwargs):
        refs_dir = _kwargs["refs_dir"]
        for name in (
            "01-writings.md",
            "02-conversations.md",
            "03-expression-dna.md",
            "04-external-views.md",
            "05-decisions.md",
            "06-timeline.md",
        ):
            (refs_dir / name).write_text(f"# {name}\n\ncontent", encoding="utf-8")
        return WebResearchResult(channels_ok=2, channel_status={}, total_chars=100)

    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")

    def fake_llm(_cfg, *, display_name, corpus_text):
        assert "Web research" in corpus_text
        return _fake_distill()

    result = run_bootstrap_job(
        cfg,
        conn,
        job_id=job_id,
        llm_fn=fake_llm,
        web_research_fn=fake_web,
    )
    assert result["ok"] is True
    assert result.get("deferred") is not True
    assert result.get("web_channels_ok") == 2

    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job is not None
    assert job.status == "done"
    payload = json.loads(job.payload_json or "{}")
    assert payload.get("web_channels_ok") == 2
    assert payload.get("local_chars") == 0

    profile = resolve_profile(creator_id=cid, cfg=cfg)
    research = (
        profile.memory_paths.profile_dir
        / "skills"
        / result["skill_slug"]
        / "references"
        / "research"
    )
    assert (research / "01-writings.md").is_file()
    conn.close()


def test_deferred_promote_when_web_ok_in_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "media2text.agent.creator_distill.bootstrap.resolve_tavily_api_key",
        lambda **_: "tvly-test",
    )
    ws = tmp_path / "data"
    cfg = AppConfig.model_validate(
        {
            "workspace": str(ws),
            "desktop": {
                "agent": {
                    "distill": {
                        "defer_until_min_chars": 5000,
                        "bootstrap_web_research": True,
                    }
                }
            },
        }
    )
    cid = _seed_creator(ws, sec_uid="sec_web_promote")
    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")

    from media2text.agent.creator_distill.web_research import WebResearchResult

    def empty_web(**_kwargs):
        return WebResearchResult(channels_ok=0, channel_status={}, total_chars=0)

    run_bootstrap_job(cfg, conn, job_id=job_id, web_research_fn=empty_web)
    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job.status == "deferred"

    CreatorAgentJobRepo(conn).mark_deferred(
        job_id,
        payload={
            "web_channels_ok": 2,
            "local_chars": 0,
            "total_chars": 0,
            "deferred_reason": "web_and_local_insufficient",
        },
    )
    assert maybe_promote_bootstrap(cfg, conn, creator_id=cid) is True
    job = CreatorAgentJobRepo(conn).get(job_id)
    assert job.status == "pending"
    conn.close()
