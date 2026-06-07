import json
from pathlib import Path

import pytest
import yaml

from media2text.agent.creator_distill.bootstrap import run_bootstrap_job
from media2text.agent.creator_distill.enqueue import enqueue_bootstrap, enqueue_evolve
from media2text.agent.creator_distill.evolve import run_evolve_job
from media2text.agent.creator_distill.evolve_log import evolve_log_path, read_evolve_log
from media2text.agent.creator_distill.evolve_patch import trim_memory
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.skills_index import handle_skill_view, handle_skills_list
from media2text.core.config import AppConfig
from media2text.core.storage.repos import CreatorAgentJobRepo, CreatorRepo
from media2text.core.workspace import open_db

pytestmark = pytest.mark.agent


def _fake_distill() -> dict:
    return {
        "mental_models": [{"title": "节奏", "body": "短线看情绪", "limitation": "样本少"}],
        "decision_heuristics": ["先看大盘"],
        "expression_dna": "直白、口语",
        "honest_boundaries": "非本人，非投资建议",
        "anti_patterns": ["编造语录"],
        "sources": ["local"],
    }


def _seed_creator(workspace: Path, *, sec_uid: str = "sec_evolve") -> str:
    cfg = AppConfig.model_validate({"workspace": str(workspace)})
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://www.douyin.com/user/{sec_uid}",
        platform="douyin",
        display_name="Evolve Creator",
    )
    conn.close()
    return cid


def _bootstrap_skill(tmp_path: Path, sec_uid: str, cid: str) -> AppConfig:
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
    creator_dir = ws / "creators" / sec_uid
    summary = creator_dir / "live" / "boot.summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("bootstrap corpus " * 40, encoding="utf-8")
    (creator_dir / "agent-manifest.json").write_text(
        json.dumps({"live": [{"id": "boot", "summary_path": str(summary)}]}),
        encoding="utf-8",
    )
    conn = open_db(cfg)
    job_id = enqueue_bootstrap(cfg, conn, creator_id=cid, trigger="manual")
    run_bootstrap_job(
        cfg,
        conn,
        job_id=job_id,
        llm_fn=lambda _c, *, display_name, corpus_text: _fake_distill(),
    )
    conn.close()
    return cfg


def _session_setup(
    tmp_path: Path,
    *,
    sec_uid: str,
    session_id: str,
    summary_text: str,
) -> tuple[AppConfig, str, str]:
    ws = tmp_path / "data"
    cid = _seed_creator(ws, sec_uid=sec_uid)
    cfg = _bootstrap_skill(tmp_path, sec_uid, cid)

    creator_dir = ws / "creators" / sec_uid
    live_dir = creator_dir / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    media = live_dir / "20260101.mp4"
    media.write_bytes(b"x")
    summary = media.with_suffix(".summary.md")
    summary.write_text(summary_text, encoding="utf-8")

    conn = open_db(cfg)
    conn.execute(
        """
        INSERT INTO live_sessions (id, creator_id, status, started_at, local_path)
        VALUES (?, ?, 'completed', '2026-01-01T00:00:00+00:00', ?)
        """,
        (session_id, cid, str(media.relative_to(ws))),
    )
    conn.commit()
    manifest = {
        "live": [
            {
                "id": session_id,
                "summary_path": str(summary.relative_to(creator_dir)),
            }
        ]
    }
    (creator_dir / "agent-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    conn.close()
    return cfg, cid, session_id


def test_evolve_idempotent(tmp_path) -> None:
    cfg, cid, session_id = _session_setup(
        tmp_path,
        sec_uid="sec_idem",
        session_id="sess-idem-1",
        summary_text="本场强调控节奏与仓位管理。",
    )
    conn = open_db(cfg)
    job1 = enqueue_evolve(cfg, conn, creator_id=cid, source_id=session_id, trigger="manual")
    assert job1
    job2 = enqueue_evolve(cfg, conn, creator_id=cid, source_id=session_id, trigger="manual")
    assert job2 is None

    result = run_evolve_job(cfg, conn, job_id=job1)
    assert result["ok"] is True
    assert result.get("skipped") is not True

    profile = resolve_profile(creator_id=cid, cfg=cfg)
    skill_slug = yaml.safe_load(
        (profile.memory_paths.profile_dir / "profile.yaml").read_text()
    )["distill"]["skill_slug"]
    skill_md = (
        profile.memory_paths.profile_dir / "skills" / skill_slug / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert session_id in skill_md
    assert profile.memory_paths.memory.is_file()
    assert session_id in profile.memory_paths.memory.read_text(encoding="utf-8")

    job3 = enqueue_evolve(cfg, conn, creator_id=cid, source_id=session_id, trigger="manual")
    assert job3 is None

    jobs = CreatorAgentJobRepo(conn)
    done = jobs.find_evolve_by_source(cid, session_id)
    assert done is not None
    assert done.status == "done"

    log_path = evolve_log_path(profile.memory_paths.profile_dir)
    assert log_path.is_file()
    entries, total = read_evolve_log(profile.memory_paths.profile_dir)
    assert total == 1
    assert entries[0]["source_id"] == session_id

    skills = handle_skills_list(profile)
    names = [s["name"] for s in skills["data"]["skills"]]
    assert skill_slug in names
    view = handle_skill_view({"name": skill_slug}, profile_ctx=profile)
    assert session_id in view["data"]["content"]

    conn.close()


def test_evolve_memory_bound(tmp_path) -> None:
    cfg, cid, session_id = _session_setup(
        tmp_path,
        sec_uid="sec_mem",
        session_id="sess-mem-1",
        summary_text="MEMORY bound test excerpt.",
    )
    cfg = AppConfig.model_validate(
        {
            **cfg.model_dump(),
            "memory": {"max_chars": 120},
        }
    )
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    memory_path = profile.memory_paths.memory
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    long_body = "\n".join(f"- bullet {i} with padding text" for i in range(20))
    memory_path.write_text("# MEMORY\n\n" + long_body, encoding="utf-8")

    trimmed = trim_memory(memory_path.read_text(encoding="utf-8"), max_chars=120)
    assert len(trimmed) <= 120

    conn = open_db(cfg)
    job_id = enqueue_evolve(cfg, conn, creator_id=cid, source_id=session_id, trigger="manual")
    run_evolve_job(cfg, conn, job_id=job_id)
    after = memory_path.read_text(encoding="utf-8")
    assert len(after) <= 120
    assert session_id in after
    conn.close()


def test_evolve_does_not_touch_research(tmp_path) -> None:
    cfg, cid, session_id = _session_setup(
        tmp_path,
        sec_uid="sec_research",
        session_id="sess-research-1",
        summary_text="本场补充一条可写入启发式的观点。",
    )
    profile = resolve_profile(creator_id=cid, cfg=cfg)
    research = (
        profile.memory_paths.profile_dir
        / "skills"
        / "evolve-creator-perspective"
        / "references"
        / "research"
    )
    writings = research / "01-writings.md"
    writings.parent.mkdir(parents=True, exist_ok=True)
    writings.write_text("# writings\n\nseed", encoding="utf-8")
    mtime_before = writings.stat().st_mtime_ns

    conn = open_db(cfg)
    job_id = enqueue_evolve(cfg, conn, creator_id=cid, source_id=session_id, trigger="manual")
    run_evolve_job(cfg, conn, job_id=job_id)
    assert writings.stat().st_mtime_ns == mtime_before
    conn.close()
